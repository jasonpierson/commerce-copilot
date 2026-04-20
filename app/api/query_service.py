from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from uuid import uuid4

from app.api.incident_service import IncidentService
from app.api.inventory_service import InventoryService
from app.api.schemas import (
    ApiLink,
    ApprovalSuggestion,
    Citation,
    IncidentEvent,
    IncidentRecord,
    QueryRequest,
    QueryResponse,
    QueryResponseData,
    QueryResponseMeta,
)
from app.retrieval.exceptions import RetrievalError
from app.retrieval.models import RetrievalQueryRequest, RetrievalResult
from app.retrieval.runtime import build_retrieval_service


class UnsupportedRouteError(Exception):
    def __init__(self, route_type: str, message: str) -> None:
        super().__init__(message)
        self.route_type = route_type


@dataclass(slots=True)
class QueryService:
    def _classify_route(self, request: QueryRequest) -> str:
        if request.route_type_override:
            return request.route_type_override

        query = request.message.lower()

        if any(token in query for token in ("inventory", "in stock", "sku", "stock level", "approval status")):
            return "structured_lookup"

        if any(token in query for token in ("escalate", "escalation", "high priority", "medium priority", "approve escalation")):
            return "escalation_guidance"

        if any(token in query for token in ("incident", "inc-", "customer impact", "checkout problem", "outage")):
            return "incident_summary"

        return "policy_qa"

    def _extract_content(self, chunk_text: str) -> str:
        marker = "Content:"
        if marker in chunk_text:
            return chunk_text.split(marker, 1)[1].strip()
        return chunk_text.strip()

    def _extract_inventory_query(self, message: str) -> str:
        normalized = message.strip()
        patterns = [
            r"inventory for (?P<product>.+)$",
            r"in stock(?: for)? (?P<product>.+)$",
            r"stock level(?: for)? (?P<product>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                product = match.group("product").strip(" ?.")
                return re.sub(r"^the\s+", "", product, flags=re.IGNORECASE)
        return re.sub(r"^the\s+", "", normalized.strip(" ?."), flags=re.IGNORECASE)

    def _extract_incident_code(self, message: str) -> str | None:
        match = re.search(r"\b(INC-\d{3,})\b", message, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).upper()

    def _build_incident_support_query(
        self,
        message: str,
        incident: IncidentRecord | None,
    ) -> str:
        if not incident:
            return message

        parts = [message]
        if incident.title:
            parts.append(f"Incident title: {incident.title}")
        if incident.service_area:
            parts.append(f"Service area: {incident.service_area}")
        if incident.severity:
            parts.append(f"Severity: {incident.severity}")
        if incident.customer_impact:
            parts.append(f"Customer impact: {incident.customer_impact}")
        return "\n".join(parts)

    def _retrieve_context(self, request: QueryRequest, *, route_type: str, request_id: str) -> list[RetrievalResult]:
        return build_retrieval_service().retrieve_context(
            RetrievalQueryRequest(
                query=request.message,
                route_type=route_type,
                user_role=request.user_role,
                top_k=request.top_k,
            ),
            request_id=request_id,
            user_id=request.user_id,
        )

    def _build_answer(self, retrieval_results: list[RetrievalResult]) -> str:
        if not retrieval_results:
            return (
                "I couldn't find matching policy or process context for that question. "
                "Try rephrasing it with more specific operational terms."
            )

        supporting_points: list[str] = []
        seen_sections: set[tuple[str, str | None]] = set()

        for result in retrieval_results[:3]:
            section_key = (result.doc_key, result.section_title)
            if section_key in seen_sections:
                continue
            supporting_points.append(self._extract_content(result.chunk_text))
            seen_sections.add(section_key)

        if not supporting_points:
            return (
                "I found relevant policy documents, but not enough section content to draft an answer yet."
            )

        primary = supporting_points[0]
        if len(supporting_points) == 1:
            return primary

        related = " ".join(point for point in supporting_points[1:] if point)
        return f"{primary}\n\nSupporting context: {related}".strip()

    def _build_incident_links(self, incident: IncidentRecord | None) -> list[ApiLink]:
        if not incident:
            return []

        return [
            ApiLink(
                rel="incident_detail",
                href=f"/api/v1/incidents/{incident.incident_code}",
                method="GET",
                description="View the structured incident record and full timeline.",
            )
        ]

    def _build_citations(self, retrieval_results: list[RetrievalResult]) -> list[Citation]:
        citations: list[Citation] = []
        seen: set[tuple[str, str | None]] = set()

        for result in retrieval_results:
            citation_key = (result.doc_key, result.section_title)
            if citation_key in seen:
                continue
            citations.append(
                Citation(
                    doc_key=result.doc_key,
                    title=result.title,
                    section_title=result.section_title,
                    relevance_score=result.relevance_score,
                )
            )
            seen.add(citation_key)

        return citations

    def _format_incident_duration(
        self,
        start_time: datetime | None,
        resolved_time: datetime | None,
    ) -> str | None:
        if not start_time:
            return None

        end_time = resolved_time or datetime.now(UTC)
        minutes = int(max((end_time - start_time).total_seconds(), 0) // 60)
        if minutes <= 0:
            return None
        return f"about {minutes} minute(s)"

    def _build_incident_next_step(
        self,
        incident: IncidentRecord | None,
        timeline: list[IncidentEvent],
    ) -> str | None:
        if not incident:
            return None

        if incident.status in {"open", "investigating"}:
            if incident.severity in {"sev1", "sev2"}:
                return "Keep mitigation work active and escalate if customer impact is still growing."
            return "Keep the timeline current and continue validating scope before closing the incident."

        if incident.status == "mitigated":
            return "Monitor recovery signals and prepare the closure summary once stability holds."

        if incident.status == "resolved":
            if timeline:
                return "Publish the final incident summary and capture any follow-up remediation from the timeline."
            return "Publish the final incident summary and capture follow-up remediation."

        return "Continue updating the incident record with status changes and next actions."

    def _build_approval_suggestion(
        self,
        incident: IncidentRecord | None,
    ) -> ApprovalSuggestion | None:
        if not incident:
            return None

        status = incident.status.lower()
        severity = incident.severity.lower()
        impact = (incident.customer_impact or "").lower()

        if status not in {"open", "investigating", "mitigated"}:
            return None

        if severity not in {"sev1", "sev2"} and "elevated" not in impact and "widespread" not in impact:
            return None

        proposed_priority = "critical" if severity == "sev1" else "high"
        reason = (
            f"{incident.incident_code} is still {incident.status} with {incident.severity.upper()} impact. "
            "Create a pending escalation approval request if the incident needs management-level attention."
        )
        return ApprovalSuggestion(
            reason=reason,
            proposed_priority=proposed_priority,
            incident_code=incident.incident_code,
            create_request=ApiLink(
                rel="approval_request",
                href="/api/v1/escalations",
                method="POST",
                description="Create a pending approval request for an incident escalation.",
            ),
        )

    def _build_incident_answer(
        self,
        retrieval_results: list[RetrievalResult],
        *,
        incident: IncidentRecord | None = None,
        timeline: list[IncidentEvent] | None = None,
    ) -> str:
        timeline = timeline or []

        if incident:
            duration = self._format_incident_duration(incident.start_time, incident.resolved_time)
            answer_parts: list[str] = []

            headline = f"{incident.incident_code} — {incident.title}"
            status_bits = [incident.severity.upper(), incident.status]
            if incident.service_area:
                status_bits.append(incident.service_area)
            headline += f" ({', '.join(status_bits)})"
            if duration:
                headline += f" lasted {duration}."
            else:
                headline += "."
            answer_parts.append(headline)

            if incident.summary:
                answer_parts.append(incident.summary)
            if incident.customer_impact:
                answer_parts.append(f"Customer impact: {incident.customer_impact}")
            if timeline:
                answer_parts.append(f"Latest timeline update: {timeline[-1].event_summary}")

            supporting_bits: list[str] = []
            for result in retrieval_results[:2]:
                supporting_bits.append(self._extract_content(result.chunk_text))
            if supporting_bits:
                answer_parts.append(f"Relevant runbook guidance: {' '.join(supporting_bits)}")

            return "\n\n".join(answer_parts).strip()

        if not retrieval_results:
            return "I couldn't find incident-supporting runbooks or playbooks for that request."

        primary = self._extract_content(retrieval_results[0].chunk_text)
        secondary_bits: list[str] = []
        seen_sections: set[tuple[str, str | None]] = set()

        for result in retrieval_results[1:3]:
            section_key = (result.doc_key, result.section_title)
            if section_key in seen_sections:
                continue
            secondary_bits.append(self._extract_content(result.chunk_text))
            seen_sections.add(section_key)

        if secondary_bits:
            return (
                f"Incident summary guidance: {primary}\n\n"
                f"Likely supporting context: {' '.join(secondary_bits)}"
            ).strip()

        return f"Incident summary guidance: {primary}"

    def handle_query(self, request: QueryRequest, *, request_id: str | None = None) -> QueryResponse:
        route_type = self._classify_route(request)
        request_id = request_id or f"req_{uuid4().hex[:12]}"

        if route_type == "policy_qa":
            try:
                retrieval_results = self._retrieve_context(
                    request,
                    route_type="policy_qa",
                    request_id=request_id,
                )
            except RetrievalError:
                raise

            citations = self._build_citations(retrieval_results)
            answer = self._build_answer(retrieval_results)

            return QueryResponse(
                request_id=request_id,
                route_type="policy_qa",
                data=QueryResponseData(answer=answer, citations=citations),
                meta=QueryResponseMeta(
                    citations_included=bool(citations),
                    tools_used=[],
                    approval_involved=False,
                ),
            )

        if route_type == "incident_summary":
            incident_code = self._extract_incident_code(request.message)
            incident: IncidentRecord | None = None
            timeline: list[IncidentEvent] = []
            tools_used: list[str] = []
            retrieval_request = request

            if incident_code:
                incident_service = IncidentService.from_env()
                incident = incident_service.get_incident(incident_code)
                if incident:
                    timeline = incident_service.get_incident_timeline(incident.incident_id)
                    tools_used.extend(["get_incident", "get_incident_timeline"])
                    retrieval_request = request.model_copy(
                        update={
                            "message": self._build_incident_support_query(
                                request.message,
                                incident,
                            )
                        }
                    )
                else:
                    return QueryResponse(
                        request_id=request_id,
                        route_type="incident_summary",
                        data=QueryResponseData(
                            answer=f"I couldn't find incident {incident_code} in the structured incident data.",
                            citations=[],
                        ),
                        meta=QueryResponseMeta(
                            citations_included=False,
                            tools_used=["get_incident"],
                            approval_involved=False,
                        ),
                    )

            try:
                retrieval_results = self._retrieve_context(
                    retrieval_request,
                    route_type="incident_summary",
                    request_id=request_id,
                )
            except RetrievalError:
                raise

            citations = self._build_citations(retrieval_results)
            answer = self._build_incident_answer(
                retrieval_results,
                incident=incident,
                timeline=timeline,
            )
            recommended_next_step = self._build_incident_next_step(incident, timeline)
            approval_suggestion = self._build_approval_suggestion(incident)
            links = self._build_incident_links(incident)
            if approval_suggestion:
                links.append(approval_suggestion.create_request)

            return QueryResponse(
                request_id=request_id,
                route_type="incident_summary",
                data=QueryResponseData(
                    answer=answer,
                    citations=citations,
                    incident=incident,
                    incident_timeline=timeline,
                    customer_impact=incident.customer_impact if incident else None,
                    recommended_next_step=recommended_next_step,
                    links=links,
                    approval_suggestion=approval_suggestion,
                ),
                meta=QueryResponseMeta(
                    citations_included=bool(citations),
                    tools_used=tools_used,
                    approval_involved=False,
                ),
            )

        if route_type == "structured_lookup":
            product_query = self._extract_inventory_query(request.message)
            outcome = InventoryService.from_env().lookup_inventory(product_query)
            return QueryResponse(
                request_id=request_id,
                route_type="structured_lookup",
                data=QueryResponseData(
                    answer=outcome.answer,
                    citations=[],
                    product=outcome.product,
                    inventory_results=outcome.inventory_results,
                ),
                meta=QueryResponseMeta(
                    citations_included=False,
                    tools_used=["resolve_product", "check_inventory"],
                    approval_involved=False,
                ),
            )

        raise UnsupportedRouteError(
            route_type=route_type,
            message=(
                "The `/query` route is currently wired for policy/process Q&A, "
                "incident-summary retrieval, and inventory lookup only. "
                f"The request was classified as `{route_type}`."
            ),
        )

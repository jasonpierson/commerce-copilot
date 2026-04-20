from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from uuid import uuid4

from app.api.approval_service import ApprovalNotFoundError, ApprovalService
from app.api.incident_service import IncidentService
from app.api.inventory_service import InventoryService
from app.api.schemas import (
    ApiLink,
    ApprovalAuditEvent,
    ApprovalRecord,
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

        if self._looks_like_approval_lookup(request.message):
            return "structured_lookup"

        if any(token in query for token in ("inventory", "in stock", "sku", "stock level")):
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

    def _extract_approval_id(self, message: str) -> str | None:
        patterns = [
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            r"\b(apr[_-][a-z0-9_-]+)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _looks_like_approval_lookup(self, message: str) -> bool:
        query = message.lower()
        if "approval" not in query:
            return False
        if "approve escalation" in query:
            return False
        return self._extract_approval_id(message) is not None or any(
            token in query
            for token in (
                "approval status",
                "status of approval",
                "show approval",
                "check approval",
                "lookup approval",
                "who approved",
                "who rejected",
                "who decided",
            )
        )

    def _is_approval_history_lookup(self, message: str) -> bool:
        query = message.lower()
        return any(
            token in query
            for token in (
                "when was",
                "approval history",
                "audit",
                "timeline",
                "when did",
                "what happened to approval",
            )
        )

    def _is_approval_actor_lookup(self, message: str) -> bool:
        query = message.lower()
        return any(
            token in query
            for token in (
                "who approved",
                "who rejected",
                "who decided",
                "who reviewed approval",
            )
        )

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

    def _build_approval_links(self, approval: ApprovalRecord | None) -> list[ApiLink]:
        if not approval:
            return []

        links = [
            ApiLink(
                rel="approval_status",
                href=f"/api/v1/approvals/{approval.approval_id}",
                method="GET",
                description="View the structured approval record and current decision state.",
            )
        ]
        incident_code = approval.payload.get("incident_code")
        if incident_code:
            links.append(
                ApiLink(
                    rel="incident_detail",
                    href=f"/api/v1/incidents/{incident_code}",
                    method="GET",
                    description="View the incident tied to this approval request.",
                )
            )
        return links

    def _build_approval_audit_links(self, approval: ApprovalRecord | None) -> list[ApiLink]:
        if not approval:
            return []
        return [
            ApiLink(
                rel="approval_audit",
                href=f"/api/v1/approvals/{approval.approval_id}/audit",
                method="GET",
                description="View the audit trail for this approval request.",
            )
        ]

    def _dedupe_links(self, links: list[ApiLink]) -> list[ApiLink]:
        deduped: list[ApiLink] = []
        seen: set[tuple[str, str, str]] = set()
        for link in links:
            key = (link.rel, link.href, link.method)
            if key in seen:
                continue
            deduped.append(link)
            seen.add(key)
        return deduped

    def _build_incident_approval_summary(self, approval: ApprovalRecord | None) -> str | None:
        if not approval:
            return None
        approver_name = approval.approver.full_name if approval.approver else "an approver"
        if approval.status == "pending":
            return (
                f"Linked approval {approval.approval_id} is still pending with {approver_name} as the current approver."
            )
        decided_at = approval.decided_at.isoformat() if approval.decided_at else "an earlier time"
        return (
            f"Linked approval {approval.approval_id} is {approval.status}; {approver_name} recorded the decision at {decided_at}."
        )

    def _build_approval_history_answer(
        self,
        message: str,
        approval: ApprovalRecord,
        audit_events: list[ApprovalAuditEvent],
    ) -> str:
        query = message.lower()
        if not audit_events:
            return (
                f"Approval {approval.approval_id} is currently {approval.status}, but I couldn't find audit events yet."
            )

        if "when was" in query or "when did" in query:
            if "approve" in query and approval.decided_at and approval.status == "approved":
                return f"Approval {approval.approval_id} was approved at {approval.decided_at.isoformat()}."
            if "reject" in query and approval.decided_at and approval.status == "rejected":
                return f"Approval {approval.approval_id} was rejected at {approval.decided_at.isoformat()}."
            requested_event = next(
                (event for event in audit_events if event.event_type == "approval_requested"),
                audit_events[0],
            )
            return f"Approval {approval.approval_id} was requested at {requested_event.occurred_at.isoformat()}."

        history_lines = [
            f"{event.occurred_at.isoformat()} - {event.event_type.replace('_', ' ')}"
            + (
                f" by {event.actor.full_name}"
                if event.actor
                else ""
            )
            for event in audit_events
        ]
        return (
            f"Approval {approval.approval_id} history:\n\n"
            + "\n".join(history_lines)
        )

    def _build_approval_answer(self, message: str, approval: ApprovalRecord) -> str:
        if self._is_approval_actor_lookup(message):
            approver_name = approval.approver.full_name if approval.approver else "an approver"
            if approval.status == "approved":
                return (
                    f"{approver_name} approved approval {approval.approval_id}."
                    + (
                        f" Notes: {approval.decision_notes}"
                        if approval.decision_notes
                        else ""
                    )
                )
            if approval.status == "rejected":
                return (
                    f"{approver_name} rejected approval {approval.approval_id}."
                    + (
                        f" Notes: {approval.decision_notes}"
                        if approval.decision_notes
                        else ""
                    )
                )
            return (
                f"Approval {approval.approval_id} is still pending, so no one has approved or rejected it yet."
            )

        request_type = approval.request_type.replace("_", " ")
        summary = (
            f"Approval {approval.approval_id} is currently {approval.status} for "
            f"{request_type} on {approval.target_type} {approval.target_id}."
        )

        details: list[str] = []
        incident_code = approval.payload.get("incident_code")
        if incident_code:
            details.append(f"Incident: {incident_code}")
        proposed_priority = approval.payload.get("proposed_priority")
        if proposed_priority:
            details.append(f"Priority: {proposed_priority}")
        if approval.requester:
            details.append(f"Requested by: {approval.requester.full_name}")
        if approval.approver:
            details.append(f"Approver: {approval.approver.full_name}")
        if approval.decision_notes:
            details.append(f"Decision notes: {approval.decision_notes}")
        if approval.next_step:
            details.append(f"Next step: {approval.next_step}")

        if not details:
            return summary

        return f"{summary}\n\n" + "\n".join(details)

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

    def _build_escalation_next_step(
        self,
        incident: IncidentRecord | None,
        approval_suggestion: ApprovalSuggestion | None,
    ) -> str | None:
        if approval_suggestion:
            return (
                f"Create a {approval_suggestion.proposed_priority}-priority approval request "
                f"if {approval_suggestion.incident_code} needs management attention."
            )

        if incident and incident.status.lower() == "resolved":
            return "Document the closure rationale and only reopen escalation if customer impact returns."

        if incident:
            return "Review the escalation criteria against the latest timeline update before opening an approval."

        return None

    def _build_escalation_answer(
        self,
        retrieval_results: list[RetrievalResult],
        *,
        incident: IncidentRecord | None = None,
        approval_suggestion: ApprovalSuggestion | None = None,
    ) -> str:
        guidance = self._build_answer(retrieval_results)

        if not incident:
            return guidance

        status_summary = f"{incident.incident_code} is {incident.status} at {incident.severity.upper()} severity"
        if incident.customer_impact:
            status_summary += f" with customer impact noted as: {incident.customer_impact}"
        else:
            status_summary += "."

        if approval_suggestion:
            return (
                f"{status_summary}\n\n"
                f"Recommended escalation posture: {approval_suggestion.reason}\n\n"
                f"Relevant policy guidance: {guidance}"
            ).strip()

        return (
            f"{status_summary}\n\n"
            "Escalation is not automatically recommended from the structured incident data yet. "
            f"Use this policy context to decide the next step:\n\n{guidance}"
        ).strip()

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
            linked_approval: ApprovalRecord | None = None
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
            if incident:
                try:
                    linked_approval = ApprovalService.from_env().get_latest_incident_approval(incident.incident_id)
                except Exception:
                    linked_approval = None
                if linked_approval:
                    tools_used.append("get_latest_incident_approval")
            answer = self._build_incident_answer(
                retrieval_results,
                incident=incident,
                timeline=timeline,
            )
            if linked_approval:
                answer = f"{answer}\n\nApproval state: {self._build_incident_approval_summary(linked_approval)}"
            recommended_next_step = self._build_incident_next_step(incident, timeline)
            approval_suggestion = self._build_approval_suggestion(incident)
            links = self._build_incident_links(incident)
            if linked_approval:
                links.extend(self._build_approval_links(linked_approval))
                links.extend(self._build_approval_audit_links(linked_approval))
            if approval_suggestion:
                links.append(approval_suggestion.create_request)
            links = self._dedupe_links(links)

            return QueryResponse(
                request_id=request_id,
                route_type="incident_summary",
                data=QueryResponseData(
                    answer=answer,
                    citations=citations,
                    approval=linked_approval,
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
                    approval_involved=bool(linked_approval or approval_suggestion),
                ),
            )

        if route_type == "structured_lookup":
            approval_id = self._extract_approval_id(request.message)
            if self._looks_like_approval_lookup(request.message):
                if not approval_id:
                    return QueryResponse(
                        request_id=request_id,
                        route_type="structured_lookup",
                        data=QueryResponseData(
                            answer=(
                                "I can look up approval status through `/api/v1/query`, but I need the approval ID "
                                "from `/api/v1/approvals/{approval_id}`."
                            ),
                            citations=[],
                        ),
                        meta=QueryResponseMeta(
                            citations_included=False,
                            tools_used=["get_approval_status"],
                            approval_involved=True,
                        ),
                    )

                try:
                    approval_service = ApprovalService.from_env()
                    approval = approval_service.get_approval_status(approval_id)
                except ApprovalNotFoundError:
                    return QueryResponse(
                        request_id=request_id,
                        route_type="structured_lookup",
                        data=QueryResponseData(
                            answer=f"I couldn't find approval {approval_id} in the structured approval data.",
                            citations=[],
                        ),
                        meta=QueryResponseMeta(
                            citations_included=False,
                            tools_used=["get_approval_status"],
                            approval_involved=True,
                        ),
                    )

                audit_events: list[ApprovalAuditEvent] = []
                tools_used = ["get_approval_status"]
                if self._is_approval_history_lookup(request.message):
                    audit_events = approval_service.get_approval_audit(approval_id)
                    tools_used.append("get_approval_audit")

                return QueryResponse(
                    request_id=request_id,
                    route_type="structured_lookup",
                    data=QueryResponseData(
                        answer=(
                            self._build_approval_history_answer(request.message, approval, audit_events)
                            if self._is_approval_history_lookup(request.message)
                            else self._build_approval_answer(request.message, approval)
                        ),
                        citations=[],
                        approval=approval,
                        approval_audit=audit_events,
                        links=self._dedupe_links(
                            self._build_approval_links(approval) + self._build_approval_audit_links(approval)
                        ),
                    ),
                    meta=QueryResponseMeta(
                        citations_included=False,
                        tools_used=tools_used,
                        approval_involved=True,
                    ),
                )

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

        if route_type == "escalation_guidance":
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
                        route_type="escalation_guidance",
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
                    route_type="escalation_guidance",
                    request_id=request_id,
                )
            except RetrievalError:
                raise

            citations = self._build_citations(retrieval_results)
            approval_suggestion = self._build_approval_suggestion(incident)
            links = self._build_incident_links(incident)
            if approval_suggestion:
                links.append(approval_suggestion.create_request)
            links = self._dedupe_links(links)

            return QueryResponse(
                request_id=request_id,
                route_type="escalation_guidance",
                data=QueryResponseData(
                    answer=self._build_escalation_answer(
                        retrieval_results,
                        incident=incident,
                        approval_suggestion=approval_suggestion,
                    ),
                    citations=citations,
                    incident=incident,
                    incident_timeline=timeline,
                    customer_impact=incident.customer_impact if incident else None,
                    recommended_next_step=self._build_escalation_next_step(incident, approval_suggestion),
                    links=links,
                    approval_suggestion=approval_suggestion,
                ),
                meta=QueryResponseMeta(
                    citations_included=bool(citations),
                    tools_used=tools_used,
                    approval_involved=bool(approval_suggestion),
                ),
            )

        raise UnsupportedRouteError(
            route_type=route_type,
            message=(
                "The `/query` route is currently wired for policy/process Q&A, "
                "incident summaries, escalation guidance, and inventory lookup only. "
                f"The request was classified as `{route_type}`."
            ),
        )

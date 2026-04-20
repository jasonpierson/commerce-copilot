from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import uuid4

from app.api.schemas import Citation, QueryRequest, QueryResponse, QueryResponseData, QueryResponseMeta
from app.api.inventory_service import InventoryService
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

    def _build_incident_answer(self, retrieval_results: list[RetrievalResult]) -> str:
        if not retrieval_results:
            return (
                "I couldn't find incident-supporting runbooks or playbooks for that request."
            )

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
            try:
                retrieval_results = self._retrieve_context(
                    request,
                    route_type="incident_summary",
                    request_id=request_id,
                )
            except RetrievalError:
                raise

            citations = self._build_citations(retrieval_results)
            answer = self._build_incident_answer(retrieval_results)

            return QueryResponse(
                request_id=request_id,
                route_type="incident_summary",
                data=QueryResponseData(answer=answer, citations=citations),
                meta=QueryResponseMeta(
                    citations_included=bool(citations),
                    tools_used=[],
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

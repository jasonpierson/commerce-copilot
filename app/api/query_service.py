from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import re
from typing import Callable
from urllib.parse import urlencode
from uuid import uuid4

from app.api.audit import ApiAuditSink
from app.api.approval_service import ApprovalNotFoundError, ApprovalService
from app.api.incident_service import IncidentService
from app.api.inventory_service import InventoryService
from app.api.schemas import (
    ApiLink,
    ApprovalAuditEvent,
    ApprovalDashboardBucket,
    ApprovalDashboardMetrics,
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


@dataclass(frozen=True, slots=True)
class RouteRule:
    route_type: str
    matcher: Callable[[QueryRequest], bool]


@dataclass(slots=True)
class QueryService:
    audit_sink: ApiAuditSink = field(default_factory=lambda: ApiAuditSink(filename="query_events.jsonl"))

    def _route_rules(self) -> tuple[RouteRule, ...]:
        return (
            RouteRule("structured_lookup", self._is_structured_analytics_lookup),
            RouteRule("structured_lookup", self._is_approval_dashboard_route),
            RouteRule("structured_lookup", self._is_approval_list_route),
            RouteRule("structured_lookup", self._is_approval_detail_route),
            RouteRule("incident_summary", self._is_incident_escalation_status_route),
            RouteRule("structured_lookup", self._is_inventory_route),
            RouteRule("escalation_guidance", self._is_escalation_guidance_route),
            RouteRule("incident_summary", self._is_incident_summary_route),
        )

    def _classify_route(self, request: QueryRequest) -> str:
        if request.route_type_override:
            return request.route_type_override

        for rule in self._route_rules():
            if rule.matcher(request):
                return rule.route_type

        return "policy_qa"

    def _is_structured_analytics_lookup(self, request: QueryRequest) -> bool:
        message = request.message
        return any(
            matcher(message)
            for matcher in (
                self._is_pending_owner_lookup,
                self._is_oldest_pending_item_lookup,
                self._is_oldest_pending_requester_lookup,
                self._is_oldest_pending_incident_lookup,
                self._is_aged_pending_incident_lookup,
                self._is_approver_bottleneck_lookup,
                self._is_requester_load_lookup,
                self._is_escalation_load_lookup,
            )
        )

    def _is_approval_dashboard_route(self, request: QueryRequest) -> bool:
        return self._is_approval_dashboard_lookup(request.message)

    def _is_approval_list_route(self, request: QueryRequest) -> bool:
        return self._is_approval_list_lookup(request.message)

    def _is_approval_detail_route(self, request: QueryRequest) -> bool:
        return self._looks_like_approval_lookup(request.message)

    def _is_incident_escalation_status_route(self, request: QueryRequest) -> bool:
        return bool(
            self._extract_incident_code(request.message)
            and self._is_incident_escalation_status_lookup(request.message)
        )

    def _is_inventory_route(self, request: QueryRequest) -> bool:
        query = request.message.lower()
        return any(token in query for token in ("inventory", "in stock", "sku", "stock level"))

    def _is_escalation_guidance_route(self, request: QueryRequest) -> bool:
        query = request.message.lower()
        return any(
            token in query
            for token in ("escalate", "escalation", "high priority", "medium priority", "approve escalation")
        )

    def _is_incident_summary_route(self, request: QueryRequest) -> bool:
        query = request.message.lower()
        return any(token in query for token in ("incident", "inc-", "customer impact", "checkout problem", "outage"))

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

    def _is_approval_list_lookup(self, message: str) -> bool:
        query = message.lower()
        if "approval" not in query:
            return False
        if self._is_approval_dashboard_lookup(message):
            return False
        return any(
            token in query
            for token in (
                "all pending approvals",
                "pending approvals",
                "all approved approvals",
                "approved approvals",
                "all rejected approvals",
                "rejected approvals",
                "list approvals",
                "show approvals",
                "browse approvals",
                "approvals for inc-",
                "approvals for incident",
            )
        )

    def _is_approval_dashboard_lookup(self, message: str) -> bool:
        query = message.lower()
        if "approval" not in query:
            return False
        return any(
            token in query
            for token in (
                "approval dashboard",
                "approvals dashboard",
                "dashboard for approvals",
                "approval work dashboard",
            )
        )

    def _is_pending_owner_lookup(self, message: str) -> bool:
        query = message.lower()
        return "pending approval" in query and any(
            token in query
            for token in (
                "who is holding",
                "who's holding",
                "who owns",
                "who has",
            )
        )

    def _is_oldest_pending_item_lookup(self, message: str) -> bool:
        query = message.lower()
        if "pending" not in query or "approv" not in query:
            return False
        return any(
            token in query
            for token in (
                "oldest pending item",
                "oldest pending approval",
                "oldest pending approv",
                "been waiting the longest",
                "waiting longest",
            )
        )

    def _is_oldest_pending_requester_lookup(self, message: str) -> bool:
        query = message.lower()
        return "requester" in query and self._is_oldest_pending_item_lookup(message)

    def _is_oldest_pending_incident_lookup(self, message: str) -> bool:
        query = message.lower()
        if "pending" not in query or "approv" not in query:
            return False
        return "incident" in query and any(
            token in query
            for token in (
                "oldest pending approval",
                "oldest pending item",
                "waiting the longest",
                "waiting longest",
            )
        )

    def _is_aged_pending_incident_lookup(self, message: str) -> bool:
        query = message.lower()
        return (
            "incident" in query
            and "pending approval" in query
            and self._extract_min_pending_age_minutes(message) is not None
        )

    def _is_approver_bottleneck_lookup(self, message: str) -> bool:
        query = message.lower()
        if "approval" not in query and "approver" not in query:
            return False
        return any(
            token in query
            for token in (
                "which approver is the bottleneck",
                "who is the bottleneck",
                "who's the bottleneck",
                "approver bottleneck",
                "holding the most pending approvals",
                "owns the most pending approvals",
            )
        )

    def _is_requester_load_lookup(self, message: str) -> bool:
        query = message.lower()
        return "approval load" in query and any(
            token in query
            for token in (
                "which requester",
                "who is creating",
                "who's creating",
                "most approval load",
                "most pending approval load",
            )
        )

    def _is_escalation_load_lookup(self, message: str) -> bool:
        query = message.lower()
        return "pending approval" in query and any(
            token in query
            for token in (
                "approval pressure",
                "most pending",
                "highest pending",
                "which incidents have",
                "escalation load",
            )
        )

    def _extract_approval_status_filter(self, message: str) -> str | None:
        query = message.lower()
        for status in ("pending", "approved", "rejected"):
            if status in query:
                return status
        return None

    def _extract_min_pending_age_minutes(self, message: str) -> int | None:
        patterns = [
            r"older than (?P<minutes>\d+)\s*(?:minute|minutes|min)\b",
            r"over (?P<minutes>\d+)\s*(?:minute|minutes|min)\b",
            r"at least (?P<minutes>\d+)\s*(?:minute|minutes|min)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return int(match.group("minutes"))
        return None

    def _extract_requester_filter(self, message: str) -> str | None:
        patterns = [
            r"requested by (?P<requester>[a-z0-9 .@_-]+)",
            r"for requester (?P<requester>[a-z0-9 .@_-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group("requester").strip(" ?.")
        return None

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

    def _is_approval_reason_lookup(self, message: str) -> bool:
        query = message.lower()
        if "approval" not in query:
            return False
        return any(
            token in query
            for token in (
                "why was",
                "why did",
                "reason for rejection",
                "why rejected",
                "why was this rejected",
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

    def _is_incident_escalation_status_lookup(self, message: str) -> bool:
        query = message.lower()
        return any(
            token in query
            for token in (
                "already been escalated",
                "already escalated",
                "has this incident been escalated",
                "was this incident escalated",
                "is there already an approval",
                "is there an approval",
            )
        )

    def _is_incident_approval_history_lookup(self, message: str) -> bool:
        query = message.lower()
        return "approval" in query and any(
            token in query
            for token in (
                "approval history",
                "approval timeline",
                "approval audit",
                "show me the approval history",
                "what is the approval history",
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

    def _build_incident_escalation_status_answer(
        self,
        incident: IncidentRecord | None,
        linked_approval: ApprovalRecord | None,
    ) -> str:
        if not incident:
            return "I couldn't determine escalation status because I couldn't load the incident record."

        if not linked_approval:
            return (
                f"No linked escalation approval has been recorded for {incident.incident_code} yet."
            )

        approver_name = linked_approval.approver.full_name if linked_approval.approver else "the assigned approver"
        requested_at = linked_approval.requested_at.isoformat()
        base = (
            f"Yes. {incident.incident_code} already has approval {linked_approval.approval_id}, "
            f"requested at {requested_at}."
        )
        if linked_approval.status == "pending":
            return f"{base} It is still pending with {approver_name}."
        decided_at = linked_approval.decided_at.isoformat() if linked_approval.decided_at else "a recorded time"
        return f"{base} It is {linked_approval.status}, and {approver_name} recorded the decision at {decided_at}."

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

    def _build_approval_reason_answer(
        self,
        approval: ApprovalRecord,
        audit_events: list[ApprovalAuditEvent],
    ) -> str:
        if approval.status == "pending":
            return (
                f"Approval {approval.approval_id} is still pending, so there is no rejection reason yet."
            )

        if approval.status == "approved":
            return (
                f"Approval {approval.approval_id} was approved, not rejected."
                + (
                    f" Decision notes: {approval.decision_notes}"
                    if approval.decision_notes
                    else ""
                )
            )

        decided_event = next(
            (event for event in reversed(audit_events) if event.event_type == "approval_decided"),
            None,
        )
        decision_notes = approval.decision_notes
        if not decision_notes and decided_event:
            decision_notes = decided_event.payload.get("decision_notes")

        if decision_notes:
            return (
                f"Approval {approval.approval_id} was rejected because: {decision_notes}"
            )

        return (
            f"Approval {approval.approval_id} is rejected, but no decision notes were recorded in the audit trail."
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

    def _build_approval_list_answer(
        self,
        approvals: list[ApprovalRecord],
        *,
        status_filter: str | None,
        incident_code: str | None,
        requester: str | None = None,
        total_count: int | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not approvals:
            if status_filter:
                return f"I couldn't find any {status_filter} approvals{scope} right now."
            return f"I couldn't find any approval work items{scope} right now."

        label = f"{status_filter} approvals" if status_filter else "approval work items"
        count = total_count if total_count is not None else len(approvals)
        lines = [f"I found {count} {label}{scope}:"]
        for approval in approvals[:5]:
            incident_code = approval.payload.get("incident_code")
            requested_at = approval.requested_at.isoformat()
            summary = (
                f"- {approval.approval_id} — {approval.status} {approval.request_type.replace('_', ' ')} "
                f"requested at {requested_at}"
            )
            if incident_code:
                summary += f" for {incident_code}"
            lines.append(summary)
        return "\n".join(lines)

    def _build_approval_dashboard_answer(
        self,
        buckets: list[ApprovalDashboardBucket],
        metrics: ApprovalDashboardMetrics | None = None,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        if not buckets or all(bucket.count == 0 for bucket in buckets):
            return "I couldn't find any approval work items for the dashboard right now."

        total = sum(bucket.count for bucket in buckets)
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" ({', '.join(scope_bits)})" if scope_bits else ""
        lines = [f"Approval dashboard{scope}: {total} total work item(s)."]
        if metrics:
            metrics_line = f"Pending: {metrics.pending_count}"
            metrics_line += (
                f"; created in last 24h: {metrics.approvals_created_last_24h}"
                f"; decided in last 24h: {metrics.approvals_decided_last_24h}"
                f"; created in last 7d: {metrics.approvals_created_last_7d}"
                f"; decided in last 7d: {metrics.approvals_decided_last_7d}"
            )
            if metrics.oldest_pending_age_minutes is not None:
                metrics_line += f"; oldest pending age: {metrics.oldest_pending_age_minutes} minute(s)"
            if metrics.daily_trends_7d:
                trend_summary = ", ".join(
                    f"{bucket.bucket_date.isoformat()}: +{bucket.approvals_created}/-{bucket.approvals_decided}"
                    for bucket in metrics.daily_trends_7d
                )
                metrics_line += f"; 7d daily trend: {trend_summary}"
            if metrics.pending_by_priority:
                priority_summary = ", ".join(
                    f"{priority}={count}" for priority, count in metrics.pending_by_priority.items()
                )
                metrics_line += f"; pending by priority: {priority_summary}"
            lines.append(metrics_line)
            if metrics.daily_trends_7d:
                lines.append("7-day daily trend:")
                for bucket in metrics.daily_trends_7d:
                    lines.append(
                        f"- {bucket.bucket_date.isoformat()}: created {bucket.approvals_created}, decided {bucket.approvals_decided}"
                    )
        for bucket in buckets:
            preview = ", ".join(approval.approval_id for approval in bucket.approvals[:3])
            line = f"- {bucket.status}: {bucket.count}"
            if preview:
                line += f" ({preview})"
            lines.append(line)
        return "\n".join(lines)

    def _build_dashboard_summary_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        top_risk_details: list[str],
        incident_code: str | None = None,
        requester: str | None = None,
        min_pending_age_minutes: int | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        if min_pending_age_minutes is not None:
            scope_bits.append(f"min_age={min_pending_age_minutes}m")
        scope = f" ({', '.join(scope_bits)})" if scope_bits else ""
        lines = [
            f"Approval dashboard summary{scope}: {metrics.pending_count} pending item(s), "
            f"{metrics.approvals_created_last_24h} created in the last 24h, "
            f"{metrics.approvals_decided_last_24h} decided in the last 24h."
        ]
        if top_risk_details:
            lines.append("Top risks:")
            for detail in top_risk_details:
                lines.append(f"- {detail}")
        if metrics.daily_trends_7d:
            lines.append("7-day daily trend:")
            for bucket in metrics.daily_trends_7d:
                lines.append(
                    f"- {bucket.bucket_date.isoformat()}: created {bucket.approvals_created}, decided {bucket.approvals_decided}"
                )
        return "\n".join(lines)

    def _build_pending_owner_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.pending_by_owner:
            return f"I couldn't find any pending approvals{scope} right now."

        lines = [f"Pending approvals{scope} are currently held by:"]
        for owner in metrics.pending_by_owner:
            role = f" ({owner.approver_role})" if owner.approver_role else ""
            lines.append(f"- {owner.approver_name}{role}: {owner.pending_count}")
        return "\n".join(lines)

    def _build_oldest_pending_item_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.oldest_pending_item:
            return f"I couldn't find an oldest pending approval item{scope} right now."

        item = metrics.oldest_pending_item
        role = f" ({item.approver_role})" if item.approver_role else ""
        incident = f" for {item.incident_code}" if item.incident_code else ""
        return (
            f"The oldest pending approval item{scope} is currently with "
            f"{item.approver_name}{role}: {item.approval_id}{incident}, pending for "
            f"{item.pending_age_minutes} minute(s)."
        )

    def _build_oldest_pending_requester_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.oldest_pending_item:
            return f"I couldn't find a requester with the oldest pending approval{scope} right now."

        item = metrics.oldest_pending_item
        requester_role = f" ({item.requester_role})" if item.requester_role else ""
        incident = f" for {item.incident_code}" if item.incident_code else ""
        requester_name = item.requester_name or "Unknown requester"
        return (
            f"The requester with the oldest pending approval{scope} is {requester_name}{requester_role}. "
            f"Approval {item.approval_id}{incident} has been pending for {item.pending_age_minutes} minute(s)."
        )

    def _build_oldest_pending_incident_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.oldest_pending_item:
            return f"I couldn't find an incident with the oldest pending approval{scope} right now."

        item = metrics.oldest_pending_item
        if not item.incident_code:
            return f"I found the oldest pending approval item{scope}, but it is not linked to an incident."
        return (
            f"The incident with the oldest pending approval{scope} is {item.incident_code}. "
            f"Approval {item.approval_id} has been pending with {item.approver_name}"
            f"{f' ({item.approver_role})' if item.approver_role else ''} for {item.pending_age_minutes} minute(s)."
        )

    def _build_aged_pending_incidents_answer(
        self,
        incidents: list,
        *,
        min_pending_age_minutes: int,
        requester: str | None = None,
    ) -> str:
        scope = f" for requester={requester}" if requester else ""
        if not incidents:
            return (
                f"I couldn't find any incidents with pending approvals older than "
                f"{min_pending_age_minutes} minute(s){scope}."
            )
        lines = [
            f"I found {len(incidents)} incident(s) with pending approvals older than "
            f"{min_pending_age_minutes} minute(s){scope}:"
        ]
        for incident in incidents:
            lines.append(
                f"- {incident.incident_code}: {incident.pending_count} pending approval(s), "
                f"oldest age {incident.oldest_pending_age_minutes} minute(s)"
            )
        return "\n".join(lines)

    def _build_approver_bottleneck_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.pending_by_owner:
            return f"I couldn't find an approver bottleneck{scope} right now."

        top_owner = metrics.pending_by_owner[0]
        top_role = f" ({top_owner.approver_role})" if top_owner.approver_role else ""
        lines = [
            f"The current approval bottleneck is {top_owner.approver_name}{top_role} with {top_owner.pending_count} pending approval(s){scope}."
        ]
        if len(metrics.pending_by_owner) > 1:
            lines.append("Current pending approval load by approver:")
            for owner in metrics.pending_by_owner:
                role = f" ({owner.approver_role})" if owner.approver_role else ""
                lines.append(f"- {owner.approver_name}{role}: {owner.pending_count}")
        return "\n".join(lines)

    def _build_requester_load_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.pending_by_requester:
            return f"I couldn't find any requester-driven approval load{scope} right now."

        top_requester = metrics.pending_by_requester[0]
        lines = [
            f"Approval load is currently highest for requester {top_requester.requester_name} with {top_requester.pending_count} pending approval(s){scope}."
        ]
        if len(metrics.pending_by_requester) > 1:
            lines.append("Current pending approval load by requester:")
            for requester_metric in metrics.pending_by_requester:
                role = f" ({requester_metric.requester_role})" if requester_metric.requester_role else ""
                lines.append(
                    f"- {requester_metric.requester_name}{role}: {requester_metric.pending_count}"
                )
        return "\n".join(lines)

    def _build_escalation_load_answer(
        self,
        metrics: ApprovalDashboardMetrics,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> str:
        scope_bits: list[str] = []
        if incident_code:
            scope_bits.append(incident_code)
        if requester:
            scope_bits.append(f"requester={requester}")
        scope = f" for {', '.join(scope_bits)}" if scope_bits else ""
        if not metrics.pending_by_incident:
            return f"I couldn't find any pending approval pressure{scope} right now."

        top_incident = metrics.pending_by_incident[0]
        lines = [
            f"Pending approval pressure is currently highest on {top_incident.incident_code} with {top_incident.pending_count} pending approval(s){scope}."
        ]
        if len(metrics.pending_by_incident) > 1:
            lines.append("Current pending approval pressure by incident:")
            for incident_metric in metrics.pending_by_incident:
                lines.append(f"- {incident_metric.incident_code}: {incident_metric.pending_count}")
        return "\n".join(lines)

    def _build_query_string(
        self,
        *,
        status: str | None = None,
        incident_code: str | None = None,
        requester: str | None = None,
        min_pending_age_minutes: int | None = None,
    ) -> str:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if incident_code:
            params["incident_code"] = incident_code
        if requester:
            params["requester"] = requester
        if min_pending_age_minutes is not None:
            params["min_pending_age_minutes"] = str(min_pending_age_minutes)
        if not params:
            return ""
        return "?" + urlencode(params)

    def _build_incident_approval_history_answer(
        self,
        incident: IncidentRecord,
        approval: ApprovalRecord | None,
        audit_events: list[ApprovalAuditEvent],
    ) -> str:
        if not approval:
            return (
                f"{incident.incident_code} does not have a linked approval history yet."
            )

        if not audit_events:
            return (
                f"{incident.incident_code} is linked to approval {approval.approval_id}, "
                "but I couldn't find audit events for it yet."
            )

        history_lines = [
            f"{event.occurred_at.isoformat()} - {event.event_type.replace('_', ' ')}"
            + (f" by {event.actor.full_name}" if event.actor else "")
            + (
                f" ({event.payload.get('decision_notes')})"
                if event.payload.get("decision_notes")
                else ""
            )
            for event in audit_events
        ]
        return (
            f"Approval history for {incident.incident_code} is recorded under approval {approval.approval_id}:\n\n"
            + "\n".join(history_lines)
        )

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

    def _collect_approval_ids(self, response: QueryResponse) -> list[str]:
        approval_ids: list[str] = []
        if response.data.approval:
            approval_ids.append(response.data.approval.approval_id)
        approval_ids.extend(approval.approval_id for approval in response.data.approvals)
        deduped: list[str] = []
        for approval_id in approval_ids:
            if approval_id not in deduped:
                deduped.append(approval_id)
        return deduped

    def _log_query_response(self, request: QueryRequest, response: QueryResponse) -> None:
        self.audit_sink.log_event(
            event_type="query_handled",
            request_id=response.request_id,
            route_type=response.route_type,
            user_id=request.user_id,
            user_role=request.user_role,
            tools_used=response.meta.tools_used,
            doc_keys=[citation.doc_key for citation in response.data.citations],
            approval_ids=self._collect_approval_ids(response),
            incident_code=response.data.incident.incident_code if response.data.incident else None,
        )

    def _handle_policy_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
        retrieval_results = self._retrieve_context(
            request,
            route_type="policy_qa",
            request_id=request_id,
        )
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

    def _handle_incident_summary_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
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
                    update={"message": self._build_incident_support_query(request.message, incident)}
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

        retrieval_results = self._retrieve_context(
            retrieval_request,
            route_type="incident_summary",
            request_id=request_id,
        )
        citations = self._build_citations(retrieval_results)
        approval_audit: list[ApprovalAuditEvent] = []
        if incident:
            try:
                approval_service = ApprovalService.from_env()
                linked_approval = approval_service.get_latest_incident_approval(incident.incident_id)
                if linked_approval and self._is_incident_approval_history_lookup(request.message):
                    approval_audit = approval_service.get_approval_audit(linked_approval.approval_id)
                    tools_used.append("get_approval_audit")
            except Exception:
                linked_approval = None
                approval_audit = []
            if linked_approval:
                tools_used.append("get_latest_incident_approval")
        answer = self._build_incident_answer(retrieval_results, incident=incident, timeline=timeline)
        if self._is_incident_escalation_status_lookup(request.message):
            answer = self._build_incident_escalation_status_answer(incident, linked_approval)
        elif incident and self._is_incident_approval_history_lookup(request.message):
            answer = self._build_incident_approval_history_answer(incident, linked_approval, approval_audit)
        elif linked_approval:
            answer = f"{answer}\n\nApproval state: {self._build_incident_approval_summary(linked_approval)}"
        recommended_next_step = self._build_incident_next_step(incident, timeline)
        approval_suggestion = self._build_approval_suggestion(incident)
        links = self._build_incident_links(incident)
        if linked_approval:
            links.extend(self._build_approval_links(linked_approval))
            links.extend(self._build_approval_audit_links(linked_approval))
        if approval_suggestion:
            links.append(approval_suggestion.create_request)
        return QueryResponse(
            request_id=request_id,
            route_type="incident_summary",
            data=QueryResponseData(
                answer=answer,
                citations=citations,
                approval=linked_approval,
                approval_audit=approval_audit,
                incident=incident,
                incident_timeline=timeline,
                customer_impact=incident.customer_impact if incident else None,
                recommended_next_step=recommended_next_step,
                links=self._dedupe_links(links),
                approval_suggestion=approval_suggestion,
            ),
            meta=QueryResponseMeta(
                citations_included=bool(citations),
                tools_used=tools_used,
                approval_involved=bool(linked_approval or approval_suggestion),
            ),
        )

    def _handle_dashboard_structured_lookup(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
        approval_service = ApprovalService.from_env()
        incident_code_filter = self._extract_incident_code(request.message)
        requester_filter = self._extract_requester_filter(request.message)
        min_pending_age_minutes = self._extract_min_pending_age_minutes(request.message)
        buckets, metrics = approval_service.get_approval_dashboard(
            incident_code=incident_code_filter,
            requester=requester_filter,
            page_size_per_bucket=5,
        )
        total_count = sum(bucket.count for bucket in buckets)
        dashboard_href = "/api/v1/approvals/dashboard" + self._build_query_string(
            incident_code=incident_code_filter,
            requester=requester_filter,
        )
        summary_href = "/api/v1/approvals/dashboard/summary" + self._build_query_string(
            incident_code=incident_code_filter,
            requester=requester_filter,
            min_pending_age_minutes=min_pending_age_minutes,
        )
        dashboard_links = [
            ApiLink(
                rel="approval_dashboard",
                href=dashboard_href,
                method="GET",
                description="Browse approval work grouped by status.",
            ),
            ApiLink(
                rel="approval_list",
                href=dashboard_href.replace("/approvals/dashboard", "/approvals"),
                method="GET",
                description="Browse the full approval work queue.",
            ),
            ApiLink(
                rel="approval_dashboard_summary",
                href=summary_href,
                method="GET",
                description="View headline approval metrics and top risks first.",
            ),
        ]
        if self._is_aged_pending_incident_lookup(request.message):
            aged_incidents = approval_service.list_incidents_with_pending_approvals_older_than(
                min_pending_age_minutes=min_pending_age_minutes or 0,
                requester=requester_filter,
            )
            answer = self._build_aged_pending_incidents_answer(
                aged_incidents,
                min_pending_age_minutes=min_pending_age_minutes or 0,
                requester=requester_filter,
            )
        else:
            answer_builders: tuple[tuple[Callable[[str], bool], Callable[..., str]], ...] = (
                (self._is_pending_owner_lookup, self._build_pending_owner_answer),
                (self._is_oldest_pending_requester_lookup, self._build_oldest_pending_requester_answer),
                (self._is_oldest_pending_incident_lookup, self._build_oldest_pending_incident_answer),
                (self._is_oldest_pending_item_lookup, self._build_oldest_pending_item_answer),
                (self._is_approver_bottleneck_lookup, self._build_approver_bottleneck_answer),
                (self._is_requester_load_lookup, self._build_requester_load_answer),
                (self._is_escalation_load_lookup, self._build_escalation_load_answer),
            )
            answer = ""
            for matcher, builder in answer_builders:
                if matcher(request.message):
                    answer = builder(
                        metrics,
                        incident_code=incident_code_filter,
                        requester=requester_filter,
                    )
                    break
            if not answer:
                answer = self._build_approval_dashboard_answer(
                    buckets,
                    metrics,
                    incident_code=incident_code_filter,
                    requester=requester_filter,
                )
        return QueryResponse(
            request_id=request_id,
            route_type="structured_lookup",
            data=QueryResponseData(
                answer=answer,
                citations=[],
                approval_dashboard=buckets,
                approval_dashboard_metrics=metrics,
                approvals=[approval for bucket in buckets for approval in bucket.approvals],
                links=dashboard_links,
            ),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_approval_dashboard"],
                approval_involved=total_count > 0,
            ),
        )

    def _handle_approval_list_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
        approval_service = ApprovalService.from_env()
        status_filter = self._extract_approval_status_filter(request.message)
        incident_code_filter = self._extract_incident_code(request.message)
        requester_filter = self._extract_requester_filter(request.message)
        approvals, total_count = approval_service.list_approvals(
            status=status_filter,
            incident_code=incident_code_filter,
            requester=requester_filter,
            page=1,
            page_size=20,
            sort_by="requested_at",
            sort_order="desc",
        )
        tool_name = "list_approvals"
        if status_filter:
            tool_name = f"{tool_name}:{status_filter}"
        if incident_code_filter:
            tool_name = f"list_approvals:{status_filter}:incident" if status_filter else f"{tool_name}:incident"
        list_href = "/api/v1/approvals" + self._build_query_string(
            status=status_filter,
            incident_code=incident_code_filter,
            requester=requester_filter,
        )
        links = [
            ApiLink(
                rel="approval_list",
                href=list_href,
                method="GET",
                description="Browse approval work items with optional status filtering.",
            )
        ]
        for approval in approvals[:3]:
            links.extend(self._build_approval_links(approval))
        return QueryResponse(
            request_id=request_id,
            route_type="structured_lookup",
            data=QueryResponseData(
                answer=self._build_approval_list_answer(
                    approvals,
                    status_filter=status_filter,
                    incident_code=incident_code_filter,
                    requester=requester_filter,
                    total_count=total_count,
                ),
                citations=[],
                approvals=approvals,
                links=self._dedupe_links(links),
            ),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=[tool_name],
                approval_involved=bool(approvals),
            ),
        )

    def _handle_approval_detail_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
        approval_id = self._extract_approval_id(request.message)
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

        approval_service = ApprovalService.from_env()
        try:
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
        if self._is_approval_history_lookup(request.message) or self._is_approval_reason_lookup(request.message):
            audit_events = approval_service.get_approval_audit(approval_id)
            tools_used.append("get_approval_audit")

        answer = self._build_approval_answer(request.message, approval)
        if self._is_approval_reason_lookup(request.message):
            answer = self._build_approval_reason_answer(approval, audit_events)
        elif self._is_approval_history_lookup(request.message):
            answer = self._build_approval_history_answer(request.message, approval, audit_events)

        return QueryResponse(
            request_id=request_id,
            route_type="structured_lookup",
            data=QueryResponseData(
                answer=answer,
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

    def _handle_inventory_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
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

    def _handle_structured_lookup_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
        if self._is_structured_analytics_lookup(request) or self._is_approval_dashboard_lookup(request.message):
            return self._handle_dashboard_structured_lookup(request, request_id=request_id)
        if self._is_approval_list_lookup(request.message):
            return self._handle_approval_list_query(request, request_id=request_id)
        if self._looks_like_approval_lookup(request.message):
            return self._handle_approval_detail_query(request, request_id=request_id)
        return self._handle_inventory_query(request, request_id=request_id)

    def _handle_escalation_guidance_query(self, request: QueryRequest, *, request_id: str) -> QueryResponse:
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
                    update={"message": self._build_incident_support_query(request.message, incident)}
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

        retrieval_results = self._retrieve_context(
            retrieval_request,
            route_type="escalation_guidance",
            request_id=request_id,
        )
        citations = self._build_citations(retrieval_results)
        approval_suggestion = self._build_approval_suggestion(incident)
        links = self._build_incident_links(incident)
        if approval_suggestion:
            links.append(approval_suggestion.create_request)
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
                links=self._dedupe_links(links),
                approval_suggestion=approval_suggestion,
            ),
            meta=QueryResponseMeta(
                citations_included=bool(citations),
                tools_used=tools_used,
                approval_involved=bool(approval_suggestion),
            ),
        )

    def handle_query(self, request: QueryRequest, *, request_id: str | None = None) -> QueryResponse:
        route_type = self._classify_route(request)
        request_id = request_id or f"req_{uuid4().hex[:12]}"
        handlers: dict[str, Callable[[QueryRequest], QueryResponse]] = {
            "policy_qa": lambda current_request: self._handle_policy_query(current_request, request_id=request_id),
            "incident_summary": lambda current_request: self._handle_incident_summary_query(
                current_request,
                request_id=request_id,
            ),
            "structured_lookup": lambda current_request: self._handle_structured_lookup_query(
                current_request,
                request_id=request_id,
            ),
            "escalation_guidance": lambda current_request: self._handle_escalation_guidance_query(
                current_request,
                request_id=request_id,
            ),
        }
        if route_type not in handlers:
            raise UnsupportedRouteError(
                route_type=route_type,
                message=(
                    "The `/query` route is currently wired for policy/process Q&A, "
                    "incident summaries, escalation guidance, and inventory lookup only. "
                    f"The request was classified as `{route_type}`."
                ),
            )

        response = handlers[route_type](request)
        self._log_query_response(request, response)
        return response

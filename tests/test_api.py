from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.auth import build_demo_access_headers
from app.api.approval_service import ApprovalConflictError, ApprovalNotFoundError, ApprovalPermissionError
from app.api.audit import ApiAuditSink
from app.api.main import app
from app.api.query_service import QueryService
from app.api.schemas import (
    ApprovalAgedIncidentMetric,
    ApprovalAuditEvent,
    ApprovalDailyTrendBucket,
    ApprovalDashboardMetrics,
    ApprovalDashboardSummaryRisk,
    ApprovalIncidentPressureMetric,
    ApprovalOldestPendingItemMetric,
    ApprovalPendingOwnerMetric,
    ApprovalRequesterLoadMetric,
    ApprovalRecord,
    IncidentEvent,
    IncidentRecord,
    InventoryResult,
    ProductMatch,
    QueryRequest,
    UserSummary,
)
from app.api.inventory_service import InventoryLookupOutcome
from app.retrieval.models import RetrievalResult


SEEDED_INCIDENT = IncidentRecord(
    incident_id="inc_1042",
    incident_code="INC-1042",
    title="Mobile Checkout Failure",
    status="resolved",
    severity="sev2",
    service_area="checkout",
    summary=(
        "A mobile-only checkout issue caused intermittent failures after the payment "
        "step until the checkout configuration was rolled back."
    ),
    customer_impact="Customers experienced intermittent checkout failures and elevated abandonment on mobile web.",
    start_time=datetime(2026, 4, 12, 13, 0, tzinfo=UTC),
    resolved_time=datetime(2026, 4, 12, 13, 42, tzinfo=UTC),
)

SEEDED_TIMELINE = [
    IncidentEvent(
        event_time=datetime(2026, 4, 12, 13, 5, tzinfo=UTC),
        event_type="investigation_started",
        actor="Alex Kim",
        event_summary="Checkout failures reproduced on mobile web.",
    ),
    IncidentEvent(
        event_time=datetime(2026, 4, 12, 13, 42, tzinfo=UTC),
        event_type="resolved",
        actor="Alex Kim",
        event_summary="Mobile checkout error rates returned to baseline and the incident was resolved.",
    ),
]

ACTIVE_INCIDENT = IncidentRecord(
    incident_id="inc_1091",
    incident_code="INC-1091",
    title="Payment Authorization Timeout",
    status="mitigated",
    severity="sev1",
    service_area="payments",
    summary="Payment authorization calls timed out for a large share of checkout attempts.",
    customer_impact="Customers saw widespread checkout failures and duplicate retry attempts during the incident window.",
    start_time=datetime(2026, 4, 19, 16, 5, tzinfo=UTC),
    resolved_time=None,
)

ACTIVE_TIMELINE = [
    IncidentEvent(
        event_time=datetime(2026, 4, 19, 16, 9, tzinfo=UTC),
        event_type="investigation_started",
        actor="Sam Rivera",
        event_summary="Payment provider timeouts reproduced in checkout logs and alerting.",
    ),
    IncidentEvent(
        event_time=datetime(2026, 4, 19, 16, 31, tzinfo=UTC),
        event_type="customer_impact_updated",
        actor="Casey Nguyen",
        event_summary="Support guidance refreshed with retry limits and payment-workaround messaging.",
    ),
]


class FakeInventoryService:
    def lookup_inventory(self, product_query: str) -> InventoryLookupOutcome:
        assert product_query == "Phantom X shoes"
        return InventoryLookupOutcome(
            answer="Phantom X Shoes is currently available in 3 location(s).",
            product=ProductMatch(
                product_id="prod_123",
                sku="PX-100",
                product_name="Phantom X Shoes",
                category="Footwear",
                brand="Phantom",
                status="active",
            ),
            inventory_results=[
                InventoryResult(
                    location_code="CHI-FC",
                    location_name="Chicago Fulfillment Center",
                    region="Midwest",
                    quantity_available=24,
                    inventory_status="in_stock",
                ),
                InventoryResult(
                    location_code="DAL-DC",
                    location_name="Dallas Distribution Center",
                    region="South",
                    quantity_available=12,
                    inventory_status="in_stock",
                ),
            ],
        )


class FakeIncidentService:
    def get_incident(self, incident_code: str) -> IncidentRecord | None:
        if incident_code.upper() == "INC-1042":
            return SEEDED_INCIDENT
        return None

    def get_incident_timeline(self, incident_id: str) -> list[IncidentEvent]:
        if incident_id == SEEDED_INCIDENT.incident_id:
            return SEEDED_TIMELINE
        return []


class FakeActiveIncidentService:
    def get_incident(self, incident_code: str) -> IncidentRecord | None:
        if incident_code.upper() == "INC-1091":
            return ACTIVE_INCIDENT
        return None

    def get_incident_timeline(self, incident_id: str) -> list[IncidentEvent]:
        if incident_id == ACTIVE_INCIDENT.incident_id:
            return ACTIVE_TIMELINE
        return []


class FakeApprovalService:
    def __init__(self) -> None:
        self.requester = UserSummary(
            user_id="usr_support",
            full_name="Morgan Support",
            role="support_analyst",
            email="support.analyst@demo.local",
        )
        self.approver = UserSummary(
            user_id="usr_ops",
            full_name="Dana Lee",
            role="ops_manager",
            email="ops.manager@demo.local",
        )
        self.records: dict[str, ApprovalRecord] = {}
        self.audit_events: dict[str, list[ApprovalAuditEvent]] = {}

    def create_incident_escalation_request(
        self,
        *,
        incident_id: str,
        incident_code: str,
        requested_by_user_id: str,
        requested_by_role: str,
        escalation_reason: str,
        proposed_priority: str,
        draft_summary: str,
        request_id: str,
    ) -> ApprovalRecord:
        approval_id = "apr_test_001"
        record = ApprovalRecord(
            approval_id=approval_id,
            status="pending",
            request_type="incident_escalation",
            target_type="incident",
            target_id=incident_id,
            requested_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
            decision_notes=None,
            next_step="Awaiting approver decision.",
            requester=self.requester,
            approver=self.approver,
            payload={
                "incident_code": incident_code,
                "escalation_reason": escalation_reason,
                "proposed_priority": proposed_priority,
                "draft_summary": draft_summary,
            },
        )
        self.records[approval_id] = record
        self.audit_events[approval_id] = [
            ApprovalAuditEvent(
                audit_event_id="aud_req_001",
                event_type="approval_requested",
                occurred_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
                route_type="approval_request",
                tool_name="create_incident_escalation_request",
                request_id=request_id,
                actor=self.requester,
                target_type="incident",
                target_id=incident_id,
                payload={
                    "approval_id": approval_id,
                    "incident_code": incident_code,
                    "proposed_priority": proposed_priority,
                },
            )
        ]
        return record

    def get_approval_status(self, approval_id: str) -> ApprovalRecord:
        if approval_id not in self.records:
            raise ApprovalNotFoundError(f"Approval {approval_id} was not found.")
        return self.records[approval_id]

    def decide_approval(
        self,
        *,
        approval_id: str,
        decider_user_id: str,
        decider_role: str,
        decision: str,
        decision_notes: str | None,
        request_id: str,
    ) -> ApprovalRecord:
        record = self.get_approval_status(approval_id)
        if decider_role not in {"ops_manager", "admin"}:
            raise ApprovalPermissionError("Only ops managers or admins may decide approvals.")
        if record.status != "pending":
            raise ApprovalConflictError(
                f"Approval {approval_id} is already {record.status} and cannot be decided again."
            )
        updated = record.model_copy(
            update={
                "status": decision,
                "decision_notes": decision_notes,
                "decided_at": datetime(2026, 4, 20, 10, 15, tzinfo=UTC),
                "next_step": (
                    "Approval granted. The escalation can now be executed by the workflow owner."
                    if decision == "approved"
                    else "Approval rejected. Review the decision notes and revise the request if needed."
                ),
            }
        )
        self.records[approval_id] = updated
        self.audit_events.setdefault(approval_id, []).append(
            ApprovalAuditEvent(
                audit_event_id="aud_dec_001",
                event_type="approval_decided",
                occurred_at=datetime(2026, 4, 20, 10, 15, tzinfo=UTC),
                route_type="approval_decision",
                tool_name="decide_approval",
                request_id=request_id,
                actor=self.approver,
                target_type=record.target_type,
                target_id=record.target_id,
                payload={
                    "approval_id": approval_id,
                    "decision": decision,
                    "decision_notes": decision_notes,
                },
            )
        )
        return updated

    def get_approval_audit(
        self,
        approval_id: str,
        *,
        event_type: str | None = None,
    ) -> list[ApprovalAuditEvent]:
        self.get_approval_status(approval_id)
        events = self.audit_events.get(approval_id, [])
        if not event_type:
            return events
        return [event for event in events if event.event_type == event_type]

    def get_latest_incident_approval(self, incident_id: str) -> ApprovalRecord | None:
        for record in reversed(list(self.records.values())):
            if record.target_type == "incident" and record.target_id == incident_id:
                return record
        return None

    def list_approvals(
        self,
        *,
        status: str | None = None,
        incident_code: str | None = None,
        requester: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "requested_at",
        sort_order: str = "desc",
    ) -> tuple[list[ApprovalRecord], int]:
        records = list(self.records.values())
        if status:
            records = [record for record in records if record.status == status]
        if incident_code:
            records = [
                record for record in records if record.payload.get("incident_code") == incident_code
            ]
        if requester:
            requester_lower = requester.lower()
            records = [
                record
                for record in records
                if record.requester
                and (
                    requester_lower in record.requester.full_name.lower()
                    or (record.requester.email and requester_lower in record.requester.email.lower())
                    or requester_lower == record.requester.user_id.lower()
                )
            ]
        reverse = sort_order == "desc"
        if sort_by == "status":
            records.sort(key=lambda record: record.status, reverse=reverse)
        elif sort_by == "decided_at":
            records.sort(key=lambda record: record.decided_at or datetime.min.replace(tzinfo=UTC), reverse=reverse)
        else:
            records.sort(key=lambda record: record.requested_at, reverse=reverse)
        total_count = len(records)
        offset = max(page - 1, 0) * page_size
        return records[offset : offset + page_size], total_count

    def get_approval_dashboard(
        self,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
        page_size_per_bucket: int = 5,
    ):
        from app.api.schemas import (
            ApprovalDashboardBucket,
            ApprovalDashboardMetrics,
            ApprovalIncidentPressureMetric,
            ApprovalPendingOwnerMetric,
            ApprovalRequesterLoadMetric,
        )

        buckets = []
        for status in ("pending", "approved", "rejected"):
            approvals, total_count = self.list_approvals(
                status=status,
                incident_code=incident_code,
                requester=requester,
                page=1,
                page_size=page_size_per_bucket,
            )
            buckets.append(
                ApprovalDashboardBucket(
                    status=status,
                    count=total_count,
                    approvals=approvals,
                )
            )
        pending_approvals, pending_count = self.list_approvals(
            status="pending",
            incident_code=incident_code,
            requester=requester,
            page=1,
            page_size=200,
            sort_by="requested_at",
            sort_order="asc",
        )
        all_filtered_approvals, _ = self.list_approvals(
            incident_code=incident_code,
            requester=requester,
            page=1,
            page_size=500,
            sort_by="requested_at",
            sort_order="desc",
        )
        priority_counts: dict[str, int] = {}
        owner_counts: dict[tuple[str, str | None], int] = {}
        requester_counts: dict[tuple[str, str | None], int] = {}
        incident_counts: dict[str, int] = {}
        today = datetime.now(UTC).date()
        for approval in pending_approvals:
            priority = approval.payload.get("proposed_priority") or "unknown"
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
            incident_key = approval.payload.get("incident_code") or "unknown_incident"
            incident_counts[incident_key] = incident_counts.get(incident_key, 0) + 1
            requester_key = (
                approval.requester.full_name if approval.requester else "Unknown requester",
                approval.requester.role if approval.requester else None,
            )
            requester_counts[requester_key] = requester_counts.get(requester_key, 0) + 1
            owner_key = (
                approval.approver.full_name if approval.approver else "Unassigned approver",
                approval.approver.role if approval.approver else None,
            )
            owner_counts[owner_key] = owner_counts.get(owner_key, 0) + 1
        oldest_pending_item = None
        if pending_approvals:
            oldest = pending_approvals[0]
            oldest_pending_item = ApprovalOldestPendingItemMetric(
                approval_id=oldest.approval_id,
                approver_name=oldest.approver.full_name if oldest.approver else "Unassigned approver",
                approver_role=oldest.approver.role if oldest.approver else None,
                requester_name=oldest.requester.full_name if oldest.requester else "Unknown requester",
                requester_role=oldest.requester.role if oldest.requester else None,
                incident_code=oldest.payload.get("incident_code"),
                requested_at=oldest.requested_at,
                pending_age_minutes=30,
            )
        metrics = ApprovalDashboardMetrics(
            pending_count=pending_count,
            approvals_created_last_24h=len(all_filtered_approvals),
            approvals_decided_last_24h=len(
                [record for record in all_filtered_approvals if record.decided_at is not None]
            ),
            approvals_created_last_7d=len(all_filtered_approvals),
            approvals_decided_last_7d=len(
                [record for record in all_filtered_approvals if record.decided_at is not None]
            ),
            oldest_pending_age_minutes=30 if pending_approvals else None,
            oldest_pending_item=oldest_pending_item,
            pending_by_priority=priority_counts,
            pending_by_owner=[
                ApprovalPendingOwnerMetric(
                    approver_name=name,
                    approver_role=role,
                    pending_count=count,
                )
                for (name, role), count in owner_counts.items()
            ],
            pending_by_requester=[
                ApprovalRequesterLoadMetric(
                    requester_name=name,
                    requester_role=role,
                    pending_count=count,
                )
                for (name, role), count in requester_counts.items()
            ],
            pending_by_incident=[
                ApprovalIncidentPressureMetric(
                    incident_code=incident_code_key,
                    pending_count=count,
                )
                for incident_code_key, count in sorted(
                    incident_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            daily_trends_7d=[
                ApprovalDailyTrendBucket(
                    bucket_date=today - timedelta(days=offset),
                    approvals_created=1 if offset == 0 and all_filtered_approvals else 0,
                    approvals_decided=0,
                )
                for offset in range(6, -1, -1)
            ],
            aged_pending_incidents=[
                ApprovalAgedIncidentMetric(
                    incident_code=incident_code_key,
                    pending_count=count,
                    oldest_pending_age_minutes=30,
                )
                for incident_code_key, count in sorted(
                    incident_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
        )
        return buckets, metrics

    def list_incidents_with_pending_approvals_older_than(
        self,
        *,
        min_pending_age_minutes: int,
        requester: str | None = None,
    ):
        _, metrics = self.get_approval_dashboard(requester=requester)
        return [
            incident
            for incident in metrics.aged_pending_incidents
            if incident.oldest_pending_age_minutes >= min_pending_age_minutes
        ]

    def get_approval_dashboard_summary(
        self,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
        min_pending_age_minutes: int | None = None,
    ):
        _, metrics = self.get_approval_dashboard(incident_code=incident_code, requester=requester)
        risks: list[ApprovalDashboardSummaryRisk] = []
        if metrics.oldest_pending_item:
            risks.append(
                ApprovalDashboardSummaryRisk(
                    risk_type="oldest_pending_item",
                    title="Oldest pending approval",
                    detail="Oldest pending approval risk.",
                    metric_value=metrics.oldest_pending_item.pending_age_minutes,
                    incident_code=metrics.oldest_pending_item.incident_code,
                    approval_id=metrics.oldest_pending_item.approval_id,
                )
            )
        if metrics.pending_by_owner:
            risks.append(
                ApprovalDashboardSummaryRisk(
                    risk_type="approver_bottleneck",
                    title="Approver bottleneck",
                    detail="Approver bottleneck risk.",
                    metric_value=metrics.pending_by_owner[0].pending_count,
                )
            )
        if min_pending_age_minutes is not None:
            for incident in self.list_incidents_with_pending_approvals_older_than(
                min_pending_age_minutes=min_pending_age_minutes,
                requester=requester,
            )[:3]:
                risks.append(
                    ApprovalDashboardSummaryRisk(
                        risk_type="aged_incident_pressure",
                        title="Aged incident approval",
                        detail="Aged incident risk.",
                        metric_value=incident.oldest_pending_age_minutes,
                        incident_code=incident.incident_code,
                    )
                )
        return metrics, risks


class ApiWorkflowTests(TestCase):
    client = TestClient(app)

    def setUp(self) -> None:
        self._original_demo_access_password = os.environ.get("DEMO_ACCESS_PASSWORD")
        os.environ.pop("DEMO_ACCESS_PASSWORD", None)

    def tearDown(self) -> None:
        if self._original_demo_access_password is None:
            os.environ.pop("DEMO_ACCESS_PASSWORD", None)
        else:
            os.environ["DEMO_ACCESS_PASSWORD"] = self._original_demo_access_password

    def test_query_inventory_returns_seeded_inventory_shape(self) -> None:
        with patch(
            "app.api.query_service.InventoryService.from_env",
            return_value=FakeInventoryService(),
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Check inventory for the Phantom X shoes.",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertEqual(payload["data"]["product"]["product_name"], "Phantom X Shoes")
        self.assertEqual(len(payload["data"]["inventory_results"]), 2)
        self.assertEqual(payload["meta"]["tools_used"], ["resolve_product", "check_inventory"])

    def test_query_approval_status_returns_structured_approval_record(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_lookup",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "What is the status of approval apr_test_001?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertEqual(payload["data"]["approval"]["approval_id"], "apr_test_001")
        self.assertEqual(payload["data"]["approval"]["status"], "pending")
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/approvals/apr_test_001")
        self.assertEqual(payload["data"]["links"][1]["href"], "/api/v1/incidents/INC-1042")
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_status"])
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_approval_status_without_id_returns_guidance(self) -> None:
        response = self.client.post(
            "/api/v1/query",
            json={
                "message": "Can you check the approval status for me?",
                "user_role": "support_analyst",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("I need the approval ID", payload["data"]["answer"])
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_status"])
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_approval_actor_lookup_returns_natural_decision_summary(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_actor_lookup",
        )
        fake_approval_service.decide_approval(
            approval_id="apr_test_001",
            decider_user_id="demo-ops-manager-001",
            decider_role="ops_manager",
            decision="rejected",
            decision_notes="Escalation is not needed after mitigation stabilized.",
            request_id="req_test_approval_actor_decision",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Who rejected approval apr_test_001?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("Dana Lee rejected approval apr_test_001.", payload["data"]["answer"])
        self.assertIn("Escalation is not needed after mitigation stabilized.", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval"]["status"], "rejected")
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_status"])
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_approval_rejection_reason_uses_audit_notes(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_reason_lookup",
        )
        fake_approval_service.decide_approval(
            approval_id="apr_test_001",
            decider_user_id="demo-ops-manager-001",
            decider_role="ops_manager",
            decision="rejected",
            decision_notes="Mitigation stabilized and leadership escalation is no longer necessary.",
            request_id="req_test_approval_reason_decision",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Why was approval apr_test_001 rejected?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("was rejected because", payload["data"]["answer"])
        self.assertIn("Mitigation stabilized", payload["data"]["answer"])
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_status", "get_approval_audit"])

    def test_query_approval_history_returns_audit_timestamps(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_history_lookup",
        )
        fake_approval_service.decide_approval(
            approval_id="apr_test_001",
            decider_user_id="demo-ops-manager-001",
            decider_role="ops_manager",
            decision="approved",
            decision_notes="Proceed with escalation.",
            request_id="req_test_approval_history_decision",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "When was approval apr_test_001 approved?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("was approved at 2026-04-20T10:15:00+00:00", payload["data"]["answer"])
        self.assertEqual(len(payload["data"]["approval_audit"]), 2)
        self.assertEqual(payload["data"]["links"][2]["href"], "/api/v1/approvals/apr_test_001/audit")
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_status", "get_approval_audit"])

    def test_approval_audit_endpoint_returns_history(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_audit_lookup",
        )
        fake_approval_service.decide_approval(
            approval_id="apr_test_001",
            decider_user_id="demo-ops-manager-001",
            decider_role="ops_manager",
            decision="approved",
            decision_notes="Proceed with escalation.",
            request_id="req_test_approval_audit_decision",
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals/apr_test_001/audit")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "approval_audit")
        self.assertEqual(payload["data"]["approval"]["approval_id"], "apr_test_001")
        self.assertEqual(len(payload["data"]["audit_events"]), 2)
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_status", "get_approval_audit"])

    def test_approval_audit_endpoint_filters_by_event_type(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_audit_filter_lookup",
        )
        fake_approval_service.decide_approval(
            approval_id="apr_test_001",
            decider_user_id="demo-ops-manager-001",
            decider_role="ops_manager",
            decision="approved",
            decision_notes="Proceed with escalation.",
            request_id="req_test_approval_audit_filter_decision",
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals/apr_test_001/audit?event_type=approval_decided")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["data"]["audit_events"]), 1)
        self.assertEqual(payload["data"]["audit_events"][0]["event_type"], "approval_decided")

    def test_approval_decision_forbidden_for_non_approver(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_forbidden_decision",
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/approvals/apr_test_001/decision",
                headers={"X-User-Id": "demo-support-001", "X-User-Role": "support_analyst"},
                json={
                    "decision": "approved",
                    "decision_notes": "Testing forbidden path.",
                },
            )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "APPROVAL_PERMISSION_DENIED")

    def test_query_approver_bottleneck_analytics(self) -> None:
        fake_approval_service = FakeApprovalService()
        # Seed two pending approvals assigned to the same approver to create a clear bottleneck
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_bottleneck_1",
        )
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Still impacted.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to ongoing payment timeouts.",
            request_id="req_test_bottleneck_2",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which approver is the bottleneck?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("bottleneck", payload["data"]["answer"].lower())
        self.assertIn("Dana Lee", payload["data"]["answer"])  # current fake approver
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_dashboard"])

    def test_query_pending_owner_summary(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_pending_owner",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Who is holding the pending approvals?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("pending approvals", payload["data"]["answer"].lower())
        self.assertIn("Dana Lee", payload["data"]["answer"])  # current fake approver name appears
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_dashboard"])

    def test_query_incident_summary_includes_linked_approval_state(self) -> None:
        retrieval_results = [
            RetrievalResult(
                document_id="doc_6",
                doc_key="runbook_checkout_incident_001",
                title="Checkout Incident Runbook",
                doc_type="runbook",
                audience="engineering_support",
                section_title="Initial Triage",
                chunk_index=0,
                chunk_text=(
                    "Title: Checkout Incident Runbook\n"
                    "Section: Initial Triage\n"
                    "Content: Check recent deploys, configuration changes, and known dependency incidents."
                ),
                relevance_score=0.87,
            )
        ]
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_incident_linked_approval",
        )

        with patch(
            "app.api.query_service.IncidentService.from_env",
            return_value=FakeIncidentService(),
        ), patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ), patch.object(QueryService, "_retrieve_context", return_value=retrieval_results):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Summarize incident INC-1042 and tell me the likely customer impact.",
                    "user_role": "engineering_support",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["approval"]["approval_id"], "apr_test_001")
        self.assertIn("Approval state:", payload["data"]["answer"])
        self.assertEqual(payload["data"]["links"][1]["href"], "/api/v1/approvals/apr_test_001")
        self.assertEqual(payload["data"]["links"][2]["href"], "/api/v1/approvals/apr_test_001/audit")
        self.assertIn("get_latest_incident_approval", payload["meta"]["tools_used"])
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_incident_summary_answers_escalation_status_question(self) -> None:
        retrieval_results = [
            RetrievalResult(
                document_id="doc_7",
                doc_key="runbook_checkout_incident_001",
                title="Checkout Incident Runbook",
                doc_type="runbook",
                audience="engineering_support",
                section_title="Initial Triage",
                chunk_index=0,
                chunk_text=(
                    "Title: Checkout Incident Runbook\n"
                    "Section: Initial Triage\n"
                    "Content: Check recent deploys, configuration changes, and known dependency incidents."
                ),
                relevance_score=0.86,
            )
        ]
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_incident_escalated_question",
        )

        with patch(
            "app.api.query_service.IncidentService.from_env",
            return_value=FakeIncidentService(),
        ), patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ), patch.object(QueryService, "_retrieve_context", return_value=retrieval_results):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Has incident INC-1042 already been escalated?",
                    "user_role": "engineering_support",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "incident_summary")
        self.assertIn("already has approval apr_test_001", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval"]["approval_id"], "apr_test_001")
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_incident_summary_returns_linked_approval_history(self) -> None:
        retrieval_results = [
            RetrievalResult(
                document_id="doc_8",
                doc_key="runbook_checkout_incident_001",
                title="Checkout Incident Runbook",
                doc_type="runbook",
                audience="engineering_support",
                section_title="Initial Triage",
                chunk_index=0,
                chunk_text=(
                    "Title: Checkout Incident Runbook\n"
                    "Section: Initial Triage\n"
                    "Content: Check recent deploys, configuration changes, and known dependency incidents."
                ),
                relevance_score=0.84,
            )
        ]
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_incident_approval_history_lookup",
        )
        fake_approval_service.decide_approval(
            approval_id="apr_test_001",
            decider_user_id="demo-ops-manager-001",
            decider_role="ops_manager",
            decision="approved",
            decision_notes="Proceed with escalation.",
            request_id="req_test_incident_approval_history_decision",
        )

        with patch(
            "app.api.query_service.IncidentService.from_env",
            return_value=FakeIncidentService(),
        ), patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ), patch.object(QueryService, "_retrieve_context", return_value=retrieval_results):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Show me the approval history for incident INC-1042.",
                    "user_role": "engineering_support",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "incident_summary")
        self.assertIn("Approval history for INC-1042", payload["data"]["answer"])
        self.assertEqual(len(payload["data"]["approval_audit"]), 2)
        self.assertIn("get_latest_incident_approval", payload["meta"]["tools_used"])
        self.assertIn("get_approval_audit", payload["meta"]["tools_used"])

    def test_approval_list_endpoint_filters_pending_items(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_approval_list_pending",
        )
        fake_approval_service.records["apr_test_approved"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_approved",
                "status": "approved",
                "target_id": "inc_other",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "medium"},
            }
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals?status=pending")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "approval_list")
        self.assertEqual(len(payload["data"]["approvals"]), 1)
        self.assertEqual(payload["data"]["approvals"][0]["approval_id"], "apr_test_001")
        self.assertEqual(payload["data"]["total_count"], 1)
        self.assertEqual(payload["data"]["status_filter"], "pending")
        self.assertEqual(payload["meta"]["tools_used"], ["list_approvals:pending"])

    def test_approval_list_endpoint_supports_incident_filter_pagination_and_sorting(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_approval_list_incident_1",
        )
        fake_approval_service.records["apr_test_002"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_002",
                "requested_at": datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
                "payload": {"incident_code": "INC-1091", "proposed_priority": "critical"},
                "target_id": ACTIVE_INCIDENT.incident_id,
            }
        )
        fake_approval_service.records["apr_test_003"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_003",
                "requested_at": datetime(2026, 4, 20, 9, 30, tzinfo=UTC),
                "payload": {"incident_code": "INC-2001", "proposed_priority": "medium"},
                "target_id": "inc_other",
            }
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get(
                "/api/v1/approvals?incident_code=INC-1091&page=1&page_size=1&sort_by=requested_at&sort_order=desc"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["total_count"], 2)
        self.assertEqual(payload["data"]["page"], 1)
        self.assertEqual(payload["data"]["page_size"], 1)
        self.assertEqual(payload["data"]["incident_code_filter"], "INC-1091")
        self.assertEqual(len(payload["data"]["approvals"]), 1)
        self.assertEqual(payload["data"]["approvals"][0]["approval_id"], "apr_test_002")

    def test_approval_dashboard_endpoint_groups_by_status(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_dashboard_pending",
        )
        fake_approval_service.records["apr_test_approved"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_approved",
                "status": "approved",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "medium"},
            }
        )
        fake_approval_service.records["apr_test_rejected"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_rejected",
                "status": "rejected",
                "payload": {"incident_code": "INC-3001", "proposed_priority": "high"},
            }
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals/dashboard?page_size_per_bucket=2")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "approval_dashboard")
        self.assertEqual(payload["data"]["total_count"], 3)
        self.assertEqual([bucket["status"] for bucket in payload["data"]["buckets"]], ["pending", "approved", "rejected"])
        self.assertEqual(payload["data"]["metrics"]["pending_count"], 1)
        self.assertEqual(payload["data"]["metrics"]["approvals_created_last_24h"], 3)
        self.assertEqual(payload["data"]["metrics"]["approvals_decided_last_24h"], 0)
        self.assertEqual(payload["data"]["metrics"]["approvals_created_last_7d"], 3)
        self.assertEqual(payload["data"]["metrics"]["approvals_decided_last_7d"], 0)
        self.assertEqual(len(payload["data"]["metrics"]["daily_trends_7d"]), 7)
        self.assertEqual(payload["data"]["metrics"]["oldest_pending_item"]["approver_name"], "Dana Lee")
        self.assertEqual(payload["data"]["metrics"]["pending_by_priority"], {"high": 1})
        self.assertEqual(payload["data"]["metrics"]["pending_by_owner"][0]["approver_name"], "Dana Lee")
        self.assertEqual(payload["data"]["metrics"]["pending_by_incident"][0]["incident_code"], "INC-1042")
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_dashboard"])

    def test_approval_dashboard_endpoint_supports_filters(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_dashboard_filter_incident",
        )
        fake_approval_service.records["apr_test_other"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_other",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "high"},
                "target_id": "inc_other",
            }
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals/dashboard?incident_code=INC-1091&requester=Morgan")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["incident_code_filter"], "INC-1091")
        self.assertEqual(payload["data"]["requester_filter"], "Morgan")
        self.assertEqual(payload["data"]["total_count"], 1)
        self.assertEqual(payload["data"]["metrics"]["pending_count"], 1)
        self.assertEqual(payload["data"]["metrics"]["approvals_created_last_24h"], 1)
        self.assertEqual(payload["data"]["metrics"]["approvals_created_last_7d"], 1)

    def test_approval_dashboard_summary_endpoint_returns_headlines_and_top_risks(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_dashboard_summary",
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals/dashboard/summary?min_pending_age_minutes=15")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "approval_dashboard_summary")
        self.assertIn("Approval summary:", payload["data"]["answer"])
        self.assertIn("Top risks:", payload["data"]["answer"])
        self.assertEqual(payload["data"]["headline_metrics"]["pending_count"], 1)
        self.assertGreaterEqual(len(payload["data"]["top_risks"]), 1)
        self.assertEqual(payload["data"]["min_pending_age_minutes"], 15)
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_dashboard_summary"])

    def test_operator_dashboard_endpoint_returns_summary_and_bucket_shape(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_operator_dashboard",
        )

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/operator/dashboard?min_pending_age_minutes=15")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "operator_dashboard")
        self.assertIn("Approval summary:", payload["data"]["summary"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard"]["metrics"]["pending_count"], 1)
        self.assertEqual(payload["data"]["approval_dashboard"]["total_count"], 1)
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_dashboard", "get_approval_dashboard_summary"])

    def test_query_approval_list_returns_pending_items(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_query_approval_list_pending",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Show me all pending approvals.",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("I found 1 pending approvals", payload["data"]["answer"])
        self.assertEqual(len(payload["data"]["approvals"]), 1)
        self.assertEqual(payload["data"]["approvals"][0]["approval_id"], "apr_test_001")
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/approvals?status=pending")
        self.assertEqual(payload["meta"]["tools_used"], ["list_approvals:pending"])
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_approval_list_filters_rejected_items_for_incident(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_rejected_incident",
        )
        fake_approval_service.records["apr_test_rejected"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_rejected",
                "status": "rejected",
                "target_id": ACTIVE_INCIDENT.incident_id,
                "payload": {"incident_code": "INC-1091", "proposed_priority": "critical"},
            }
        )
        fake_approval_service.records["apr_test_other"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_other",
                "status": "rejected",
                "target_id": "inc_other",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "high"},
            }
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Show me rejected approvals for INC-1091.",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("I found 1 rejected approvals for INC-1091", payload["data"]["answer"])
        self.assertEqual(len(payload["data"]["approvals"]), 1)
        self.assertEqual(payload["data"]["approvals"][0]["approval_id"], "apr_test_rejected")
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/approvals?status=rejected&incident_code=INC-1091")
        self.assertEqual(payload["meta"]["tools_used"], ["list_approvals:rejected:incident"])

    def test_query_approval_dashboard_returns_grouped_status_summary(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=SEEDED_INCIDENT.incident_id,
            incident_code=SEEDED_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact is growing.",
            proposed_priority="high",
            draft_summary="Escalate to management due to sustained checkout issues.",
            request_id="req_test_query_dashboard_pending",
        )
        fake_approval_service.records["apr_test_approved"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_approved",
                "status": "approved",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "medium"},
            }
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Show me the approval dashboard.",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("Approval dashboard:", payload["data"]["answer"])
        self.assertIn("7-day daily trend:", payload["data"]["answer"])
        self.assertEqual(len(payload["data"]["approval_dashboard"]), 3)
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/approvals/dashboard")
        self.assertEqual(payload["data"]["links"][1]["href"], "/api/v1/approvals/dashboard/summary")
        self.assertEqual(payload["data"]["links"][2]["href"], "/api/v1/operator/dashboard")
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_count"], 1)
        self.assertIn("Review approval apr_test_001", payload["data"]["recommended_next_step"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["approvals_created_last_24h"], 2)
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["approvals_created_last_7d"], 2)
        self.assertEqual(len(payload["data"]["approval_dashboard_metrics"]["daily_trends_7d"]), 7)
        self.assertEqual(payload["meta"]["tools_used"], ["get_approval_dashboard"])
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_query_pending_owner_lookup_returns_current_approvers(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_pending_owners",
        )
        fake_approval_service.records["apr_test_002"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_002",
                "payload": {"incident_code": "INC-1091", "proposed_priority": "high"},
                "target_id": ACTIVE_INCIDENT.incident_id,
            }
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Who is holding the pending approvals for INC-1091?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("Pending approvals for INC-1091 are currently held by:", payload["data"]["answer"])
        self.assertIn("Dana Lee", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_count"], 2)
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/approvals/dashboard?incident_code=INC-1091")

    def test_query_escalation_load_lookup_returns_top_incidents(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_escalation_load_1",
        )
        fake_approval_service.records["apr_test_002"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_002",
                "payload": {"incident_code": "INC-1091", "proposed_priority": "high"},
                "target_id": ACTIVE_INCIDENT.incident_id,
            }
        )
        fake_approval_service.records["apr_test_003"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_003",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "medium"},
                "target_id": "inc_other",
            }
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which incidents have the most pending approval pressure?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("Pending approval pressure is currently highest on INC-1091 with 2 pending approval(s).", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_by_incident"][0]["incident_code"], "INC-1091")
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_by_incident"][0]["pending_count"], 2)

    def test_query_requester_load_lookup_returns_top_requester(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_requester_load_1",
        )
        fake_approval_service.records["apr_test_002"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_002",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "high"},
                "target_id": "inc_other",
            }
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which requester is creating the most approval load?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("Approval load is currently highest for requester Morgan Support with 2 pending approval(s).", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_by_requester"][0]["requester_name"], "Morgan Support")
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_by_requester"][0]["pending_count"], 2)

    def test_query_approver_bottleneck_lookup_returns_top_approver(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_approver_bottleneck_1",
        )
        fake_approval_service.records["apr_test_002"] = fake_approval_service.records["apr_test_001"].model_copy(
            update={
                "approval_id": "apr_test_002",
                "payload": {"incident_code": "INC-2001", "proposed_priority": "high"},
                "target_id": "inc_other",
            }
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which approver is the bottleneck?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn(
            "The current approval bottleneck is Dana Lee (ops_manager) with 2 pending approval(s).",
            payload["data"]["answer"],
        )
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_by_owner"][0]["approver_name"], "Dana Lee")
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["pending_by_owner"][0]["pending_count"], 2)

    def test_query_oldest_pending_item_lookup_returns_oldest_pending_approver(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_oldest_pending_item_1",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which approver has the oldest pending item?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("The oldest pending approval item is currently with Dana Lee (ops_manager):", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["oldest_pending_item"]["approver_name"], "Dana Lee")

    def test_query_oldest_pending_requester_lookup_returns_requester_summary(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_oldest_pending_requester_1",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which requester has the oldest pending approval?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("The requester with the oldest pending approval is Morgan Support (support_analyst).", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["oldest_pending_item"]["requester_name"], "Morgan Support")

    def test_query_oldest_pending_incident_lookup_returns_incident_summary(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_oldest_pending_incident_1",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Which incident has the oldest pending approval?",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("The incident with the oldest pending approval is INC-1091.", payload["data"]["answer"])
        self.assertEqual(payload["data"]["approval_dashboard_metrics"]["oldest_pending_item"]["incident_code"], "INC-1091")

    def test_query_aged_pending_incidents_lookup_filters_by_minutes(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_approval_service.create_incident_escalation_request(
            incident_id=ACTIVE_INCIDENT.incident_id,
            incident_code=ACTIVE_INCIDENT.incident_code,
            requested_by_user_id="demo-support-001",
            requested_by_role="support_analyst",
            escalation_reason="Customer impact remains elevated.",
            proposed_priority="critical",
            draft_summary="Escalate to management due to payment failures.",
            request_id="req_test_query_aged_incidents_1",
        )

        with patch(
            "app.api.query_service.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Show me only incidents with pending approvals older than 15 minutes.",
                    "user_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "structured_lookup")
        self.assertIn("I found 1 incident(s) with pending approvals older than 15 minute(s):", payload["data"]["answer"])
        self.assertIn("INC-1091", payload["data"]["answer"])

    def test_incident_detail_endpoint_returns_incident_and_timeline(self) -> None:
        with patch(
            "app.api.incident_router.IncidentService.from_env",
            return_value=FakeIncidentService(),
        ):
            response = self.client.get("/api/v1/incidents/INC-1042")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "incident_detail")
        self.assertEqual(payload["data"]["incident"]["incident_code"], "INC-1042")
        self.assertEqual(len(payload["data"]["incident_timeline"]), 2)
        self.assertEqual(payload["meta"]["tools_used"], ["get_incident", "get_incident_timeline"])

    def test_query_incident_summary_blends_structured_and_retrieval_context(self) -> None:
        retrieval_results = [
            RetrievalResult(
                document_id="doc_1",
                doc_key="incident_playbook_mobile_checkout_001",
                title="Mobile Checkout Incident Playbook",
                doc_type="incident_playbook",
                audience="engineering_support",
                section_title="Immediate Actions",
                chunk_index=0,
                chunk_text=(
                    "Title: Mobile Checkout Incident Playbook\n"
                    "Section: Immediate Actions\n"
                    "Content: Confirm whether the issue reproduces on mobile web and whether "
                    "desktop remains healthy."
                ),
                relevance_score=0.91,
            ),
            RetrievalResult(
                document_id="doc_2",
                doc_key="runbook_checkout_incident_001",
                title="Checkout Incident Runbook",
                doc_type="runbook",
                audience="engineering_support",
                section_title="Initial Triage",
                chunk_index=1,
                chunk_text=(
                    "Title: Checkout Incident Runbook\n"
                    "Section: Initial Triage\n"
                    "Content: Check recent deploys, configuration changes, and known dependency incidents."
                ),
                relevance_score=0.88,
            ),
        ]

        with patch(
            "app.api.query_service.IncidentService.from_env",
            return_value=FakeIncidentService(),
        ), patch.object(QueryService, "_retrieve_context", return_value=retrieval_results):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Summarize incident INC-1042 and tell me the likely customer impact.",
                    "user_role": "engineering_support",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "incident_summary")
        self.assertIn("INC-1042 — Mobile Checkout Failure", payload["data"]["answer"])
        self.assertEqual(payload["data"]["incident"]["incident_code"], "INC-1042")
        self.assertEqual(payload["data"]["recommended_next_step"], "Publish the final incident summary and capture any follow-up remediation from the timeline.")
        self.assertEqual(payload["meta"]["tools_used"], ["get_incident", "get_incident_timeline"])
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/incidents/INC-1042")
        self.assertIsNone(payload["data"]["approval_suggestion"])

    def test_query_incident_summary_exposes_approval_suggestion_for_active_incident(self) -> None:
        retrieval_results = [
            RetrievalResult(
                document_id="doc_3",
                doc_key="runbook_checkout_incident_001",
                title="Checkout Incident Runbook",
                doc_type="runbook",
                audience="engineering_support",
                section_title="Mitigation Guidance",
                chunk_index=0,
                chunk_text=(
                    "Title: Checkout Incident Runbook\n"
                    "Section: Mitigation Guidance\n"
                    "Content: Keep mitigation active while customer impact remains elevated."
                ),
                relevance_score=0.84,
            )
        ]

        with patch(
            "app.api.query_service.IncidentService.from_env",
            return_value=FakeActiveIncidentService(),
        ), patch.object(QueryService, "_retrieve_context", return_value=retrieval_results):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Summarize incident INC-1091 and tell me the likely customer impact.",
                    "user_role": "engineering_support",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/incidents/INC-1091")
        self.assertEqual(payload["data"]["links"][1]["href"], "/api/v1/escalations")
        self.assertEqual(payload["data"]["approval_suggestion"]["action_type"], "incident_escalation")
        self.assertEqual(payload["data"]["approval_suggestion"]["proposed_priority"], "critical")

    def test_query_escalation_guidance_blends_policy_and_active_incident_context(self) -> None:
        retrieval_results = [
            RetrievalResult(
                document_id="doc_4",
                doc_key="escalation_procedure_incident_escalation_001",
                title="Incident Escalation Procedure",
                doc_type="policy",
                audience="ops_manager",
                section_title="When Escalation Is Required",
                chunk_index=0,
                chunk_text=(
                    "Title: Incident Escalation Procedure\n"
                    "Section: When Escalation Is Required\n"
                    "Content: Escalate when severe customer impact continues, mitigation is unstable, "
                    "or leadership coordination is required."
                ),
                relevance_score=0.93,
            ),
            RetrievalResult(
                document_id="doc_5",
                doc_key="matrix_priority_escalation_001",
                title="Priority Escalation Matrix",
                doc_type="matrix",
                audience="ops_manager",
                section_title="High Priority Criteria",
                chunk_index=1,
                chunk_text=(
                    "Title: Priority Escalation Matrix\n"
                    "Section: High Priority Criteria\n"
                    "Content: Use critical or high priority when the incident affects checkout revenue, "
                    "cross-functional coordination, or widespread customer harm."
                ),
                relevance_score=0.89,
            ),
        ]

        with patch(
            "app.api.query_service.IncidentService.from_env",
            return_value=FakeActiveIncidentService(),
        ), patch.object(QueryService, "_retrieve_context", return_value=retrieval_results):
            response = self.client.post(
                "/api/v1/query",
                json={
                    "message": "Should INC-1091 be escalated right now?",
                    "user_role": "ops_manager",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_type"], "escalation_guidance")
        self.assertEqual(payload["data"]["incident"]["incident_code"], "INC-1091")
        self.assertIn("Recommended escalation posture", payload["data"]["answer"])
        self.assertEqual(
            payload["data"]["recommended_next_step"],
            "Create a critical-priority approval request if INC-1091 needs management attention.",
        )
        self.assertEqual(payload["data"]["links"][0]["href"], "/api/v1/incidents/INC-1091")
        self.assertEqual(payload["data"]["links"][1]["href"], "/api/v1/escalations")
        self.assertEqual(payload["data"]["approval_suggestion"]["proposed_priority"], "critical")
        self.assertTrue(payload["meta"]["approval_involved"])

    def test_escalation_flow_create_get_and_decide(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_incident_service = FakeIncidentService()

        with patch(
            "app.api.approval_router.IncidentService.from_env",
            return_value=fake_incident_service,
        ), patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            create_response = self.client.post(
                "/api/v1/escalations",
                json={
                    "incident_code": "INC-1042",
                    "escalation_reason": "Customer impact is growing and mitigation is incomplete.",
                    "proposed_priority": "high",
                    "draft_summary": "Recommend escalation due to sustained checkout failures.",
                    "requested_by_role": "engineering_support",
                },
            )

        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertEqual(created["route_type"], "approval_request")
        approval_id = created["data"]["approval"]["approval_id"]
        self.assertEqual(created["data"]["approval"]["status"], "pending")

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            status_response = self.client.get(f"/api/v1/approvals/{approval_id}")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["data"]["approval"]["status"], "pending")

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            decision_response = self.client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "decision_notes": "Escalation justified based on impact.",
                    "decider_role": "ops_manager",
                },
            )

        self.assertEqual(decision_response.status_code, 200)
        decided = decision_response.json()
        self.assertEqual(decided["route_type"], "approval_decision")
        self.assertEqual(decided["data"]["approval"]["status"], "approved")
        self.assertEqual(
            decided["data"]["approval"]["decision_notes"],
            "Escalation justified based on impact.",
        )

    def test_escalation_decision_rejects_non_approver_role(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_incident_service = FakeIncidentService()

        with patch(
            "app.api.approval_router.IncidentService.from_env",
            return_value=fake_incident_service,
        ), patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            create_response = self.client.post(
                "/api/v1/escalations",
                json={
                    "incident_code": "INC-1042",
                    "escalation_reason": "Customer impact is growing and mitigation is incomplete.",
                    "proposed_priority": "high",
                    "draft_summary": "Recommend escalation due to sustained checkout failures.",
                    "requested_by_role": "engineering_support",
                },
            )
            approval_id = create_response.json()["data"]["approval"]["approval_id"]

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "decision_notes": "Trying to self-approve.",
                    "decider_role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "APPROVAL_PERMISSION_DENIED")

    def test_escalation_decision_rejects_duplicate_decision(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_incident_service = FakeIncidentService()

        with patch(
            "app.api.approval_router.IncidentService.from_env",
            return_value=fake_incident_service,
        ), patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            create_response = self.client.post(
                "/api/v1/escalations",
                json={
                    "incident_code": "INC-1042",
                    "escalation_reason": "Customer impact is growing and mitigation is incomplete.",
                    "proposed_priority": "high",
                    "draft_summary": "Recommend escalation due to sustained checkout failures.",
                    "requested_by_role": "engineering_support",
                },
            )
            approval_id = create_response.json()["data"]["approval"]["approval_id"]

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            first_response = self.client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "decision_notes": "Escalation justified based on impact.",
                    "decider_role": "ops_manager",
                },
            )
            second_response = self.client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "decision_notes": "Trying to approve again.",
                    "decider_role": "ops_manager",
                },
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(second_response.json()["error"]["code"], "APPROVAL_CONFLICT")

    def test_escalation_decision_uses_mock_auth_headers_over_body_role(self) -> None:
        fake_approval_service = FakeApprovalService()
        fake_incident_service = FakeIncidentService()

        with patch(
            "app.api.approval_router.IncidentService.from_env",
            return_value=fake_incident_service,
        ), patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            create_response = self.client.post(
                "/api/v1/escalations",
                json={
                    "incident_code": "INC-1042",
                    "escalation_reason": "Customer impact is growing and mitigation is incomplete.",
                    "proposed_priority": "high",
                    "draft_summary": "Recommend escalation due to sustained checkout failures.",
                    "requested_by_role": "engineering_support",
                },
                headers={
                    "X-User-Id": "usr_support_header",
                    "X-User-Role": "engineering_support",
                },
            )
            approval_id = create_response.json()["data"]["approval"]["approval_id"]

        with patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.post(
                f"/api/v1/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "decision_notes": "Body says ops manager, headers say support.",
                    "decider_role": "ops_manager",
                },
                headers={
                    "X-User-Id": "usr_support_header",
                    "X-User-Role": "support_analyst",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "APPROVAL_PERMISSION_DENIED")

    def test_query_logging_persists_request_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_sink = ApiAuditSink(output_path=Path(temp_dir) / "query_events.jsonl")
            service = QueryService(audit_sink=audit_sink)

            with patch(
                "app.api.query_service.InventoryService.from_env",
                return_value=FakeInventoryService(),
            ):
                response = service.handle_query(
                    QueryRequest(
                        message="Check inventory for the Phantom X shoes.",
                        user_id="usr_trace",
                        user_role="support_analyst",
                    ),
                    request_id="req_trace_001",
                )

            lines = (Path(temp_dir) / "query_events.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["event_type"], "query_handled")
            self.assertEqual(payload["request_id"], "req_trace_001")
            self.assertEqual(payload["route_type"], "structured_lookup")
            self.assertEqual(payload["user_role"], "support_analyst")
            self.assertEqual(payload["tools_used"], ["resolve_product", "check_inventory"])
            self.assertEqual(payload["doc_keys"], [])
            self.assertEqual(payload["approval_ids"], [])
            self.assertEqual(response.request_id, "req_trace_001")

    def test_demo_password_protects_non_health_routes(self) -> None:
        with patch.dict(os.environ, {"DEMO_ACCESS_PASSWORD": "demo-secret"}, clear=False):
            health_response = self.client.get("/health")
            query_response = self.client.post(
                "/api/v1/query",
                json={"message": "What is the return process for damaged products?"},
            )

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(query_response.status_code, 401)
        self.assertEqual(query_response.json()["error"]["code"], "DEMO_ACCESS_REQUIRED")

    def test_demo_password_allows_authorized_requests(self) -> None:
        fake_approval_service = FakeApprovalService()
        headers = build_demo_access_headers("demo-secret")

        with patch.dict(os.environ, {"DEMO_ACCESS_PASSWORD": "demo-secret"}, clear=False), patch(
            "app.api.approval_router.ApprovalService.from_env",
            return_value=fake_approval_service,
        ):
            response = self.client.get("/api/v1/approvals", headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

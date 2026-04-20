from __future__ import annotations

from datetime import UTC, datetime
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.approval_service import ApprovalConflictError, ApprovalNotFoundError, ApprovalPermissionError
from app.api.main import app
from app.api.query_service import QueryService
from app.api.schemas import (
    ApprovalRecord,
    IncidentEvent,
    IncidentRecord,
    InventoryResult,
    ProductMatch,
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
        return updated


class ApiWorkflowTests(TestCase):
    client = TestClient(app)

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

from __future__ import annotations

from datetime import UTC, datetime
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.approval_service import ApprovalConflictError, ApprovalNotFoundError, ApprovalPermissionError
from app.api.main import app
from app.api.query_service import QueryService
from app.api.schemas import (
    ApprovalAuditEvent,
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

    def get_approval_audit(self, approval_id: str) -> list[ApprovalAuditEvent]:
        self.get_approval_status(approval_id)
        return self.audit_events.get(approval_id, [])

    def get_latest_incident_approval(self, incident_id: str) -> ApprovalRecord | None:
        for record in reversed(list(self.records.values())):
            if record.target_type == "incident" and record.target_id == incident_id:
                return record
        return None


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

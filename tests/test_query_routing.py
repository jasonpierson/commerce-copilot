from __future__ import annotations

from unittest import TestCase

from app.api.query_service import QueryService
from app.api.schemas import QueryRequest


class QueryRoutingTests(TestCase):
    def setUp(self) -> None:
        self.service = QueryService()

    def test_classify_route_policy_qa(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="What is the return process for damaged products?")
        )
        self.assertEqual(route, "policy_qa")

    def test_classify_route_inventory_lookup(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Check inventory for the Phantom X shoes.")
        )
        self.assertEqual(route, "structured_lookup")

    def test_classify_route_incident_summary(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Summarize incident INC-1091 and tell me the likely customer impact.")
        )
        self.assertEqual(route, "incident_summary")

    def test_classify_route_escalation_guidance(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Should INC-1091 be escalated right now?", user_role="ops_manager")
        )
        self.assertEqual(route, "escalation_guidance")

    def test_classify_route_override_wins(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(
                message="Check inventory for the Phantom X shoes.",
                route_type_override="policy_qa",
            )
        )
        self.assertEqual(route, "policy_qa")

    def test_classify_route_approval_dashboard(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Show me the approval dashboard.")
        )
        self.assertEqual(route, "structured_lookup")

    def test_classify_route_approval_list_browse(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Show me rejected approvals for INC-1091.")
        )
        self.assertEqual(route, "structured_lookup")

    def test_classify_route_pending_owner_lookup(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Who is holding the pending approvals for INC-1091?")
        )
        self.assertEqual(route, "structured_lookup")

    def test_classify_route_requester_load_lookup(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Which requester is creating the most approval load?")
        )
        self.assertEqual(route, "structured_lookup")

    def test_classify_route_escalation_pressure_lookup(self) -> None:
        route = self.service._classify_route(  # noqa: SLF001
            QueryRequest(message="Which incidents have the most pending approval pressure?")
        )
        self.assertEqual(route, "structured_lookup")

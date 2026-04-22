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

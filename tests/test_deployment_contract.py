from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.auth import build_demo_access_headers
from app.api.main import app, rate_limiter
from app.api.schemas import ApprovalRecord, IncidentRecord, UserSummary


class DeploymentContractTests(TestCase):
    client = TestClient(app)

    def setUp(self) -> None:
        rate_limiter.reset()
        self._original_demo_access_password = os.environ.get("DEMO_ACCESS_PASSWORD")
        os.environ.pop("DEMO_ACCESS_PASSWORD", None)

    def tearDown(self) -> None:
        if self._original_demo_access_password is None:
            os.environ.pop("DEMO_ACCESS_PASSWORD", None)
        else:
            os.environ["DEMO_ACCESS_PASSWORD"] = self._original_demo_access_password

    def test_health_route_is_available_without_auth(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_root_route_explains_next_steps_and_auth(self) -> None:
        response = self.client.get("/")
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("description", body)
        self.assertIn("/docs", [step["href"] for step in body["next_steps"]])
        self.assertIn("/version", [step["href"] for step in body["next_steps"]])
        self.assertIn("how_to_authenticate", body["auth"])
        self.assertIn("build", body)

    def test_version_route_reports_build_metadata(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "APP_VERSION": "0.1.0",
                "GIT_SHA": "abc1234",
                "BUILD_TIMESTAMP": "2026-04-27T12:00:00Z",
            },
            clear=False,
        ):
            response = self.client.get("/version")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["app_version"], "0.1.0")
        self.assertEqual(response.json()["git_sha"], "abc1234")
        self.assertEqual(response.json()["build_timestamp"], "2026-04-27T12:00:00Z")
        self.assertEqual(response.json()["app_env"], "production")

    def test_ready_route_reports_ready_when_env_and_db_are_ok(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "SUPABASE_DB_URL": "postgres://demo",
                "OPENAI_API_KEY": "sk-demo",
                "DEMO_ACCESS_PASSWORD": "demo-secret",
            },
            clear=False,
        ), patch("app.api.main.check_connectivity", return_value=(True, None)):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertTrue(response.json()["checks"]["db_ok"])

    def test_ready_route_reports_missing_env(self) -> None:
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "SUPABASE_DB_URL": "", "OPENAI_API_KEY": "", "DEMO_ACCESS_PASSWORD": ""},
            clear=False,
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "not_ready")
        self.assertIn("SUPABASE_DB_URL", response.json()["missing_env"])
        self.assertIn("OPENAI_API_KEY", response.json()["missing_env"])
        self.assertIn("DEMO_ACCESS_PASSWORD", response.json()["missing_env"])

    def test_protected_routes_require_demo_password_when_enabled(self) -> None:
        with patch.dict(os.environ, {"DEMO_ACCESS_PASSWORD": "demo-secret"}, clear=False):
            unauthorized = self.client.post("/api/v1/query", json={"message": "hello"})
            authorized = self.client.post(
                "/api/v1/query",
                json={"message": "hello"},
                headers=build_demo_access_headers("demo-secret"),
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.json()["error"]["code"], "DEMO_ACCESS_REQUIRED")
        self.assertIn("how_to_authenticate", unauthorized.json()["error"]["details"])
        self.assertNotEqual(authorized.status_code, 401)

    def test_rate_limiter_returns_429_for_query_route(self) -> None:
        headers = build_demo_access_headers("demo-secret")
        with patch.dict(
            os.environ,
            {
                "DEMO_ACCESS_PASSWORD": "demo-secret",
                "QUERY_RATE_LIMIT_MAX_REQUESTS": "1",
                "QUERY_RATE_LIMIT_WINDOW_SECONDS": "60",
            },
            clear=False,
        ):
            first = self.client.post("/api/v1/query", json={"message": "hello"}, headers=headers)
            second = self.client.post("/api/v1/query", json={"message": "hello"}, headers=headers)

        self.assertNotEqual(first.status_code, 429)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"]["code"], "RATE_LIMITED")

    def test_query_route_returns_request_id_header(self) -> None:
        with patch.dict(os.environ, {"DEMO_ACCESS_PASSWORD": "demo-secret"}, clear=False):
            response = self.client.post(
                "/api/v1/query",
                json={"message": "hello"},
                headers=build_demo_access_headers("demo-secret"),
            )

        self.assertIn("X-Request-Id", response.headers)
        self.assertEqual(response.headers["X-Request-Id"], response.json()["request_id"])

    def test_incident_route_returns_request_id_header(self) -> None:
        fake_incident = IncidentRecord(
            incident_id="inc_123",
            incident_code="INC-1234",
            title="Demo",
            status="mitigated",
            severity="sev2",
            service_area="payments",
            summary="Demo incident",
            customer_impact="Low",
            start_time=datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
            resolved_time=None,
        )
        with patch("app.api.incident_router.IncidentService.from_env") as incident_service:
            incident_service.return_value.get_incident.return_value = fake_incident
            incident_service.return_value.get_incident_timeline.return_value = []
            response = self.client.get("/api/v1/incidents/INC-1234")

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-Id", response.headers)
        self.assertEqual(response.headers["X-Request-Id"], response.json()["request_id"])

    def test_approval_route_returns_request_id_header(self) -> None:
        fake_requester = UserSummary(
            user_id="usr_requester",
            full_name="Morgan Support",
            role="support_analyst",
            email="morgan@example.com",
        )
        fake_approver = UserSummary(
            user_id="usr_approver",
            full_name="Dana Lee",
            role="ops_manager",
            email="dana@example.com",
        )
        fake_approval = ApprovalRecord(
            approval_id="apr_123",
            status="pending",
            request_type="incident_escalation",
            target_type="incident",
            target_id="inc_123",
            requested_at=datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
            decision_notes=None,
            next_step="Awaiting approver decision.",
            requester=fake_requester,
            approver=fake_approver,
            payload={"incident_code": "INC-1234"},
        )
        with patch("app.api.approval_router.ApprovalService.from_env") as approval_service:
            approval_service.return_value.get_approval_status.return_value = fake_approval
            response = self.client.get("/api/v1/approvals/apr_123")

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-Id", response.headers)
        self.assertEqual(response.headers["X-Request-Id"], response.json()["request_id"])

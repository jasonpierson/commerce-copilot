from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.auth import build_demo_access_headers
from app.api.main import app, rate_limiter


class DeploymentContractTests(TestCase):
    client = TestClient(app)

    def setUp(self) -> None:
        rate_limiter.reset()

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
        self.assertIn("how_to_authenticate", body["auth"])

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

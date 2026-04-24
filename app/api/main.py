from __future__ import annotations

from dataclasses import dataclass
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.approval_router import router as approval_router
from app.api.auth import (
    InMemoryRateLimiter,
    current_rate_limit_rules,
    demo_access_help_text,
    demo_access_denied_response,
    is_demo_access_allowed,
    rate_limit_exceeded_response,
    request_fingerprint,
)
from app.api.db import check_connectivity
from app.api.incident_router import router as incident_router
from app.api.query_router import router as query_router
from app.common.config import missing_required_runtime_env


PUBLIC_PATHS = {"/health", "/ready"}
rate_limiter = InMemoryRateLimiter()


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    app_env: str
    missing_env: list[str]
    db_ok: bool
    db_error: str | None = None


def build_readiness_report() -> ReadinessReport:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    missing_env = missing_required_runtime_env(app_env=app_env)
    db_ok = False
    db_error: str | None = None
    if not missing_env:
        db_ok, db_error = check_connectivity()
    return ReadinessReport(
        ready=not missing_env and db_ok,
        app_env=app_env,
        missing_env=missing_env,
        db_ok=db_ok,
        db_error=db_error,
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Governed Commerce Operations Copilot API",
        version="0.1.0",
        description=(
            "Backend slice for a governed operations copilot: retrieval-backed policy/process Q&A, "
            "structured incident/inventory reads, and an approval workflow with auditability."
        ),
        contact={
            "name": "Demo Maintainers",
            "url": "https://github.com/jasonpierson/commerce-copilot",
        },
        license_info={
            "name": "Proprietary demo; see repository",
            "url": "https://github.com/jasonpierson/commerce-copilot",
        },
        openapi_tags=[
            {"name": "query", "description": "Unified copilot entry points and analytics-style queries."},
            {"name": "approvals", "description": "Approval workflow, audit, browsing, and dashboard endpoints."},
            {"name": "incidents", "description": "Incident detail and timeline endpoints."},
        ],
    )

    @app.middleware("http")
    async def require_demo_access(request: Request, call_next):
        for rule in current_rate_limit_rules():
            if request.method == rule.method and rule.path_pattern.match(request.url.path):
                fingerprint = request_fingerprint(
                    path=request.url.path,
                    method=request.method,
                    forwarded_for=request.headers.get("X-Forwarded-For"),
                    client_host=request.client.host if request.client else None,
                    user_id=request.headers.get("X-User-Id"),
                )
                allowed, retry_after = rate_limiter.check(
                    key=fingerprint,
                    limit=rule.limit,
                    window_seconds=rule.window_seconds,
                )
                if not allowed:
                    return rate_limit_exceeded_response(
                        rule_name=rule.name,
                        retry_after_seconds=retry_after,
                    )

        if request.url.path not in PUBLIC_PATHS and not is_demo_access_allowed(
            authorization_header=request.headers.get("Authorization"),
            password_header=request.headers.get("X-Demo-Password"),
        ):
            return demo_access_denied_response()
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> JSONResponse:
        report = build_readiness_report()
        status_code = 200 if report.ready else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if report.ready else "not_ready",
                "app_env": report.app_env,
                "checks": {
                    "config_ok": not report.missing_env,
                    "db_ok": report.db_ok,
                },
                "missing_env": report.missing_env,
                "db_error": report.db_error,
            },
        )

    @app.get("/", include_in_schema=False, response_model=None)
    def root(request: Request) -> JSONResponse | HTMLResponse:
        payload = {
            "name": "Governed Commerce Operations Copilot API",
            "description": (
                "Private hosted demo for governed operations support: retrieval-backed guidance, "
                "structured incident/inventory answers, and approval-gated escalation workflows."
            ),
            "next_steps": [
                {"label": "Open interactive API docs", "href": "/docs"},
                {"label": "Check liveness", "href": "/health"},
                {"label": "Check readiness", "href": "/ready"},
            ],
            "auth": {
                "protected_routes": "All routes except /health and /ready when DEMO_ACCESS_PASSWORD is set.",
                "how_to_authenticate": demo_access_help_text(),
            },
        }
        accepts_html = "text/html" in request.headers.get("accept", "").lower()
        if accepts_html:
            items = "".join(
                f"<li><a href='{item['href']}'>{item['label']}</a></li>" for item in payload["next_steps"]
            )
            html = f"""
            <html>
              <head><title>{payload['name']}</title></head>
              <body>
                <h1>{payload['name']}</h1>
                <p>{payload['description']}</p>
                <h2>Next steps</h2>
                <ul>{items}</ul>
                <h2>Authentication</h2>
                <p>{payload['auth']['protected_routes']}</p>
                <p>{payload['auth']['how_to_authenticate']}</p>
              </body>
            </html>
            """
            return HTMLResponse(html)
        return JSONResponse(payload)

    app.include_router(query_router, prefix="/api/v1")
    app.include_router(incident_router, prefix="/api/v1")
    app.include_router(approval_router, prefix="/api/v1")
    return app


app = create_app()

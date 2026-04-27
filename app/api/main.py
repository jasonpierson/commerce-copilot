from __future__ import annotations

from dataclasses import dataclass
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

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
from app.common.config import APP_NAME, get_build_metadata, missing_required_runtime_env


PUBLIC_PATHS = {"/", "/health", "/ready", "/version"}
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
        title=APP_NAME,
        version=get_build_metadata().app_version,
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

    @app.get("/version")
    def version() -> dict[str, str]:
        metadata = get_build_metadata()
        return {
            "app_name": metadata.app_name,
            "app_version": metadata.app_version,
            "git_sha": metadata.git_sha,
            "build_timestamp": metadata.build_timestamp,
            "app_env": metadata.app_env,
        }

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", include_in_schema=False, response_model=None)
    def root(request: Request) -> JSONResponse | HTMLResponse:
        metadata = get_build_metadata()
        payload = {
            "name": metadata.app_name,
            "description": (
                "Private hosted demo for governed operations support: retrieval-backed guidance, "
                "structured incident/inventory answers, and approval-gated escalation workflows."
            ),
            "next_steps": [
                {"label": "Open interactive API docs", "href": "/docs"},
                {"label": "Check liveness", "href": "/health"},
                {"label": "Check readiness", "href": "/ready"},
                {"label": "Check deployed version metadata", "href": "/version"},
            ],
            "auth": {
                "protected_routes": "All routes except /health and /ready when DEMO_ACCESS_PASSWORD is set.",
                "how_to_authenticate": demo_access_help_text(),
            },
            "build": {
                "app_version": metadata.app_version,
                "git_sha": metadata.git_sha,
                "build_timestamp": metadata.build_timestamp,
                "app_env": metadata.app_env,
            },
            "reviewer_notes": {
                "streamlit": "Streamlit is a local-only reviewer companion and is not hosted on this URL.",
            },
        }
        accepts_html = "text/html" in request.headers.get("accept", "").lower()
        if accepts_html:
            items = "".join(
                f"<li><a href='{item['href']}'>{item['label']}</a></li>" for item in payload["next_steps"]
            )
            html = f"""
            <html>
              <head>
                <title>{payload['name']}</title>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <style>
                  :root {{
                    color-scheme: light;
                    --bg: #f7f4ec;
                    --panel: #fffdf8;
                    --ink: #1f2933;
                    --muted: #5b6770;
                    --accent: #0b6bcb;
                    --border: #e5dfd0;
                  }}
                  body {{
                    margin: 0;
                    font-family: Georgia, "Times New Roman", serif;
                    background: radial-gradient(circle at top, #fffaf0 0%, var(--bg) 55%, #f0eadc 100%);
                    color: var(--ink);
                  }}
                  main {{
                    max-width: 760px;
                    margin: 48px auto;
                    padding: 0 20px 48px;
                  }}
                  .panel {{
                    background: var(--panel);
                    border: 1px solid var(--border);
                    border-radius: 18px;
                    padding: 28px;
                    box-shadow: 0 14px 40px rgba(31, 41, 51, 0.08);
                  }}
                  h1, h2 {{
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                  }}
                  p, li {{
                    font-size: 1rem;
                    line-height: 1.6;
                  }}
                  .eyebrow {{
                    display: inline-block;
                    margin-bottom: 12px;
                    padding: 4px 10px;
                    border-radius: 999px;
                    background: #e6f0fb;
                    color: var(--accent);
                    font-size: 0.86rem;
                    letter-spacing: 0.02em;
                  }}
                  ul {{
                    padding-left: 1.2rem;
                  }}
                  a {{
                    color: var(--accent);
                  }}
                  .grid {{
                    display: grid;
                    gap: 16px;
                  }}
                  @media (min-width: 720px) {{
                    .grid {{
                      grid-template-columns: 1fr 1fr;
                    }}
                  }}
                  .card {{
                    border: 1px solid var(--border);
                    border-radius: 14px;
                    padding: 16px 18px;
                    background: #fff;
                  }}
                  code {{
                    background: #f3efe6;
                    border-radius: 6px;
                    padding: 2px 6px;
                  }}
                </style>
              </head>
              <body>
                <main>
                  <section class="panel">
                    <span class="eyebrow">Hosted reviewer entrypoint</span>
                    <h1>{payload['name']}</h1>
                    <p>{payload['description']}</p>
                    <div class="grid">
                      <div class="card">
                        <h2>Next steps</h2>
                        <ul>{items}</ul>
                      </div>
                      <div class="card">
                        <h2>Authentication</h2>
                        <p>{payload['auth']['protected_routes']}</p>
                        <p>{payload['auth']['how_to_authenticate']}</p>
                      </div>
                      <div class="card">
                        <h2>Build metadata</h2>
                        <ul>
                          <li>Version: <code>{payload['build']['app_version']}</code></li>
                          <li>Git SHA: <code>{payload['build']['git_sha']}</code></li>
                          <li>Built at: <code>{payload['build']['build_timestamp']}</code></li>
                          <li>Environment: <code>{payload['build']['app_env']}</code></li>
                        </ul>
                      </div>
                      <div class="card">
                        <h2>Reviewer note</h2>
                        <p>{payload['reviewer_notes']['streamlit']}</p>
                      </div>
                    </div>
                  </section>
                </main>
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

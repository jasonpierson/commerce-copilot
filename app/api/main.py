from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.approval_router import router as approval_router
from app.api.auth import demo_access_denied_response, is_demo_access_allowed
from app.api.incident_router import router as incident_router
from app.api.query_router import router as query_router


PUBLIC_PATHS = {"/health"}


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
        if request.url.path not in PUBLIC_PATHS and not is_demo_access_allowed(
            authorization_header=request.headers.get("Authorization"),
            password_header=request.headers.get("X-Demo-Password"),
        ):
            return demo_access_denied_response()
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "Governed Commerce Operations Copilot API",
                "docs": "/docs",
                "health": "/health",
                "query": "/api/v1/query",
            }
        )

    app.include_router(query_router, prefix="/api/v1")
    app.include_router(incident_router, prefix="/api/v1")
    app.include_router(approval_router, prefix="/api/v1")
    return app


app = create_app()

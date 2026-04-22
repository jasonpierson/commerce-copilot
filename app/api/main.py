from __future__ import annotations

from fastapi import FastAPI

from app.api.approval_router import router as approval_router
from app.api.incident_router import router as incident_router
from app.api.query_router import router as query_router


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
            "url": "https://github.com/",
        },
        license_info={
            "name": "Proprietary demo; see repository",
            "url": "https://github.com/",
        },
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(query_router, prefix="/api/v1")
    app.include_router(incident_router, prefix="/api/v1")
    app.include_router(approval_router, prefix="/api/v1")
    return app


app = create_app()

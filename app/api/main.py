from __future__ import annotations

from fastapi import FastAPI

from app.api.query_router import router as query_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Governed Commerce Operations Copilot API",
        version="0.1.0",
        description="First backend slice for policy/process Q&A over the retrieval layer.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(query_router, prefix="/api/v1")
    return app


app = create_app()

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Header, status
from fastapi.responses import JSONResponse

from app.api.auth import resolve_demo_principal
from app.api.query_service import QueryService, UnsupportedRouteError
from app.api.schemas import ErrorDetail, ErrorResponse, QueryRequest, QueryResponse, SupportedUserRole
from app.retrieval.exceptions import RetrievalError

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    summary="Unified copilot entry point",
    description=(
        "Classifies the user message and returns a composed answer that can include retrieval-backed policy Q&A, "
        "structured incident summaries, escalation guidance, inventory lookups, or approval analytics."
    ),
    response_model=QueryResponse,
    responses={
        501: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def query(
    request: QueryRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: SupportedUserRole | None = Header(default=None, alias="X-User-Role"),
) -> QueryResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    service = QueryService()
    principal = resolve_demo_principal(
        header_user_id=x_user_id,
        header_user_role=x_user_role,
        fallback_user_id=request.user_id,
        fallback_user_role=request.user_role,
    )
    request = request.model_copy(
        update={"user_id": principal.user_id, "user_role": principal.user_role}
    )

    try:
        return service.handle_query(request, request_id=request_id)
    except UnsupportedRouteError as exc:
        error = ErrorResponse(
            request_id=request_id,
            error=ErrorDetail(
                code="ROUTE_NOT_IMPLEMENTED",
                message=str(exc),
                details={"route_type": exc.route_type},
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=error.model_dump(),
        )
    except RetrievalError as exc:
        error = ErrorResponse(
            request_id=request_id,
            error=ErrorDetail(
                code="RETRIEVAL_FAILED",
                message="The retrieval layer could not complete the request.",
                details={"cause": str(exc)},
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error.model_dump(),
        )
    except Exception as exc:
        error = ErrorResponse(
            request_id=request_id,
            error=ErrorDetail(
                code="BACKEND_EXECUTION_FAILED",
                message="The backend could not complete the request.",
                details={"cause": type(exc).__name__},
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error.model_dump(),
        )

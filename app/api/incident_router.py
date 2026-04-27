from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from app.api.incident_service import IncidentService
from app.api.schemas import ErrorDetail, ErrorResponse, IncidentDetailData, IncidentDetailResponse, QueryResponseMeta

router = APIRouter(tags=["incidents"])


def _set_request_id_header(response: Response, request_id: str) -> None:
    response.headers["X-Request-Id"] = request_id


def _error_json_response(*, request_id: str, status_code: int, error: ErrorResponse) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(),
        headers={"X-Request-Id": request_id},
    )


@router.get(
    "/incidents/{incident_code}",
    summary="Get structured incident detail and timeline",
    description="Returns the incident record and timeline events for a known incident code such as `INC-1091`.",
    response_model=IncidentDetailResponse,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def get_incident_detail(incident_code: str, response: Response) -> IncidentDetailResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    _set_request_id_header(response, request_id)
    service = IncidentService.from_env()

    try:
        incident = service.get_incident(incident_code)
        if not incident:
            error = ErrorResponse(
                request_id=request_id,
                error=ErrorDetail(
                    code="INCIDENT_NOT_FOUND",
                    message=f"Incident {incident_code.upper()} was not found.",
                ),
            )
            return _error_json_response(
                request_id=request_id,
                status_code=status.HTTP_404_NOT_FOUND,
                error=error,
            )

        timeline = service.get_incident_timeline(incident.incident_id)
        return IncidentDetailResponse(
            request_id=request_id,
            data=IncidentDetailData(incident=incident, incident_timeline=timeline),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_incident", "get_incident_timeline"],
                approval_involved=False,
            ),
        )
    except Exception as exc:
        error = ErrorResponse(
            request_id=request_id,
            error=ErrorDetail(
                code="INCIDENT_LOOKUP_FAILED",
                message="The backend could not load the incident detail.",
                details={"cause": type(exc).__name__},
            ),
        )
        return _error_json_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error=error,
        )

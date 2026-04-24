from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.incident_service import IncidentService
from app.api.schemas import ErrorDetail, ErrorResponse, IncidentDetailData, IncidentDetailResponse, QueryResponseMeta

router = APIRouter(tags=["incidents"])


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
def get_incident_detail(incident_code: str) -> IncidentDetailResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
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
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error.model_dump())

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
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error.model_dump(),
        )

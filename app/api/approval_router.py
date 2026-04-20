from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.approval_service import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    ApprovalPermissionError,
    ApprovalService,
    ApprovalValidationError,
)
from app.api.incident_service import IncidentService
from app.api.schemas import (
    ApprovalAuditData,
    ApprovalAuditResponse,
    ApprovalData,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalRequestResponse,
    ApprovalStatusResponse,
    CreateEscalationRequest,
    ErrorDetail,
    ErrorResponse,
    QueryResponseMeta,
)

router = APIRouter(tags=["approvals"])


def _error_response(
    *,
    request_id: str,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    error = ErrorResponse(
        request_id=request_id,
        error=ErrorDetail(code=code, message=message, details=details or {}),
    )
    return JSONResponse(status_code=status_code, content=error.model_dump())


@router.post(
    "/escalations",
    response_model=ApprovalRequestResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def create_incident_escalation(
    request: CreateEscalationRequest,
) -> ApprovalRequestResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"

    try:
        incident_service = IncidentService.from_env()
        incident = incident_service.get_incident(request.incident_code)
        if not incident:
            return _error_response(
                request_id=request_id,
                status_code=status.HTTP_404_NOT_FOUND,
                code="INCIDENT_NOT_FOUND",
                message=f"Incident {request.incident_code.upper()} was not found.",
            )

        approval = ApprovalService.from_env().create_incident_escalation_request(
            incident_id=incident.incident_id,
            incident_code=incident.incident_code,
            requested_by_user_id=request.requested_by_user_id,
            requested_by_role=request.requested_by_role,
            escalation_reason=request.escalation_reason,
            proposed_priority=request.proposed_priority,
            draft_summary=request.draft_summary,
            request_id=request_id,
        )
        return ApprovalRequestResponse(
            request_id=request_id,
            data=ApprovalData(approval=approval),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["create_incident_escalation_request"],
                approval_involved=True,
            ),
        )
    except ApprovalPermissionError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_403_FORBIDDEN,
            code="APPROVAL_PERMISSION_DENIED",
            message=str(exc),
        )
    except ApprovalValidationError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="APPROVAL_VALIDATION_FAILED",
            message=str(exc),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_REQUEST_FAILED",
            message="The backend could not create the approval request.",
            details={"cause": type(exc).__name__},
        )


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalStatusResponse,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def get_approval_status(approval_id: str) -> ApprovalStatusResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    try:
        approval = ApprovalService.from_env().get_approval_status(approval_id)
        return ApprovalStatusResponse(
            request_id=request_id,
            data=ApprovalData(approval=approval),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_approval_status"],
                approval_involved=True,
            ),
        )
    except ApprovalNotFoundError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_404_NOT_FOUND,
            code="APPROVAL_NOT_FOUND",
            message=str(exc),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_STATUS_FAILED",
            message="The backend could not load the approval status.",
            details={"cause": type(exc).__name__},
        )


@router.get(
    "/approvals/{approval_id}/audit",
    response_model=ApprovalAuditResponse,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def get_approval_audit(approval_id: str) -> ApprovalAuditResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    service = ApprovalService.from_env()
    try:
        approval = service.get_approval_status(approval_id)
        audit_events = service.get_approval_audit(approval_id)
        return ApprovalAuditResponse(
            request_id=request_id,
            data=ApprovalAuditData(approval=approval, audit_events=audit_events),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_approval_status", "get_approval_audit"],
                approval_involved=True,
            ),
        )
    except ApprovalNotFoundError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_404_NOT_FOUND,
            code="APPROVAL_NOT_FOUND",
            message=str(exc),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_AUDIT_FAILED",
            message="The backend could not load the approval audit history.",
            details={"cause": type(exc).__name__},
        )


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalDecisionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
) -> ApprovalDecisionResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"

    try:
        approval = ApprovalService.from_env().decide_approval(
            approval_id=approval_id,
            decider_user_id=request.decider_user_id,
            decider_role=request.decider_role,
            decision=request.decision,
            decision_notes=request.decision_notes,
            request_id=request_id,
        )
        return ApprovalDecisionResponse(
            request_id=request_id,
            data=ApprovalData(approval=approval),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["decide_approval"],
                approval_involved=True,
            ),
        )
    except ApprovalPermissionError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_403_FORBIDDEN,
            code="APPROVAL_PERMISSION_DENIED",
            message=str(exc),
        )
    except ApprovalValidationError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="APPROVAL_VALIDATION_FAILED",
            message=str(exc),
        )
    except ApprovalNotFoundError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_404_NOT_FOUND,
            code="APPROVAL_NOT_FOUND",
            message=str(exc),
        )
    except ApprovalConflictError as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_409_CONFLICT,
            code="APPROVAL_CONFLICT",
            message=str(exc),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_DECISION_FAILED",
            message="The backend could not apply the approval decision.",
            details={"cause": type(exc).__name__},
        )

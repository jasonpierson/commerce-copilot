from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import JSONResponse

from app.api.auth import resolve_demo_principal
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
    ApprovalDashboardData,
    ApprovalDashboardResponse,
    ApprovalDashboardSummaryData,
    ApprovalDashboardSummaryResponse,
    ApprovalListData,
    ApprovalListResponse,
    ApprovalAuditResponse,
    ApprovalData,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalRequestResponse,
    ApprovalStatusResponse,
    CreateEscalationRequest,
    ErrorDetail,
    ErrorResponse,
    ApiLink,
    OperatorDashboardData,
    OperatorDashboardResponse,
    QueryResponseMeta,
    SupportedUserRole,
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
    summary="Create a pending escalation approval request for an incident",
    description=(
        "Creates a pending approval request tied to an incident code. Decisions must be taken by `ops_manager` or `admin`."
    ),
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
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: SupportedUserRole | None = Header(default=None, alias="X-User-Role"),
) -> ApprovalRequestResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    principal = resolve_demo_principal(
        header_user_id=x_user_id,
        header_user_role=x_user_role,
        fallback_user_id=request.requested_by_user_id,
        fallback_user_role=request.requested_by_role,
    )

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
            requested_by_user_id=principal.user_id,
            requested_by_role=principal.user_role,
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
    "/approvals",
    summary="List approvals with optional filters",
    description="Browse approval work items with optional status, incident, and requester filters.",
    response_model=ApprovalListResponse,
    responses={
        502: {"model": ErrorResponse},
    },
)
def list_approvals(
    approval_status: str | None = Query(default=None, alias="status", pattern="^(pending|approved|rejected)$"),
    incident_code: str | None = Query(default=None, pattern="^INC-\\d{3,}$"),
    requester: str | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="requested_at", pattern="^(requested_at|decided_at|status)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> ApprovalListResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    try:
        approvals, total_count = ApprovalService.from_env().list_approvals(
            status=approval_status,
            incident_code=incident_code,
            requester=requester,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        tool_name = "list_approvals"
        if approval_status:
            tool_name = f"{tool_name}:{approval_status}"
        return ApprovalListResponse(
            request_id=request_id,
            data=ApprovalListData(
                approvals=approvals,
                total_count=total_count,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                status_filter=approval_status,
                incident_code_filter=incident_code,
                requester_filter=requester,
            ),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=[tool_name],
                approval_involved=bool(approvals),
            ),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_LIST_FAILED",
            message="The backend could not load approval work items.",
            details={"cause": type(exc).__name__},
        )


@router.get(
    "/approvals/dashboard",
    summary="Approval dashboard buckets and metrics",
    description="Grouped approvals by status plus headline metrics and trends.",
    response_model=ApprovalDashboardResponse,
    responses={
        502: {"model": ErrorResponse},
    },
)
def get_approval_dashboard(
    incident_code: str | None = Query(default=None, pattern="^INC-\\d{3,}$"),
    requester: str | None = Query(default=None),
    page_size_per_bucket: int = Query(default=5, ge=1, le=25),
) -> ApprovalDashboardResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    try:
        buckets, metrics = ApprovalService.from_env().get_approval_dashboard(
            incident_code=incident_code,
            requester=requester,
            page_size_per_bucket=page_size_per_bucket,
        )
        total_count = sum(bucket.count for bucket in buckets)
        return ApprovalDashboardResponse(
            request_id=request_id,
            data=ApprovalDashboardData(
                buckets=buckets,
                total_count=total_count,
                page_size_per_bucket=page_size_per_bucket,
                metrics=metrics,
                incident_code_filter=incident_code,
                requester_filter=requester,
            ),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_approval_dashboard"],
                approval_involved=total_count > 0,
            ),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_DASHBOARD_FAILED",
            message="The backend could not load the approval dashboard.",
            details={"cause": type(exc).__name__},
        )


@router.get(
    "/approvals/dashboard/summary",
    summary="Approval dashboard summary (headline + top risks)",
    description="Concise summary of headline metrics and top risks.",
    response_model=ApprovalDashboardSummaryResponse,
    responses={
        502: {"model": ErrorResponse},
    },
)
def get_approval_dashboard_summary(
    incident_code: str | None = Query(default=None, pattern="^INC-\\d{3,}$"),
    requester: str | None = Query(default=None),
    min_pending_age_minutes: int | None = Query(default=None, ge=0, le=100000),
) -> ApprovalDashboardSummaryResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    try:
        metrics, top_risks = ApprovalService.from_env().get_approval_dashboard_summary(
            incident_code=incident_code,
            requester=requester,
            min_pending_age_minutes=min_pending_age_minutes,
        )
        answer = (
            f"Approval summary: {metrics.pending_count} pending item(s); "
            f"{metrics.approvals_created_last_24h} created in the last 24h; "
            f"{metrics.approvals_decided_last_24h} decided in the last 24h."
        )
        if top_risks:
            answer += " Top risks: " + "; ".join(
                f"{risk.title}: {risk.detail}" for risk in top_risks[:3]
            )
        return ApprovalDashboardSummaryResponse(
            request_id=request_id,
            data=ApprovalDashboardSummaryData(
                answer=answer,
                headline_metrics=metrics,
                top_risks=top_risks,
                incident_code_filter=incident_code,
                requester_filter=requester,
                min_pending_age_minutes=min_pending_age_minutes,
            ),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_approval_dashboard_summary"],
                approval_involved=metrics.pending_count > 0,
            ),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="APPROVAL_DASHBOARD_SUMMARY_FAILED",
            message="The backend could not load the approval dashboard summary.",
            details={"cause": type(exc).__name__},
        )


@router.get(
    "/operator/dashboard",
    summary="Operator-oriented dashboard",
    description="UI-friendly shape combining summary, buckets, and links.",
    response_model=OperatorDashboardResponse,
    responses={
        502: {"model": ErrorResponse},
    },
)
def get_operator_dashboard(
    incident_code: str | None = Query(default=None, pattern="^INC-\\d{3,}$"),
    requester: str | None = Query(default=None),
    min_pending_age_minutes: int | None = Query(default=None, ge=0, le=100000),
    page_size_per_bucket: int = Query(default=5, ge=1, le=25),
) -> OperatorDashboardResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    try:
        service = ApprovalService.from_env()
        buckets, metrics = service.get_approval_dashboard(
            incident_code=incident_code,
            requester=requester,
            page_size_per_bucket=page_size_per_bucket,
        )
        top_risks = service.get_approval_dashboard_summary(
            incident_code=incident_code,
            requester=requester,
            min_pending_age_minutes=min_pending_age_minutes,
        )[1]
        answer = (
            f"Approval summary: {metrics.pending_count} pending item(s); "
            f"{metrics.approvals_created_last_24h} created in the last 24h; "
            f"{metrics.approvals_decided_last_24h} decided in the last 24h."
        )
        if top_risks:
            answer += " Top risks: " + "; ".join(
                f"{risk.title}: {risk.detail}" for risk in top_risks[:3]
            )
        summary_data = ApprovalDashboardSummaryData(
            answer=answer,
            headline_metrics=metrics,
            top_risks=top_risks,
            incident_code_filter=incident_code,
            requester_filter=requester,
            min_pending_age_minutes=min_pending_age_minutes,
        )
        dashboard_data = ApprovalDashboardData(
            buckets=buckets,
            total_count=sum(bucket.count for bucket in buckets),
            page_size_per_bucket=page_size_per_bucket,
            metrics=metrics,
            incident_code_filter=incident_code,
            requester_filter=requester,
        )
        links = [
            ApiLink(
                rel="approval_dashboard",
                href="/api/v1/approvals/dashboard",
                method="GET",
                description="Browse grouped approval buckets.",
            ),
            ApiLink(
                rel="approval_dashboard_summary",
                href="/api/v1/approvals/dashboard/summary",
                method="GET",
                description="View headline approval metrics and top risks.",
            ),
        ]
        return OperatorDashboardResponse(
            request_id=request_id,
            data=OperatorDashboardData(
                summary=summary_data,
                approval_dashboard=dashboard_data,
                links=links,
            ),
            meta=QueryResponseMeta(
                citations_included=False,
                tools_used=["get_approval_dashboard", "get_approval_dashboard_summary"],
                approval_involved=metrics.pending_count > 0,
            ),
        )
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="OPERATOR_DASHBOARD_FAILED",
            message="The backend could not load the operator dashboard.",
            details={"cause": type(exc).__name__},
        )


@router.get(
    "/approvals/{approval_id}",
    summary="Get approval status",
    description="Returns the structured approval record and current decision state.",
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
    summary="Get approval audit history",
    description="Audit trail for a given approval ID, optionally filtered by event type.",
    response_model=ApprovalAuditResponse,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def get_approval_audit(
    approval_id: str,
    event_type: str | None = Query(default=None, pattern="^(approval_requested|approval_decided)$"),
) -> ApprovalAuditResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    service = ApprovalService.from_env()
    try:
        approval = service.get_approval_status(approval_id)
        audit_events = service.get_approval_audit(approval_id, event_type=event_type)
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
    summary="Apply an approval decision (authorized roles only)",
    description="Only `ops_manager` or `admin` may decide approvals in the demo auth model.",
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
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: SupportedUserRole | None = Header(default=None, alias="X-User-Role"),
) -> ApprovalDecisionResponse | JSONResponse:
    request_id = f"req_{uuid4().hex[:12]}"
    principal = resolve_demo_principal(
        header_user_id=x_user_id,
        header_user_role=x_user_role,
        fallback_user_id=request.decider_user_id,
        fallback_user_role=request.decider_role,
    )

    try:
        approval = ApprovalService.from_env().decide_approval(
            approval_id=approval_id,
            decider_user_id=principal.user_id,
            decider_role=principal.user_role,
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

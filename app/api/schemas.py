from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SupportedRouteType = Literal[
    "policy_qa",
    "structured_lookup",
    "incident_summary",
    "escalation_guidance",
]
SupportedUserRole = Literal[
    "support_analyst",
    "engineering_support",
    "ops_manager",
    "admin",
]
ApproverUserRole = Literal["ops_manager", "admin"]
ApprovalStatusValue = Literal["pending", "approved", "rejected"]
ApprovalDecisionValue = Literal["approved", "rejected"]
EscalationPriority = Literal["medium", "high", "critical"]


class QueryRequest(BaseModel):
    message: str = Field(min_length=1, description="Natural-language user query.")
    conversation_id: str | None = Field(default=None)
    user_id: str = Field(default="demo-support-001")
    user_role: SupportedUserRole = Field(default="support_analyst")
    top_k: int = Field(default=5, ge=1, le=10)
    route_type_override: SupportedRouteType | None = Field(default=None)


class Citation(BaseModel):
    doc_key: str
    title: str
    section_title: str | None = None
    relevance_score: float


class ProductMatch(BaseModel):
    product_id: str
    sku: str
    product_name: str
    category: str | None = None
    brand: str | None = None
    status: str | None = None


class InventoryResult(BaseModel):
    location_code: str | None = None
    location_name: str | None = None
    region: str | None = None
    quantity_available: int
    inventory_status: str | None = None


class IncidentRecord(BaseModel):
    incident_id: str
    incident_code: str
    title: str
    status: str
    severity: str
    service_area: str | None = None
    summary: str | None = None
    customer_impact: str | None = None
    start_time: datetime | None = None
    resolved_time: datetime | None = None


class IncidentEvent(BaseModel):
    event_time: datetime
    event_type: str
    actor: str | None = None
    event_summary: str


class ApiLink(BaseModel):
    rel: str
    href: str
    method: Literal["GET", "POST"] = "GET"
    description: str | None = None


class ApprovalSuggestion(BaseModel):
    action_type: Literal["incident_escalation"] = "incident_escalation"
    reason: str
    proposed_priority: EscalationPriority
    incident_code: str
    create_request: ApiLink


class QueryResponseData(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    product: ProductMatch | None = None
    inventory_results: list[InventoryResult] = Field(default_factory=list)
    approval: ApprovalRecord | None = None
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    approval_dashboard: list["ApprovalDashboardBucket"] = Field(default_factory=list)
    approval_dashboard_metrics: ApprovalDashboardMetrics | None = None
    approval_audit: list["ApprovalAuditEvent"] = Field(default_factory=list)
    incident: IncidentRecord | None = None
    incident_timeline: list[IncidentEvent] = Field(default_factory=list)
    customer_impact: str | None = None
    recommended_next_step: str | None = None
    links: list[ApiLink] = Field(default_factory=list)
    approval_suggestion: ApprovalSuggestion | None = None


class QueryResponseMeta(BaseModel):
    citations_included: bool = False
    tools_used: list[str] = Field(default_factory=list)
    approval_involved: bool = False


class QueryResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: SupportedRouteType
    data: QueryResponseData
    meta: QueryResponseMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    request_id: str
    status: Literal["error"] = "error"
    error: ErrorDetail


class UserSummary(BaseModel):
    user_id: str
    full_name: str
    role: SupportedUserRole
    email: str | None = None


class IncidentDetailData(BaseModel):
    incident: IncidentRecord
    incident_timeline: list[IncidentEvent] = Field(default_factory=list)


class IncidentDetailResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["incident_detail"] = "incident_detail"
    data: IncidentDetailData
    meta: QueryResponseMeta


class CreateEscalationRequest(BaseModel):
    incident_code: str = Field(min_length=1)
    escalation_reason: str = Field(min_length=1)
    proposed_priority: EscalationPriority
    draft_summary: str = Field(min_length=1)
    requested_by_user_id: str = Field(default="demo-support-001")
    requested_by_role: SupportedUserRole = Field(default="support_analyst")


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecisionValue
    decision_notes: str | None = None
    decider_user_id: str = Field(default="demo-ops-manager-001")
    decider_role: SupportedUserRole = Field(default="ops_manager")


class ApprovalRecord(BaseModel):
    approval_id: str
    status: ApprovalStatusValue
    request_type: str
    target_type: str
    target_id: str
    requested_at: datetime
    decided_at: datetime | None = None
    decision_notes: str | None = None
    next_step: str | None = None
    requester: UserSummary | None = None
    approver: UserSummary | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalAuditEvent(BaseModel):
    audit_event_id: str
    event_type: str
    occurred_at: datetime
    route_type: str | None = None
    tool_name: str | None = None
    request_id: str | None = None
    actor: UserSummary | None = None
    target_type: str | None = None
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalData(BaseModel):
    approval: ApprovalRecord


class ApprovalAuditData(BaseModel):
    approval: ApprovalRecord
    audit_events: list[ApprovalAuditEvent] = Field(default_factory=list)


class ApprovalListData(BaseModel):
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20
    sort_by: Literal["requested_at", "decided_at", "status"] = "requested_at"
    sort_order: Literal["asc", "desc"] = "desc"
    status_filter: ApprovalStatusValue | None = None
    incident_code_filter: str | None = None
    requester_filter: str | None = None


class ApprovalDashboardBucket(BaseModel):
    status: ApprovalStatusValue
    count: int = 0
    approvals: list[ApprovalRecord] = Field(default_factory=list)


class ApprovalPendingOwnerMetric(BaseModel):
    approver_name: str
    approver_role: SupportedUserRole | None = None
    pending_count: int = 0


class ApprovalOldestPendingItemMetric(BaseModel):
    approval_id: str
    approver_name: str
    approver_role: SupportedUserRole | None = None
    requester_name: str | None = None
    requester_role: SupportedUserRole | None = None
    incident_code: str | None = None
    requested_at: datetime
    pending_age_minutes: int = 0


class ApprovalRequesterLoadMetric(BaseModel):
    requester_name: str
    requester_role: SupportedUserRole | None = None
    pending_count: int = 0


class ApprovalIncidentPressureMetric(BaseModel):
    incident_code: str
    pending_count: int = 0


class ApprovalDailyTrendBucket(BaseModel):
    bucket_date: date
    approvals_created: int = 0
    approvals_decided: int = 0


class ApprovalAgedIncidentMetric(BaseModel):
    incident_code: str
    pending_count: int = 0
    oldest_pending_age_minutes: int = 0


class ApprovalDashboardSummaryRisk(BaseModel):
    risk_type: str
    title: str
    detail: str
    metric_value: int | None = None
    incident_code: str | None = None
    approval_id: str | None = None


class ApprovalDashboardMetrics(BaseModel):
    pending_count: int = 0
    approvals_created_last_24h: int = 0
    approvals_decided_last_24h: int = 0
    approvals_created_last_7d: int = 0
    approvals_decided_last_7d: int = 0
    oldest_pending_age_minutes: int | None = None
    oldest_pending_item: ApprovalOldestPendingItemMetric | None = None
    pending_by_priority: dict[str, int] = Field(default_factory=dict)
    pending_by_owner: list[ApprovalPendingOwnerMetric] = Field(default_factory=list)
    pending_by_requester: list[ApprovalRequesterLoadMetric] = Field(default_factory=list)
    pending_by_incident: list[ApprovalIncidentPressureMetric] = Field(default_factory=list)
    daily_trends_7d: list[ApprovalDailyTrendBucket] = Field(default_factory=list)
    aged_pending_incidents: list[ApprovalAgedIncidentMetric] = Field(default_factory=list)


class ApprovalDashboardData(BaseModel):
    buckets: list[ApprovalDashboardBucket] = Field(default_factory=list)
    total_count: int = 0
    page_size_per_bucket: int = 5
    metrics: ApprovalDashboardMetrics = Field(default_factory=ApprovalDashboardMetrics)
    incident_code_filter: str | None = None
    requester_filter: str | None = None


class ApprovalDashboardSummaryData(BaseModel):
    answer: str
    headline_metrics: ApprovalDashboardMetrics = Field(default_factory=ApprovalDashboardMetrics)
    top_risks: list[ApprovalDashboardSummaryRisk] = Field(default_factory=list)
    incident_code_filter: str | None = None
    requester_filter: str | None = None
    min_pending_age_minutes: int | None = None


class ApprovalRequestResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_request"] = "approval_request"
    data: ApprovalData
    meta: QueryResponseMeta


class ApprovalStatusResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_status"] = "approval_status"
    data: ApprovalData
    meta: QueryResponseMeta


class ApprovalDecisionResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_decision"] = "approval_decision"
    data: ApprovalData
    meta: QueryResponseMeta


class ApprovalAuditResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_audit"] = "approval_audit"
    data: ApprovalAuditData
    meta: QueryResponseMeta


class ApprovalListResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_list"] = "approval_list"
    data: ApprovalListData
    meta: QueryResponseMeta


class ApprovalDashboardResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_dashboard"] = "approval_dashboard"
    data: ApprovalDashboardData
    meta: QueryResponseMeta


class ApprovalDashboardSummaryResponse(BaseModel):
    request_id: str
    status: Literal["success"] = "success"
    route_type: Literal["approval_dashboard_summary"] = "approval_dashboard_summary"
    data: ApprovalDashboardSummaryData
    meta: QueryResponseMeta

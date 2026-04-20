from __future__ import annotations

from datetime import datetime
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

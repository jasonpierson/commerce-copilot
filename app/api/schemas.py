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


class QueryResponseData(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    product: ProductMatch | None = None
    inventory_results: list[InventoryResult] = Field(default_factory=list)
    incident: IncidentRecord | None = None
    incident_timeline: list[IncidentEvent] = Field(default_factory=list)
    customer_impact: str | None = None
    recommended_next_step: str | None = None


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

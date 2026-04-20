from __future__ import annotations

from .config import RetrievalConfig
from .exceptions import RetrievalValidationError
from .models import RetrievalPolicy, RetrievalQueryRequest

ROLE_TO_AUDIENCE = {
    "support_analyst": {"support", "multi_role"},
    "engineering_support": {"engineering_support", "multi_role"},
    "ops_manager": {"ops_manager", "commerce_operations", "multi_role"},
    "admin": {"support", "engineering_support", "commerce_operations", "ops_manager", "multi_role"},
}


def validate_retrieval_request(req: RetrievalQueryRequest) -> None:
    if not req.query or not req.query.strip():
        raise RetrievalValidationError("query is required")

    allowed_routes = {"policy_qa", "incident_summary", "escalation_guidance"}
    if req.route_type not in allowed_routes:
        raise RetrievalValidationError(f"unsupported route_type: {req.route_type}")

    allowed_roles = set(ROLE_TO_AUDIENCE.keys())
    if req.user_role not in allowed_roles:
        raise RetrievalValidationError(f"unsupported user_role: {req.user_role}")

    if req.top_k < 1 or req.top_k > 10:
        raise RetrievalValidationError("top_k must be between 1 and 10")


def build_retrieval_policy(req: RetrievalQueryRequest, config: RetrievalConfig) -> RetrievalPolicy:
    if req.route_type == "policy_qa":
        doc_types = ["policy", "sop"]
        top_k = config.policy_qa_top_k
        candidate_limit = config.policy_qa_candidate_limit
    elif req.route_type == "incident_summary":
        doc_types = ["runbook", "incident_playbook"]
        top_k = config.incident_summary_top_k
        candidate_limit = config.incident_summary_candidate_limit
    elif req.route_type == "escalation_guidance":
        doc_types = ["escalation_procedure", "matrix", "runbook"]
        top_k = config.escalation_guidance_top_k
        candidate_limit = config.escalation_guidance_candidate_limit
    else:
        raise RetrievalValidationError(f"unsupported route_type: {req.route_type}")

    if req.allowed_doc_types:
        doc_types = req.allowed_doc_types

    return RetrievalPolicy(
        allowed_doc_types=doc_types,
        allowed_audiences=ROLE_TO_AUDIENCE[req.user_role],
        top_k=req.top_k or top_k,
        candidate_limit=candidate_limit,
    )

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

# Ensure project root is on sys.path when running as a script
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.retrieval.audit import AuditSink
from app.retrieval.config import RetrievalConfig
from app.retrieval.embedder import DummyEmbedder
from app.retrieval.models import RetrievalQueryRequest, RetrievalRow
from app.retrieval.repository import FakeRetrievalRepository
from app.retrieval.service import RetrievalService


def build_fake_rows() -> list[RetrievalRow]:
    return [
        RetrievalRow(
            document_id="doc-1",
            doc_key="policy_returns_001",
            title="Returns Policy",
            doc_type="policy",
            audience="support",
            section_title="Damaged Product Exception",
            chunk_index=0,
            chunk_text="Title: Returns Policy\nSection: Damaged Product Exception\nContent: Products reported as damaged on arrival are handled under the damaged-product exception process.",
            similarity_score=0.88,
        ),
        RetrievalRow(
            document_id="doc-2",
            doc_key="sop_damaged_product_handling_001",
            title="Damaged Product Handling SOP",
            doc_type="sop",
            audience="support",
            section_title="Verification Steps",
            chunk_index=0,
            chunk_text="Title: Damaged Product Handling SOP\nSection: Verification Steps\nContent: Confirm the order exists, determine whether the report describes likely transit damage, and review photos when required.",
            similarity_score=0.84,
        ),
        RetrievalRow(
            document_id="doc-3",
            doc_key="runbook_checkout_incident_001",
            title="Checkout Incident Runbook",
            doc_type="runbook",
            audience="engineering_support",
            section_title="Customer Impact Assessment",
            chunk_index=1,
            chunk_text="Title: Checkout Incident Runbook\nSection: Customer Impact Assessment\nContent: The team should identify whether the issue is intermittent or persistent and whether safe workarounds exist.",
            similarity_score=0.79,
        ),
        RetrievalRow(
            document_id="doc-4",
            doc_key="matrix_priority_escalation_001",
            title="Priority Escalation Matrix",
            doc_type="matrix",
            audience="ops_manager",
            section_title="High Priority Criteria",
            chunk_index=0,
            chunk_text="Title: Priority Escalation Matrix\nSection: High Priority Criteria\nContent: Use high priority when the issue is actively customer-facing and affecting revenue-generating workflows.",
            similarity_score=0.76,
        ),
    ]


def main() -> None:
    service = RetrievalService(
        repository=FakeRetrievalRepository(rows=build_fake_rows()),
        config=RetrievalConfig(),
        embedder=DummyEmbedder(),
        audit_sink=AuditSink(),
    )

    req = RetrievalQueryRequest(
        query="What is the return process for damaged products?",
        route_type="policy_qa",
        user_role="support_analyst",
        top_k=5,
    )

    results = service.retrieve_context(req, request_id="req-smoke", user_id="user-smoke")
    print(json.dumps([asdict(r) for r in results], indent=2))


if __name__ == "__main__":
    main()

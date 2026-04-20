from dataclasses import dataclass
import os


@dataclass(slots=True)
class RetrievalConfig:
    default_top_k: int = 5
    policy_qa_top_k: int = 5
    incident_summary_top_k: int = 4
    escalation_guidance_top_k: int = 3
    policy_qa_candidate_limit: int = int(os.getenv("POLICY_QA_CANDIDATE_LIMIT", "25"))
    incident_summary_candidate_limit: int = int(os.getenv("INCIDENT_SUMMARY_CANDIDATE_LIMIT", "30"))
    escalation_guidance_candidate_limit: int = int(
        os.getenv("ESCALATION_GUIDANCE_CANDIDATE_LIMIT", "15")
    )
    max_chunks_per_doc: int = int(os.getenv("MAX_CHUNKS_PER_DOC", "2"))
    # Route caps stay independent so one aggressive global knob does not regress every route.
    policy_qa_max_chunks_per_doc: int = int(os.getenv("POLICY_QA_MAX_CHUNKS_PER_DOC", "2"))
    incident_summary_max_chunks_per_doc: int = int(
        os.getenv("INCIDENT_SUMMARY_MAX_CHUNKS_PER_DOC", "2")
    )
    escalation_guidance_max_chunks_per_doc: int = int(
        os.getenv("ESCALATION_GUIDANCE_MAX_CHUNKS_PER_DOC", "2")
    )

from __future__ import annotations

import re

from .models import SourceDocument


ALLOWED_DOC_TYPES = {
    "policy",
    "sop",
    "runbook",
    "incident_playbook",
    "escalation_procedure",
    "matrix",
}



def validate_source_document(doc: SourceDocument) -> None:
    required = {
        "title": doc.title,
        "doc_type": doc.doc_type,
        "doc_key": doc.doc_key,
        "status": doc.status,
        "source_name": doc.source_name,
    }
    for field_name, value in required.items():
        if not value:
            raise ValueError(f"Missing required metadata: {field_name}")

    if doc.doc_type not in ALLOWED_DOC_TYPES:
        raise ValueError(f"Unsupported doc_type: {doc.doc_type}")



def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")



def strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())



def collapse_excess_blank_lines(text: str, max_blank_lines: int = 1) -> str:
    pattern = r"\n{" + str(max_blank_lines + 2) + r",}"
    replacement = "\n" * (max_blank_lines + 1)
    return re.sub(pattern, replacement, text)



def normalize_inline_whitespace(text: str) -> str:
    normalized_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            normalized_lines.append("")
            continue
        if stripped.startswith("#") or stripped.startswith("-") or re.match(r"^\d+\.\s", stripped):
            normalized_lines.append(stripped)
            continue
        normalized_lines.append(re.sub(r"\s+", " ", stripped))
    return "\n".join(normalized_lines)



def normalize_document(doc: SourceDocument) -> SourceDocument:
    text = normalize_line_endings(doc.raw_text)
    text = strip_trailing_whitespace(text)
    text = collapse_excess_blank_lines(text, max_blank_lines=1)
    text = normalize_inline_whitespace(text)

    return SourceDocument(
        file_path=doc.file_path,
        title=doc.title.strip(),
        doc_type=doc.doc_type,
        doc_key=doc.doc_key,
        audience=doc.audience,
        status=doc.status,
        source_name=doc.source_name,
        source_path=doc.source_path,
        version=doc.version,
        raw_text=text.strip(),
    )

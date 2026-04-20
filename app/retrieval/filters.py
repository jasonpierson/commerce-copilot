from __future__ import annotations


def build_metadata_filters(
    *,
    allowed_doc_types: list[str],
    audience_filter: set[str],
    status: str = "published",
) -> dict:
    return {
        "doc_types": allowed_doc_types,
        "audiences": list(audience_filter),
        "status": status,
    }
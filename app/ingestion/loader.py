from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import SourceDocument


class FrontmatterError(ValueError):
    pass



def discover_corpus_files(root: Path, allowed_extensions: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Corpus root does not exist: {root}")
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in allowed_extensions
    )



def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        raise FrontmatterError("Missing YAML frontmatter opening delimiter")

    try:
        _, remainder = raw.split("---\n", 1)
        frontmatter_text, body = remainder.split("\n---\n", 1)
    except ValueError as exc:
        raise FrontmatterError("Invalid YAML frontmatter block") from exc

    metadata: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise FrontmatterError(f"Invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "version":
            metadata[key] = int(value)
        else:
            metadata[key] = value

    return metadata, body.lstrip("\n")



def load_source_document(file_path: Path) -> SourceDocument:
    raw = file_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw)

    return SourceDocument(
        file_path=str(file_path),
        title=metadata["title"],
        doc_type=metadata["doc_type"],
        doc_key=metadata["doc_key"],
        audience=metadata.get("audience"),
        status=metadata.get("status", "published"),
        source_name=metadata.get("source_name", "internal_wiki"),
        source_path=metadata.get("source_path"),
        version=int(metadata.get("version", 1)),
        raw_text=body,
    )

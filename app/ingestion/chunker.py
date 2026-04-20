from __future__ import annotations

import re
from typing import Iterable

from .models import Chunk, Section, SourceDocument



def count_tokens(text: str) -> int:
    """Approximate token count.

    Prefer determinism and zero external dependencies for v1.
    A rough heuristic is enough for the scaffold.
    """
    word_like = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return max(1, int(len(word_like) * 0.75))



def render_section_with_context(document_title: str, section_title: str | None, body_text: str) -> str:
    parts = [f"Title: {document_title}"]
    if section_title:
        parts.append(f"Section: {section_title}")
    parts.append(f"Content: {body_text.strip()}")
    return "\n".join(parts)



def split_into_paragraphs(body_text: str) -> list[str]:
    parts = [part.strip() for part in body_text.split("\n\n")]
    return [part for part in parts if part]



def _take_overlap_tail(text: str, overlap_tokens: int) -> str:
    words = text.split()
    if len(words) <= overlap_tokens:
        return text
    return " ".join(words[-overlap_tokens:])



def split_oversized_paragraph(
    paragraph: str,
    document_title: str,
    section_title: str | None,
    hard_max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    words = paragraph.split()
    chunks: list[str] = []
    start = 0

    while start < len(words):
        end = min(len(words), start + max(50, int(hard_max_tokens / 0.75)))
        piece = " ".join(words[start:end])
        rendered = render_section_with_context(document_title, section_title, piece)
        while count_tokens(rendered) > hard_max_tokens and end > start + 1:
            end -= 10
            piece = " ".join(words[start:end])
            rendered = render_section_with_context(document_title, section_title, piece)

        chunks.append(rendered)
        if end >= len(words):
            break
        overlap_tail = _take_overlap_tail(piece, overlap_tokens).split()
        start = max(start + 1, end - len(overlap_tail))

    return chunks



def split_long_section(
    document_title: str,
    section_title: str | None,
    body_text: str,
    target_tokens: int,
    soft_max_tokens: int,
    hard_max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    paragraphs = split_into_paragraphs(body_text)
    groups: list[str] = []
    current_group: list[str] = []

    for paragraph in paragraphs:
        candidate_group = current_group + [paragraph]
        candidate_text = render_section_with_context(
            document_title=document_title,
            section_title=section_title,
            body_text="\n\n".join(candidate_group),
        )

        if count_tokens(candidate_text) <= soft_max_tokens:
            current_group.append(paragraph)
            continue

        if current_group:
            groups.append(
                render_section_with_context(
                    document_title=document_title,
                    section_title=section_title,
                    body_text="\n\n".join(current_group),
                )
            )
            current_group = [paragraph]
            continue

        groups.extend(
            split_oversized_paragraph(
                paragraph=paragraph,
                document_title=document_title,
                section_title=section_title,
                hard_max_tokens=hard_max_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
        current_group = []

    if current_group:
        groups.append(
            render_section_with_context(
                document_title=document_title,
                section_title=section_title,
                body_text="\n\n".join(current_group),
            )
        )

    return groups



def build_chunks(
    document: SourceDocument,
    sections: list[Section],
    target_tokens: int,
    soft_max_tokens: int,
    hard_max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_index = 0

    for section in sections:
        rendered = render_section_with_context(
            document_title=document.title,
            section_title=section.title,
            body_text=section.body_text,
        )
        token_count = count_tokens(rendered)

        if token_count <= soft_max_tokens:
            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    document_title=document.title,
                    doc_key=document.doc_key,
                    doc_type=document.doc_type,
                    audience=document.audience,
                    section_title=section.title,
                    chunk_text=rendered,
                    token_count=token_count,
                )
            )
            chunk_index += 1
            continue

        for text in split_long_section(
            document_title=document.title,
            section_title=section.title,
            body_text=section.body_text,
            target_tokens=target_tokens,
            soft_max_tokens=soft_max_tokens,
            hard_max_tokens=hard_max_tokens,
            overlap_tokens=overlap_tokens,
        ):
            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    document_title=document.title,
                    doc_key=document.doc_key,
                    doc_type=document.doc_type,
                    audience=document.audience,
                    section_title=section.title,
                    chunk_text=text,
                    token_count=count_tokens(text),
                )
            )
            chunk_index += 1

    return chunks



def validate_chunks(chunks: list[Chunk], hard_max_tokens: int) -> None:
    if not chunks:
        raise ValueError("No chunks produced")

    expected_index = 0
    for chunk in chunks:
        if chunk.chunk_index != expected_index:
            raise ValueError("Non-contiguous chunk indexes")
        if chunk.token_count > hard_max_tokens:
            raise ValueError(
                f"Chunk {chunk.chunk_index} exceeds hard max token limit: {chunk.token_count}"
            )
        if not chunk.chunk_text.strip():
            raise ValueError(f"Chunk {chunk.chunk_index} is empty")
        expected_index += 1

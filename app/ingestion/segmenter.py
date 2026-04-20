from __future__ import annotations

from .models import Section, SourceDocument



def is_heading(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("## ") or stripped.startswith("### ") or stripped.startswith("# ")



def extract_heading_text(line: str) -> str:
    return line.lstrip("#").strip()



def segment_document(doc: SourceDocument) -> list[Section]:
    lines = doc.raw_text.splitlines()

    sections: list[Section] = []
    current_title: str | None = None
    current_body: list[str] = []
    section_index = 0

    for line in lines:
        if is_heading(line):
            heading = extract_heading_text(line)

            # Ignore the H1 if it matches the document title; use it as document title only.
            if heading == doc.title and line.strip().startswith("# "):
                continue

            if current_body:
                body_text = "\n".join(current_body).strip()
                if body_text:
                    sections.append(
                        Section(
                            section_index=section_index,
                            title=current_title,
                            body_text=body_text,
                        )
                    )
                    section_index += 1
                current_body = []

            current_title = heading
        else:
            current_body.append(line)

    if current_body:
        body_text = "\n".join(current_body).strip()
        if body_text:
            sections.append(
                Section(
                    section_index=section_index,
                    title=current_title,
                    body_text=body_text,
                )
            )

    if not sections and doc.raw_text.strip():
        sections.append(Section(section_index=0, title=None, body_text=doc.raw_text.strip()))

    return sections

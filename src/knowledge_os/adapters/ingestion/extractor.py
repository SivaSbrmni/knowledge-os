"""Text extraction from uploaded documents."""

from io import BytesIO
from pathlib import Path


def extract_text_from_bytes(content: bytes, mime_type: str, filename: str) -> tuple[str, int | None]:
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _extract_pdf(content)
    if mime_type.startswith("text/") or filename.lower().endswith((".txt", ".md")):
        text = content.decode("utf-8", errors="replace")
        return text, None
    raise ValueError(f"Unsupported file type: {mime_type}")


def _extract_pdf(content: bytes) -> tuple[str, int | None]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[Page {i + 1}]\n{page_text}")
    return "\n\n".join(pages), len(reader.pages)


def extract_text_from_file(path: Path, mime_type: str) -> tuple[str, int | None]:
    return extract_text_from_bytes(path.read_bytes(), mime_type, path.name)

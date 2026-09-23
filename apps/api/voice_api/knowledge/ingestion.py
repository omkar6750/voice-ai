"""In-memory extraction and Markdown section-aware overlapping chunks."""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Chunk:
    content: str
    metadata: dict


def extract_upload(filename: str, data: bytes) -> tuple[str, str, str]:
    name = PurePosixPath(filename.replace("\\", "/")).name
    kind = PurePosixPath(name).suffix.lower().lstrip(".")
    if kind not in {"pdf", "txt", "md"}:
        raise ValueError("Only PDF, TXT, and MD files are supported")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload exceeds 10 MiB")
    if kind == "pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(BytesIO(data))
            content = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("PDF could not be read (encrypted or invalid PDF)") from exc
    else:
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text uploads must use UTF-8") from exc
    content = clean_text(content)
    return name, kind, content


def clean_text(content: str) -> str:
    content = content.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    if not content:
        raise ValueError("Source contains no extractable text; scanned PDFs require OCR")
    return content


def chunk_markdown(content: str, size: int = 1600, overlap: int = 200) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Require size > overlap >= 0")
    content = clean_text(content)
    # Headings inside fenced code are ordinary content, not section boundaries.
    sections: list[tuple[int, str]] = [(0, "")]
    offset = 0
    fence = None
    headings: list[str] = []
    for line in content.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading and fence is None:
            level = len(heading[1])
            headings = [*headings[: level - 1], heading[2]]
            if offset == 0:
                sections[0] = (0, " / ".join(headings))
            else:
                sections.append((offset, " / ".join(headings)))
        offset += len(line)
    chunks = []
    for index, (start, heading) in enumerate(sections):
        stop = sections[index + 1][0] if index + 1 < len(sections) else len(content)
        pos = start
        while pos < stop:
            end = min(pos + size, stop)
            if end < stop:
                # Prefer paragraph/line boundaries, but never sacrifice forward progress.
                boundary = content.rfind("\n", pos + max(overlap + 1, size // 2), end)
                if boundary > pos:
                    end = boundary + 1
            value = content[pos:end]
            if value.strip():
                chunks.append(Chunk(value, {"heading": heading, "start": pos, "end": end}))
            if end == stop:
                break
            pos = end - overlap
    return chunks

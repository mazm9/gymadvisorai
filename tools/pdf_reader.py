from __future__ import annotations
from typing import List

def read_pdf_text(path: str, max_chars: int = 200_000) -> str:
    """Extract text from a PDF (no OCR). If the PDF has no text layer, returns an empty string."""
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise RuntimeError("pypdf is required to read PDFs. Install: pip install pypdf") from e

    reader = PdfReader(path)
    parts: List[str] = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        if txt.strip():
            parts.append(txt)
        if sum(len(p) for p in parts) >= max_chars:
            break
    out = "\n\n".join(parts).strip()
    return out[:max_chars]

from __future__ import annotations
from pathlib import Path

def load_pdf_text(path: str | Path) -> str:
    """
    Extract text from a PDF without OCR.
    Works for text-based PDFs (your generated ones are text-based).
    """
    from pypdf import PdfReader

    p = Path(path)
    reader = PdfReader(str(p))
    pages = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        pages.append(txt)
    return "\n\n".join(pages)

def load_pdfs_from_dir(pdf_dir: str | Path) -> list[dict]:
    """
    Returns a list of documents: [{"doc_id":..., "source":..., "text":...}, ...]
    """
    pdf_dir = Path(pdf_dir)
    docs = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        docs.append({
            "doc_id": pdf.stem,
            "source": str(pdf),
            "text": load_pdf_text(pdf),
        })
    return docs

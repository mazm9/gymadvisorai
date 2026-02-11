from __future__ import annotations

import os
from typing import List

def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        return ""

def load_texts_from_docs_dir(docs_dir: str = "data/docs") -> List[str]:
    if not os.path.exists(docs_dir):
        return []
    out: List[str] = []
    for root, _, files in os.walk(docs_dir):
        for fn in files:
            p = os.path.join(root, fn)
            ext = os.path.splitext(fn.lower())[1]
            if ext in [".md", ".txt"]:
                txt = _read_text_file(p).strip()
                if txt:
                    out.append(txt)
            elif ext == ".pdf":
                txt = _read_pdf(p).strip()
                if txt:
                    out.append(txt)
    return out

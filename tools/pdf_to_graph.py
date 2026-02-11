from __future__ import annotations
import os, csv, re
from typing import Any, Dict, List, Tuple

from core.llm import get_llm
from .pdf_reader import read_pdf_text

EDGE_FIELDS = ["source","relation","target"]

_PROMPT = """Extract a small knowledge graph from the text.
Return STRICT JSON: {{ "edges": [{{"source": "...", "relation": "...", "target": "..."}}] }}
Rules:
- Use concise entity names.
- Prefer domain entities: exercises, muscles, goals, injuries/limitations, equipment, training principles.
- Relations examples: targets, alternative, contraindicated_for, supports_goal, requires_equipment, improves, avoid_pattern.
- Do NOT include explanations, only JSON.
"""

def _chunk(text: str, max_chars: int = 3500) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+max_chars])
        i += max_chars
    return chunks

def extract_graph_from_docs(docs_dir: str = "data/docs", out_csv: str = "data/graph/edges_llm.csv", *, max_chunks: int = 12) -> Dict[str, Any]:
    llm = get_llm()
    texts: List[Tuple[str,str]] = []

    for fn in os.listdir(docs_dir):
        path = os.path.join(docs_dir, fn)
        if os.path.isdir(path):
            continue
        low = fn.lower()
        try:
            if low.endswith(".pdf"):
                texts.append((fn, read_pdf_text(path)))
            elif low.endswith(".md") or low.endswith(".txt"):
                with open(path, "r", encoding="utf-8") as f:
                    texts.append((fn, f.read()))
        except Exception:
            continue

    edges: List[Dict[str,str]] = []
    seen = set()

    for name, txt in texts:
        for ch in _chunk(txt)[:max_chunks]:
            user = _PROMPT + "\n\nTEXT:\n" + ch
            raw = llm.generate("You output JSON only.", user).text
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                continue
            import json
            try:
                obj = json.loads(raw[start:end+1])
            except Exception:
                continue
            for e in obj.get("edges", []) or []:
                s = str(e.get("source","")).strip()
                r = str(e.get("relation","")).strip()
                t = str(e.get("target","")).strip()
                if not (s and r and t):
                    continue
                key = (s.lower(), r.lower(), t.lower())
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"source": s, "relation": r, "target": t})

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EDGE_FIELDS)
        w.writeheader()
        w.writerows(edges)

    return {"out_csv": out_csv, "edges": len(edges), "docs": [n for n,_ in texts]}

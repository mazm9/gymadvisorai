from __future__ import annotations
import os, csv
from typing import Any, Dict, List

from .pdf_to_graph import extract_graph_from_docs
from .graph_rag import ingest_edges_to_json

EDGE_FIELDS = ["source","relation","target"]

def _read_edges(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out=[]
    with open(path,"r",encoding="utf-8") as f:
        r=csv.DictReader(f)
        for row in r:
            s=(row.get("source") or "").strip()
            t=(row.get("target") or "").strip()
            rel=(row.get("relation") or "related_to").strip()
            if s and t:
                out.append({"source": s, "relation": rel, "target": t})
    return out

def _write_edges(path: str, edges: List[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f, fieldnames=EDGE_FIELDS)
        w.writeheader()
        for e in edges:
            w.writerow({"source": e["source"], "relation": e["relation"], "target": e["target"]})

def build_from_docs(*, docs_dir: str = "data/docs", edges_csv: str = "data/graph/edges.csv") -> Dict[str, Any]:
    """Extract edges from docs (PDF/MD/TXT) using LLM and merge into local graph."""
    llm_out = extract_graph_from_docs(docs_dir=docs_dir, out_csv="data/graph/edges_llm.csv")
    base = _read_edges(edges_csv)
    new = _read_edges(llm_out["out_csv"])
    seen=set((e["source"].lower(), e["relation"].lower(), e["target"].lower()) for e in base)
    merged=list(base)
    added=0
    for e in new:
        key=(e["source"].lower(), e["relation"].lower(), e["target"].lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
        added += 1
    _write_edges(edges_csv, merged)
    ing = ingest_edges_to_json(edges_csv=edges_csv, out_json="data/graph/graph.json")
    return {"llm_edges": llm_out["edges"], "added": added, "total_edges": len(merged), "graph_json": ing.get("out")}

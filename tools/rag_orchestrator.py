from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple


def query(query_text: str, run_vector: bool = True, run_graph: bool = True) -> Dict[str, Any]:
    """Call both Vector RAG and Graph RAG and return a merged view.

    The function is intentionally conservative: it doesn't modify the
    source results, only annotates items with their origin and produces
    a merged summary useful for UI comparison.
    """
    out: Dict[str, Any] = {"type": "rag_orchestrator", "query": query_text}

    vector_obs = None
    graph_obs = None

    if run_vector:
        try:
            from .vector_rag import query as _vquery

            vector_obs = _vquery(query_text)
        except Exception as e:  # pragma: no cover - defensive
            vector_obs = {"error": str(e)}

    if run_graph:
        try:
            from .graph_rag import query as _gquery

            graph_obs = _gquery(query_text)
        except Exception as e:  # pragma: no cover - defensive
            graph_obs = {"error": str(e)}

    # Build a merged summary: matched nodes, edges, and simple stats.
    matched_nodes: Set[Tuple[str, str]] = set()
    edges_set: Set[Tuple[str, str, str, str]] = set()

    if isinstance(vector_obs, dict):
        for n in vector_obs.get("matched_nodes", []) or []:
            matched_nodes.add(("vector", str(n)))
        for e in vector_obs.get("edges", []) or []:
            edges_set.add(("vector", str(e.get("source")), str(e.get("relation")), str(e.get("target"))))

    if isinstance(graph_obs, dict):
        for n in graph_obs.get("matched_nodes", []) or []:
            matched_nodes.add(("graph", str(n)))
        for e in graph_obs.get("edges", []) or []:
            edges_set.add(("graph", str(e.get("source")), str(e.get("relation")), str(e.get("target"))))

    merged = {
        "matched_nodes": [{"origin": o, "node": n} for (o, n) in sorted(matched_nodes)],
        "edges": [
            {"origin": o, "source": s, "relation": r, "target": t}
            for (o, s, r, t) in sorted(edges_set)
        ],
        "vector": vector_obs,
        "graph": graph_obs,
    }

    out["merged"] = merged
    return out

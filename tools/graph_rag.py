from __future__ import annotations

import os
import csv
import json
import re
from typing import Any, Dict, List, Tuple
import networkx as nx


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _dedup_edges(edges: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for e in edges:
        key = (_norm(e.get("source", "")), _norm(e.get("relation", "related_to")), _norm(e.get("target", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source": e.get("source", ""),
            "relation": e.get("relation", "related_to"),
            "target": e.get("target", ""),
        })
    return out


def generate_edges_from_catalog(catalog_json: str = "data/catalog/exercises.json") -> List[Dict[str, str]]:
    """Build graph edges from the structured exercise catalog.

    This makes the local GraphRAG useful out-of-the-box (even without Neo4j)
    for tasks like filtering/counting by equipment, muscles or tags.
    """
    if not os.path.exists(catalog_json):
        return []
    with open(catalog_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    exercises = data.get("exercises") if isinstance(data, dict) else data
    if not isinstance(exercises, list):
        return []

    edges: List[Dict[str, str]] = []
    for ex in exercises:
        if not isinstance(ex, dict):
            continue
        name = ex.get("name") or ex.get("id")
        if not name:
            continue

        # Equipment requirements
        for eq in ex.get("equipment", []) or []:
            if not eq:
                continue
            edges.append({"source": name, "relation": "requires", "target": str(eq)})

        # Primary muscles
        for m in ex.get("muscles_primary", []) or []:
            if not m:
                continue
            edges.append({"source": name, "relation": "targets", "target": str(m)})

        # Tags
        for t in ex.get("tags", []) or []:
            if not t:
                continue
            edges.append({"source": name, "relation": "tagged_as", "target": str(t)})

    return _dedup_edges(edges)


def count_exercises_with_equipment(
    allowed_equipment: List[str],
    exact: bool = False,
    graph_json: str = "data/graph/graph.json",
) -> Dict[str, Any]:
    """Count exercises that can be performed with a given equipment set.

    - exact=False (default): exercise equipment set must be a subset of allowed.
    - exact=True: exercise equipment set must equal allowed.
    """
    allowed = {_norm(x) for x in (allowed_equipment or []) if _norm(x)}
    if not allowed:
        return {"type": "graph_count", "allowed": [], "exact": exact, "count": 0, "exercise_names": []}

    if not os.path.exists(graph_json):
        ingest_edges_to_json()

    with open(graph_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    req_map: Dict[str, set] = {}
    for e in data.get("edges", []) or []:
        if _norm(e.get("relation")) != "requires":
            continue
        src = e.get("source")
        tgt = e.get("target")
        if not src or not tgt:
            continue
        req_map.setdefault(src, set()).add(_norm(str(tgt)))

    hits = []
    for ex_name, reqs in req_map.items():
        if exact:
            ok = reqs == allowed
        else:
            ok = reqs.issubset(allowed)
        if ok:
            hits.append(ex_name)

    hits_sorted = sorted(hits, key=lambda x: x.lower())
    return {
        "type": "graph_count",
        "allowed": sorted(list(allowed)),
        "exact": exact,
        "count": len(hits_sorted),
        "exercise_names": hits_sorted,
    }

def _normalize_neo4j_uri(uri: str) -> str:
    """Return a driver URI that avoids routing issues when possible.

    - neo4j:// and neo4j+s:// are routing schemes.
    - bolt:// and bolt+s:// are direct schemes.

    Some networks fail to fetch routing info; direct bolt usually works.
    """
    u = (uri or "").strip()
    if u.startswith("neo4j+s://"):
        return "bolt+s://" + u[len("neo4j+s://"):]
    if u.startswith("neo4j://"):
        return "bolt://" + u[len("neo4j://"):]
    return u


def _open_driver_with_fallback(uri: str, auth: tuple[str, str]):
    """Try routing URI; if it fails, retry with direct bolt scheme."""
    from neo4j import GraphDatabase
    try:
        return GraphDatabase.driver(uri, auth=auth)
    except Exception:
        u2 = _normalize_neo4j_uri(uri)
        if u2 != uri:
            return GraphDatabase.driver(u2, auth=auth)
        raise


def _neo4j_configured() -> bool:
    return bool(os.getenv("NEO4J_URI","").strip() and os.getenv("NEO4J_USER","").strip() and os.getenv("NEO4J_PASSWORD","").strip())

def _load_local_graph(path_json: str = "data/graph/graph.json") -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    if os.path.exists(path_json):
        with open(path_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        for e in data.get("edges", []):
            g.add_edge(e["source"], e["target"], relation=e.get("relation","related_to"))
        return g
    csv_path = "data/graph/edges.csv"
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                g.add_edge(row["source"], row["target"], relation=row.get("relation","related_to"))
    return g

def _query_local(g: nx.MultiDiGraph, query_text: str, max_hops: int = 2) -> Dict[str, Any]:
    q = query_text.lower()
    tokens = [t for t in [w.strip(".,!?;:()[]{}").lower() for w in q.split()] if len(t) > 2]
    matched = [n for n in g.nodes() if any(t in str(n).lower() for t in tokens)][:5]

    edges_out = []
    for n in matched:
        for nbr in list(g.successors(n))[:10]:
            for _, attrs in (g.get_edge_data(n, nbr) or {}).items():
                edges_out.append({"source": n, "target": nbr, "relation": attrs.get("relation","related_to")})

    paths = []
    ug = g.to_undirected()
    for s in matched:
        for t in list(ug.nodes())[:50]:
            if s == t:
                continue
            try:
                p = nx.shortest_path(ug, s, t)
                if 2 <= len(p) <= max_hops + 1:
                    paths.append(p)
            except Exception:
                continue
        if len(paths) >= 5:
            break

    return {"type":"graph_rag","mode":"local","matched_nodes": matched, "edges": edges_out[:20], "paths": paths[:5]}

def _query_neo4j(query_text: str, limit: int = 25) -> Dict[str, Any]:
    from neo4j import GraphDatabase
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    pwd = os.getenv("NEO4J_PASSWORD")

    tokens = [t for t in query_text.split() if len(t) > 2][:6]
    cypher = """
    UNWIND $tokens AS tok
    MATCH (a)-[r]->(b)
    WHERE toLower(a.name) CONTAINS toLower(tok) OR toLower(b.name) CONTAINS toLower(tok)
    RETURN a.name AS source, type(r) AS relation, b.name AS target
    LIMIT $limit
    """

    edges = []
    with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
        with driver.session() as session:
            for rec in session.run(cypher, tokens=tokens, limit=limit):
                edges.append({"source": rec["source"], "relation": rec["relation"], "target": rec["target"]})
    nodes = list({e["source"] for e in edges} | {e["target"] for e in edges})
    return {"type":"graph_rag","mode":"neo4j","matched_nodes": nodes[:20], "edges": edges[:limit], "paths": []}

def query(query_text: str) -> Dict[str, Any]:
    """Query graph relations.

    Mode selection:
      - GRAPH_RAG_MODE=neo4j will *try* Neo4j if env vars are present.
      - otherwise it uses the local graph built from data/graph (CSV/JSON).
    """

    mode = (os.getenv("GRAPH_RAG_MODE") or "local").strip().lower()

    if mode == "neo4j" and _neo4j_configured():
        try:
            return _query_neo4j(query_text)
        except Exception as e:
            g = _load_local_graph()
            out = _query_local(g, query_text)
            out["warning"] = f"Neo4j failed; using local graph. Error: {e}"
            return out

    g = _load_local_graph()
    return _query_local(g, query_text)


def query_graph_local(query_text: str, top_k: int = 25) -> Dict[str, Any]:
    """Public helper for querying the local graph.

    Useful for quick CLI checks:
    `py -c "from tools.graph_rag import query_graph_local; print(query_graph_local('bench chest'))"`
    """
    g = _load_local_graph()
    out = _query_local(g, query_text)
    if isinstance(out.get("edges"), list):
        out["edges"] = out["edges"][:top_k]
    if isinstance(out.get("matched_nodes"), list):
        out["matched_nodes"] = out["matched_nodes"][:top_k]
    return out

def ingest_edges_to_json(edges_csv: str = "data/graph/edges.csv", out_json: str = "data/graph/graph.json") -> Dict[str, Any]:
    edges: List[Dict[str, str]] = []

    if os.path.exists(edges_csv):
        with open(edges_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("source") and row.get("target"):
                    edges.append({
                        "source": row["source"],
                        "target": row["target"],
                        "relation": row.get("relation", "related_to"),
                    })

    edges.extend(generate_edges_from_catalog("data/catalog/exercises.json"))
    edges = _dedup_edges(edges)

    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"edges": edges}, f, ensure_ascii=False, indent=2)
    return {"edges": len(edges), "out": out_json, "note": "Merged edges.csv + catalog-derived edges."}


def ingest_edges_to_neo4j(edges_csv: str = "data/graph/edges.csv") -> str:
    import csv

    uri = os.getenv("NEO4J_URI","").strip()
    user = os.getenv("NEO4J_USER","").strip()
    pwd = os.getenv("NEO4J_PASSWORD","").strip()
    if not (uri and user and pwd):
        return "Missing Neo4j env vars (NEO4J_URI/USER/PASSWORD)."

    from neo4j import GraphDatabase
    driver = _open_driver_with_fallback(uri, auth=(user, pwd))

    rows = []
    with open(edges_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    q = """UNWIND $rows AS row
    MERGE (a:Entity {name: row.source})
    MERGE (b:Entity {name: row.target})
    MERGE (a)-[r:REL {type: row.relation}]->(b)
    SET r.source_file = coalesce(row.source_file, row.source_file)
    """

    with driver.session() as session:
        session.run(q, rows=rows)

    driver.close()
    return f"Ingested {len(rows)} edges into Neo4j."

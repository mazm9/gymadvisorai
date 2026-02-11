from __future__ import annotations
import os, csv, json
from typing import Any, Dict
import networkx as nx

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
    if _neo4j_configured():
        try:
            return _query_neo4j(query_text)
        except Exception as e:
            g = _load_local_graph()
            out = _query_local(g, query_text)
            out["warning"] = f"Neo4j failed; using local graph. Error: {e}"
            return out
    g = _load_local_graph()
    return _query_local(g, query_text)

def ingest_edges_to_json(edges_csv: str = "data/graph/edges.csv", out_json: str = "data/graph/graph.json") -> Dict[str, Any]:
    edges = []
    if os.path.exists(edges_csv):
        with open(edges_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("source") and row.get("target"):
                    edges.append({"source": row["source"], "target": row["target"], "relation": row.get("relation","related_to")})
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"edges": edges}, f, ensure_ascii=False, indent=2)
    return {"edges": len(edges), "out": out_json}

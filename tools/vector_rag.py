from __future__ import annotations
import os, glob
from typing import Any, Dict
import chromadb
from chromadb.utils import embedding_functions

def _client() -> chromadb.PersistentClient:
    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "data/indexes/chroma")
    return chromadb.PersistentClient(path=persist_dir)

def _collection(client: chromadb.PersistentClient):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-small",
        )
    else:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return client.get_or_create_collection("docs", embedding_function=ef)

def ingest_docs(docs_dir: str = "data/docs") -> Dict[str, Any]:
    client = _client()
    col = _collection(client)

    paths = []
    for ext in ("*.txt", "*.md"):
        paths.extend(glob.glob(os.path.join(docs_dir, ext)))

    ids, docs, metas = [], [], []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        if not txt:
            continue
        doc_id = os.path.basename(p)
        ids.append(doc_id)
        docs.append(txt[:8000])
        metas.append({"source": doc_id})

    if ids:
        try:
            col.delete(ids=ids)
        except Exception:
            pass
        col.add(ids=ids, documents=docs, metadatas=metas)

    return {"ingested": len(ids), "files": [os.path.basename(p) for p in paths]}

def query(query_text: str, top_k: int = 5) -> Dict[str, Any]:
    client = _client()
    col = _collection(client)
    top_k = int(os.getenv("RAG_TOP_K", str(top_k)))
    res = col.query(query_texts=[query_text], n_results=top_k, include=["documents","metadatas","distances"])
    items = []
    for i in range(len(res["ids"][0])):
        items.append({
            "id": res["ids"][0][i],
            "text": res["documents"][0][i],
            "meta": res["metadatas"][0][i],
            "distance": res["distances"][0][i],
        })
    return {"type": "vector_rag", "items": items}

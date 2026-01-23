from __future__ import annotations
from dataclasses import dataclass
from chromadb import PersistentClient
from gymadvisorai.config import settings
from gymadvisorai.rag.azure_embeddings import embed

COLLECTION = "gymadvisorai_rag"

@dataclass(frozen=True)
class Retrieved:
    docs: list[str]

def _client():
    return PersistentClient(path=settings.chroma_dir)

def build(docs: list[str]) -> None:
    c = _client()
    col = c.get_or_create_collection(name=COLLECTION)

    # reset collection (simple/dev)
    try:
        c.delete_collection(COLLECTION)
    except Exception:
        pass
    col = c.get_or_create_collection(name=COLLECTION)

    ids = [f"d{i}" for i in range(len(docs))]
    vecs = embed(docs)
    col.add(ids=ids, documents=docs, embeddings=vecs)

def retrieve(query: str, k: int = 5) -> Retrieved:
    c = _client()
    col = c.get_or_create_collection(name=COLLECTION)
    qv = embed([query])[0]
    res = col.query(query_embeddings=[qv], n_results=k)
    docs = res["documents"][0] if res and res.get("documents") else []
    return Retrieved(docs=docs)

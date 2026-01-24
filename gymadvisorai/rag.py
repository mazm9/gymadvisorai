from __future__ import annotations

import math
import pickle
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from gymadvisorai.config import settings
from gymadvisorai.data_loader import load_json
from gymadvisorai.llm import llm_chat, llm_embed
from gymadvisorai.pdf_ingest import extract_text_from_pdf


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


@dataclass(frozen=True)
class Retrieved:
    docs: list[str]


class TfidfStore:
    """Very small TF-IDF store.

    This is a fallback baseline that works offline (no embeddings required).
    """

    def __init__(self, path: str | None = None):
        self.path = Path(path or settings.rag_store_path)
        self.docs: list[str] = []
        self.df: dict[str, int] = {}
        self.doc_vecs: list[dict[str, float]] = []
        self.norms: list[float] = []

    def build(self, docs: Iterable[str]) -> None:
        self.docs = [d.strip() for d in docs if d and d.strip()]
        N = len(self.docs)
        tf_list: list[Counter[str]] = []
        df: dict[str, int] = {}

        for d in self.docs:
            tf = Counter(_tokenize(d))
            tf_list.append(tf)
            for t in tf.keys():
                df[t] = df.get(t, 0) + 1

        self.df = df
        self.doc_vecs = []
        self.norms = []

        for tf in tf_list:
            vec: dict[str, float] = {}
            for t, c in tf.items():
                idf = math.log((N + 1) / (df[t] + 1)) + 1.0
                vec[t] = c * idf
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.doc_vecs.append(vec)
            self.norms.append(norm)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as f:
            pickle.dump(
                {"docs": self.docs, "df": self.df, "doc_vecs": self.doc_vecs, "norms": self.norms},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    def load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"TF-IDF store not found: {self.path}. Build it first (--build-rag).")
        with self.path.open("rb") as f:
            obj = pickle.load(f)
        self.docs = obj["docs"]
        self.df = obj["df"]
        self.doc_vecs = obj["doc_vecs"]
        self.norms = obj["norms"]

    def retrieve(self, query: str, k: int = 5) -> Retrieved:
        if not self.docs:
            self.load()

        q_tf = Counter(_tokenize(query))
        N = len(self.docs)
        q_vec: dict[str, float] = {}
        for t, c in q_tf.items():
            df = self.df.get(t, 0)
            idf = math.log((N + 1) / (df + 1)) + 1.0
            q_vec[t] = c * idf
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        q_keys = set(q_vec.keys())
        scored: list[tuple[float, int]] = []
        for i, dvec in enumerate(self.doc_vecs):
            dot = 0.0
            for t in q_keys:
                if t in dvec:
                    dot += q_vec[t] * dvec[t]
            score = dot / (q_norm * (self.norms[i] or 1.0))
            scored.append((score, i))

        scored.sort(reverse=True)
        docs = [self.docs[i] for s, i in scored[:k] if s > 0]
        return Retrieved(docs=docs)


class EmbeddingStore:
    """Embedding-based baseline RAG index.

    Uses Azure OpenAI embeddings when configured.
    """

    def __init__(self, path: str | None = None):
        base = Path(path or settings.rag_store_path)
        # Keep separate from TF-IDF pickle.
        self.path = base.with_suffix(base.suffix + ".emb") if base.suffix else Path(str(base) + ".emb")
        self.docs: list[str] = []
        self.vecs: list[list[float]] = []
        self.norms: list[float] = []

    def build(self, docs: Iterable[str], batch_size: int = 32) -> None:
        self.docs = [d.strip() for d in docs if d and d.strip()]
        self.vecs = []
        self.norms = []

        for i in range(0, len(self.docs), batch_size):
            chunk = self.docs[i : i + batch_size]
            self.vecs.extend(llm_embed(chunk))

        for v in self.vecs:
            n = math.sqrt(sum(float(x) * float(x) for x in v)) or 1.0
            self.norms.append(n)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as f:
            pickle.dump(
                {"docs": self.docs, "vecs": self.vecs, "norms": self.norms},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    def load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(
                f"Embedding store not found: {self.path}. Build it first (--build-rag) with embeddings enabled."
            )
        with self.path.open("rb") as f:
            obj = pickle.load(f)
        self.docs = obj["docs"]
        self.vecs = obj["vecs"]
        self.norms = obj["norms"]

    def retrieve(self, query: str, k: int = 5) -> Retrieved:
        if not self.docs:
            self.load()

        q_vec = llm_embed([query])[0]
        q_norm = math.sqrt(sum(float(x) * float(x) for x in q_vec)) or 1.0

        scored: list[tuple[float, int]] = []
        for i, dvec in enumerate(self.vecs):
            dot = 0.0
            for a, b in zip(q_vec, dvec):
                dot += float(a) * float(b)
            score = dot / (q_norm * (self.norms[i] or 1.0))
            scored.append((score, i))

        scored.sort(reverse=True)
        docs = [self.docs[i] for s, i in scored[:k] if s > 0]
        return Retrieved(docs=docs)


def _collect_demo_docs() -> list[str]:
    knowledge = load_json("exercise_knowledge.json")
    workouts = load_json("workouts.json")
    users = load_json("users.json")
    plans = load_json("training_plans.json")

    docs: list[str] = []
    for ex in knowledge.get("exercises", []):
        docs.append(
            f"Exercise: {ex.get('name')}\n"
            f"Targets: {', '.join(ex.get('targets', []))}\n"
            f"Equipment: {', '.join(ex.get('equipment', []))}\n"
            f"Risk: {', '.join(ex.get('risk', []))}\n"
        )
    for s in workouts.get("sessions", []):
        parts = [f"Date: {s.get('date')}"] + [
            f"{it.get('exercise')} {it.get('sets')}x{it.get('reps')} {it.get('weight')}"
            for it in s.get("items", [])
        ]
        docs.append("\n".join(parts))

    # Add user profiles and plan specs so baseline RAG can attempt matching
    for u in users.get("users", []) or []:
        docs.append(
            "UserProfile: {uid}\nGoal: {goal}\nDaysPerWeek: {d}\nMinutes: {m}\n"
            "Focus: {focus}\nConstraints: {cons}\nEquipment: {eq}\nLevel: {lvl}\n".format(
                uid=u.get("user_id"),
                goal=u.get("goal"),
                d=u.get("days_per_week"),
                m=u.get("minutes_per_session"),
                focus=", ".join(u.get("focus", []) or []),
                cons=", ".join(u.get("constraints", []) or []),
                eq=", ".join(u.get("equipment", []) or []),
                lvl=u.get("experience_level"),
            )
        )

    for p in plans.get("plans", []) or []:
        docs.append(
            "TrainingPlan: {name}\nDaysPerWeek: {d}\nMinutes: {m}\nFocus: {focus}\n"
            "RequiredEquipment: {eq}\nExercises: {ex}\n".format(
                name=p.get("name"),
                d=p.get("days_per_week"),
                m=p.get("minutes_per_session"),
                focus=", ".join(p.get("focus", []) or []),
                eq=", ".join(p.get("equipment", []) or []),
                ex=", ".join(p.get("exercises", []) or []),
            )
        )

    # Index any PDFs placed under gymadvisorai/data (including raw_pdfs/).
    # This lets baseline RAG "read" unstructured sources (CV-like profiles, RFP-like plans, logs).
    data_dir = Path(__file__).resolve().parent / "data"
    pdf_dirs = [data_dir, data_dir / "raw_pdfs"]

    seen: set[Path] = set()
    for d in pdf_dirs:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.pdf")):
            if p in seen:
                continue
            seen.add(p)
            try:
                rel = p.relative_to(data_dir) if data_dir in p.parents else p.name
                docs.append(f"PDF:{rel}\n" + extract_text_from_pdf(str(p)))
            except Exception:
                # PDFs are optional; ignore failures so offline baseline still builds
                pass

    return docs




def build_rag_from_local_json() -> int:
    """Build baseline RAG indexes from local demo data.

    - Always builds TF-IDF store (offline).
    - If OPENAI_EMBEDDING_MODEL is set and LLM_ENABLED=true, also builds embedding store.
    """

    docs = _collect_demo_docs()

    # Fallback
    TfidfStore().build(docs)

    # Optional embedding index
    if settings.llm_enabled and settings.openai_embedding_model:
        EmbeddingStore().build(docs)

    return len(docs)


def answer_with_rag(question: str, k: int = 5) -> str:
    """Baseline RAG.

    Retrieval:
      - Embeddings if configured + built
      - else TF-IDF fallback
    Generation:
      - LLM if enabled
      - else returns retrieved snippets (still useful for demo)
    """

    retrieved: list[str] = []
    used = "tfidf"

    if settings.llm_enabled and settings.openai_embedding_model:
        try:
            retrieved = EmbeddingStore().retrieve(question, k=k).docs
            used = "embeddings"
        except Exception:
            # fall back
            retrieved = []

    if not retrieved:
        retrieved = TfidfStore().retrieve(question, k=k).docs
        used = used if retrieved else "tfidf"

    if not retrieved:
        return "RAG baseline: no relevant context found in indexed documents."

    context = "\n\n---\n\n".join(retrieved[:k])

    if not settings.llm_enabled:
        return f"RAG baseline (retrieval={used}, LLM=off). Top snippets:\n" + context

    prompt = (
        "You answer gym-related questions using only the provided context. "
        "If the context does not contain the answer, say you don't know.\n\n"
        f"Question: {question}\n\nContext:\n{context}\n"
    )

    out = llm_chat(prompt, max_tokens=350)
    return out.strip() if out and out.strip() else f"RAG baseline (retrieval={used}). Top snippets:\n" + context

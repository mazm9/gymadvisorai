from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .pdf_utils import load_texts_from_docs_dir

@dataclass
class BuildResult:
    ok: bool
    mode: str
    nodes: int
    relationships: int
    detail: str

def build_graph_with_langchain(
    docs_dir: str = "data/docs",
    neo4j_url: Optional[str] = None,
    neo4j_username: Optional[str] = None,
    neo4j_password: Optional[str] = None,
    openai_provider: str = "azure",
    max_docs: int = 20,
) -> BuildResult:
    """Maximal pipeline: docs -> LangChain LLMGraphTransformer -> Neo4j.

    This function is **optional**: if LangChain packages are missing it returns a helpful message.
    It tries to be robust on different Python versions by importing lazily.

    Required env (Azure):
      - AZURE_OPENAI_API_KEY
      - AZURE_OPENAI_ENDPOINT
      - AZURE_OPENAI_API_VERSION
      - AZURE_OPENAI_DEPLOYMENT (chat model deployment name)

    Required env (Neo4j):
      - NEO4J_URI (bolt/neo4j+s)
      - NEO4J_USER
      - NEO4J_PASSWORD
    """
    try:
        from langchain_core.documents import Document
        from langchain_experimental.graph_transformers import LLMGraphTransformer
        from langchain_community.graphs import Neo4jGraph
    except Exception as e:
        return BuildResult(
            ok=False,
            mode="langchain_missing",
            nodes=0,
            relationships=0,
            detail=f"LangChain Graph stack not installed. Install optional requirements: pip install -r requirements_langchain.txt. Error: {e}",
        )

    # LLM
    llm = None
    if openai_provider == "azure":
        try:
            from langchain_openai import AzureChatOpenAI
        except Exception as e:
            return BuildResult(False, "langchain_missing", 0, 0, f"Missing langchain_openai. Install requirements_langchain.txt. Error: {e}")
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01-preview").strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
        if not (api_key and endpoint and deployment):
            return BuildResult(False, "bad_env", 0, 0, "Missing Azure OpenAI env vars (AZURE_OPENAI_API_KEY/ENDPOINT/DEPLOYMENT).")
        llm = AzureChatOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_deployment=deployment,
            temperature=1.0,
        )
    else:
        try:
            from langchain_openai import ChatOpenAI
        except Exception as e:
            return BuildResult(False, "langchain_missing", 0, 0, f"Missing langchain_openai. Install requirements_langchain.txt. Error: {e}")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        if not api_key:
            return BuildResult(False, "bad_env", 0, 0, "Missing OPENAI_API_KEY for openai provider.")
        llm = ChatOpenAI(api_key=api_key, model=model, temperature=1.0)

    # Neo4j
    neo4j_url = neo4j_url or os.getenv("NEO4J_URI", "").strip()
    neo4j_username = neo4j_username or os.getenv("NEO4J_USER", "").strip()
    neo4j_password = neo4j_password or os.getenv("NEO4J_PASSWORD", "").strip()
    if not (neo4j_url and neo4j_username and neo4j_password):
        return BuildResult(False, "bad_env", 0, 0, "Missing Neo4j env vars (NEO4J_URI/USER/PASSWORD).")

    graph = Neo4jGraph(url=neo4j_url, username=neo4j_username, password=neo4j_password)

    # docs
    texts = load_texts_from_docs_dir(docs_dir)
    if not texts:
        return BuildResult(False, "no_docs", 0, 0, f"No docs found in {docs_dir}.")
    texts = texts[:max_docs]
    docs = [Document(page_content=t, metadata={"source": f"doc_{i}"}) for i, t in enumerate(texts)]

    transformer = LLMGraphTransformer(llm=llm)
    graph_docs = transformer.convert_to_graph_documents(docs)

    # Add to Neo4j via langchain graph helper
    graph.add_graph_documents(graph_docs, include_source=True)

    # Quick stats (best-effort)
    nodes = 0
    rels = 0
    try:
        result = graph.query("MATCH (n) RETURN count(n) as c")
        nodes = int(result[0]["c"])
        result = graph.query("MATCH ()-[r]->() RETURN count(r) as c")
        rels = int(result[0]["c"])
    except Exception:
        pass

    return BuildResult(True, "langchain_neo4j", nodes, rels, f"Ingested {len(graph_docs)} graph documents into Neo4j.")

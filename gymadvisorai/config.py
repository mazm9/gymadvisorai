from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _opt_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default


@dataclass(frozen=True)
class Settings:

    # Neo4j
    neo4j_uri: str = _opt_env("NEO4J_URI", "") or ""
    neo4j_user: str = _opt_env("NEO4J_USER", "neo4j") or "neo4j"
    neo4j_password: str = _opt_env("NEO4J_PASSWORD", "") or ""
    neo4j_db: str = _opt_env("NEO4J_DB", "neo4j") or "neo4j"

    # LLM
    llm_enabled: bool = (_opt_env("LLM_ENABLED", "false") or "false").lower() in {"1", "true", "yes", "y"}

    openai_api_key: str | None = _opt_env("OPENAI_API_KEY")
    openai_endpoint: str | None = _opt_env("OPENAI_ENDPOINT")
    openai_model: str | None = _opt_env("OPENAI_MODEL")
    # Optional embeddings model for baseline RAG
    openai_embedding_model: str | None = _opt_env("OPENAI_EMBEDDING_MODEL")
    openai_api_version: str = _opt_env("OPENAI_API_VERSION", "2024-02-15-preview") or "2024-02-15-preview"


    openai_token_param: str = _opt_env("OPENAI_TOKEN_PARAM", "max_completion_tokens") or "max_completion_tokens"

    # Baseline RAG storage
    rag_store_path: str = _opt_env("RAG_STORE_PATH", "./.rag_store.pkl") or "./.rag_store.pkl"

    # Validation helpers
    def validate_neo4j(self) -> None:
        if not self.neo4j_uri:
            raise RuntimeError(
                "Missing NEO4J_URI. Create a .env in project root and set NEO4J_URI/USER/PASSWORD.\n"
                "For Neo4j Aura use: neo4j+s://<id>.databases.neo4j.io"
            )
        if not self.neo4j_password:
            raise RuntimeError("Missing NEO4J_PASSWORD in .env")

    def validate_llm(self) -> None:
        if not self.llm_enabled:
            return
        if not self.openai_api_key:
            raise RuntimeError("LLM_ENABLED=true but OPENAI_API_KEY is missing")
        if not self.openai_endpoint:
            raise RuntimeError("LLM_ENABLED=true but OPENAI_ENDPOINT is missing")
        if not self.openai_model:
            raise RuntimeError("LLM_ENABLED=true but OPENAI_MODEL is missing")

        # If OPENAI_EMBEDDING_MODEL is missing, baseline RAG will fall back to TF-IDF

        if self.openai_token_param not in {"max_tokens", "max_completion_tokens"}:
            raise RuntimeError(
                "OPENAI_TOKEN_PARAM must be 'max_tokens' or 'max_completion_tokens'. "
                f"Got: {self.openai_token_param}"
            )


settings = Settings()

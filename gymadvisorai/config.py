from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

@dataclass(frozen=True)
class Settings:
    openai_api_key: str = require_env("OPENAI_API_KEY")
    openai_model: str = require_env("OPENAI_MODEL")
    openai_endpoint: str = require_env("OPENAI_ENDPOINT")

    neo4j_uri: str = require_env("NEO4J_URI")
    neo4j_user: str = require_env("NEO4J_USER")
    neo4j_password: str = require_env("NEO4J_PASSWORD")
    neo4j_db: str = os.getenv("NEO4J_DB", "neo4j")

    chroma_dir: str = os.getenv("CHROMA_DIR", "./.chroma")
    #openai_embedding_model: str = require_env("OPENAI_EMBEDDING_MODEL")

settings = Settings()

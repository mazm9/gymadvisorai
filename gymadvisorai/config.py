from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = require_env("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    neo4j_uri: str = require_env("NEO4J_URI")
    neo4j_user: str = require_env("NEO4J_USER")
    neo4j_password: str = require_env("NEO4J_PASSWORD")
    neo4j_db: str = os.getenv("NEO4J_DB", "neo4j")


settings = Settings()

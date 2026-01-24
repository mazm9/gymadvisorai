from __future__ import annotations

from openai import AzureOpenAI
from gymadvisorai.config import settings

_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        if not settings.llm_enabled:
            raise RuntimeError("LLM is disabled (LLM_ENABLED=false).")
        if not settings.openai_api_key or not settings.openai_endpoint:
            raise RuntimeError("Azure OpenAI is not configured.")

        _client = AzureOpenAI(
            api_key=settings.openai_api_key,
            azure_endpoint=settings.openai_endpoint,
            api_version=settings.openai_api_version,
        )
    return _client


def llm_chat(prompt: str, *, max_tokens: int = 800) -> str:
    client = _get_client()
    model = settings.openai_model

    params = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional strength coach. "
                    "Be precise, structured, and respect all constraints."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    # Token parameter
    token_param = getattr(settings, "openai_token_param", None) or "max_completion_tokens"
    if token_param not in {"max_tokens", "max_completion_tokens"}:
        token_param = "max_completion_tokens"
    params[token_param] = int(max_tokens)

    allow_temp = getattr(settings, "openai_allow_temperature", False)
    if allow_temp:
        params["temperature"] = float(getattr(settings, "openai_temperature", 1.0))

    resp = client.chat.completions.create(**params)
    return resp.choices[0].message.content or ""


def llm_embed(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a list of texts (Azure OpenAI).

    Used by the baseline RAG to build a more realistic embedding index.
    Requires:
      - LLM_ENABLED=true
      - OPENAI_EMBEDDING_MODEL set
    """
    client = _get_client()
    model = settings.openai_embedding_model
    if not model:
        raise RuntimeError("OPENAI_EMBEDDING_MODEL is not set.")

    # Azure OpenAI embeddings API
    resp = client.embeddings.create(model=model, input=texts)
    # SDK returns objects with .embedding
    return [d.embedding for d in resp.data]
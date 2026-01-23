from openai import AzureOpenAI
from gymadvisorai.config import settings

_client = AzureOpenAI(
    api_key=settings.openai_api_key,
    api_version="2024-02-15-preview",
    azure_endpoint=settings.openai_endpoint,
)

def chat(text: str, max_tokens: int = 250, max_completion_tokens: int | None = None) -> str:
    mct = max_completion_tokens if max_completion_tokens is not None else max_tokens
    r = _client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": text}],
        max_completion_tokens=mct,
    )
    return (r.choices[0].message.content or "").strip()

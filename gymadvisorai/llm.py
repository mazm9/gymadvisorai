from openai import AzureOpenAI
from gymadvisorai.config import settings

_client = AzureOpenAI(
    api_key=settings.openai_api_key,
    azure_endpoint=settings.openai_endpoint,
    api_version="2024-02-15-preview",
)

def chat(text: str, max_completion_tokens: int = 250) -> str:
    r = _client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": text}],
        max_completion_tokens=max_completion_tokens,
    )
    return r.choices[0].message.content

from openai import AzureOpenAI
from gymadvisorai.config import settings

_client = AzureOpenAI(
    api_key=settings.openai_api_key,
    azure_endpoint=settings.openai_endpoint,
    api_version="2024-02-15-preview",
)

def embed(texts: list[str]) -> list[list[float]]:
    r = _client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [item.embedding for item in r.data]

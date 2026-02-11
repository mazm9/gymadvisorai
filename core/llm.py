from __future__ import annotations
import os, json
from pydantic import BaseModel
from openai import OpenAI

class LLMResponse(BaseModel):
    text: str

class BaseLLM:
    def generate(self, system: str, user: str) -> LLMResponse:
        raise NotImplementedError

class OpenAILLM(BaseLLM):
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, system: str, user: str) -> LLMResponse:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return LLMResponse(text=(resp.choices[0].message.content or ""))

class AzureOpenAILLM(BaseLLM):
    def __init__(self, api_key: str, endpoint: str, deployment: str, api_version: str):
        from openai import AzureOpenAI
        self.client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self.deployment = deployment

    def generate(self, system: str, user: str) -> LLMResponse:
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return LLMResponse(text=(resp.choices[0].message.content or ""))

class MockLLM(BaseLLM):
    def generate(self, system: str, user: str) -> LLMResponse:
        u = (system + "\n" + user).lower()
        if "return json" in u:
            if "next_tool" in u and "next_tool_input" in u:
                payload = {
                    "sufficient": True,
                    "reflection": "Observation is sufficient for a grounded answer.",
                    "next_tool": "none",
                    "next_tool_input": ""
                }
            else:
                tool = "vector_rag"
                if any(k in u for k in ["match", "dopas", "plan", "split", "program"]):
                    tool = "matcher"
                elif any(k in u for k in ["relac", "zale", "wynika", "powią", "path", "cause", "chain", "depends"]):
                    tool = "graph_rag"
                payload = {"intent": "Answer the question using tools if needed.", "tool": tool, "tool_input": user[:240]}
            return LLMResponse(text=json.dumps(payload, ensure_ascii=False))
        return LLMResponse(text="(MockLLM) Brak klucza. Ustaw LLM_PROVIDER + klucze w .env.")

def get_llm() -> BaseLLM:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "azure":
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01-preview").strip()
        if api_key and endpoint and deployment:
            return AzureOpenAILLM(api_key=api_key, endpoint=endpoint, deployment=deployment, api_version=api_version)
        return MockLLM()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        if api_key:
            return OpenAILLM(api_key=api_key, model=model)
        return MockLLM()

    return MockLLM()

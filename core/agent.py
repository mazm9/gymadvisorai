from __future__ import annotations
import json
from typing import Any, Dict, List

from core.llm import get_llm
from core.types import AgentResult, TraceStep, ToolName
from core import prompts
from core.utils import env_int

from tools.memory import Memory
from tools import vector_rag, graph_rag

def _parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                return {}
        return {}

def _summarize_vector(out: Dict[str, Any]) -> str:
    items = out.get("items", []) or []
    if not items:
        return "Vector RAG: no matches."
    lines = ["Vector RAG top snippets:"]
    for it in items[:5]:
        sid = it.get("id", "unknown")
        txt = (it.get("text","") or "").replace("\n"," ").strip()
        lines.append(f"- [{sid}] {txt[:240]}")
    return "\n".join(lines)

def _summarize_graph(out: Dict[str, Any]) -> str:
    mode = out.get("mode","local")
    nodes = out.get("matched_nodes", []) or []
    edges = out.get("edges", []) or []
    paths = out.get("paths", []) or []
    lines = [f"GraphRAG ({mode}) matches:"]
    if nodes:
        lines.append("Nodes: " + ", ".join(nodes[:10]))
    if edges:
        lines.append("Edges:")
        for e in edges[:10]:
            lines.append(f"- {e.get('source')} -[{e.get('relation')}]-> {e.get('target')}")
    if paths:
        lines.append("Paths:")
        for p in paths[:5]:
            lines.append("- " + " -> ".join(p))
    if out.get("warning"):
        lines.append(f"Warning: {out['warning']}")
    return "\n".join(lines)

class Agent:
    def __init__(self, memory: Memory | None = None):
        self.llm = get_llm()
        self.memory = memory or Memory()
        self.max_steps = env_int("AGENT_MAX_STEPS", 3)

    def run(self, user_query: str) -> AgentResult:
        trace: List[TraceStep] = []
        sources: List[Dict[str, Any]] = []

        router_user = f"""Question: {user_query}

Conversation memory:
{self.memory.as_text()}

{prompts.TOOL_ROUTER}
"""
        route_raw = self.llm.generate(prompts.SYSTEM, router_user).text
        route = _parse_json(route_raw)

        intent = (route.get("intent") or "Answer the user request.").strip()
        tool = route.get("tool") or "vector_rag"
        if tool not in ("vector_rag","graph_rag","none"):
            tool = "vector_rag"
        tool_input = (route.get("tool_input") or user_query).strip()

        last_observation = ""
        for step in range(1, self.max_steps + 1):
            if tool == "vector_rag":
                tool_out = vector_rag.query(tool_input)
                sources.append({"type":"vector_rag","items": tool_out.get("items", [])})
                observation = _summarize_vector(tool_out)
            elif tool == "graph_rag":
                tool_out = graph_rag.query(tool_input)
                sources.append({"type":"graph_rag","items": tool_out})
                observation = _summarize_graph(tool_out)
            else:
                observation = "No tool used."

            last_observation = observation

            ref_user = f"""User question: {user_query}
Intent: {intent}
Tool used: {tool}
Tool input: {tool_input}

Observation:
{observation}

{prompts.REFLECTION}
"""
            ref_raw = self.llm.generate(prompts.SYSTEM, ref_user).text
            refj = _parse_json(ref_raw)

            sufficient = bool(refj.get("sufficient", True))
            reflection = (refj.get("reflection") or "").strip() or "OK."
            next_tool = refj.get("next_tool") or "none"
            next_tool_input = (refj.get("next_tool_input") or "").strip()

            trace.append(TraceStep(
                step=step,
                intent=intent,
                tool=tool,  # type: ignore
                tool_input=tool_input,
                observation=observation,
                reflection=reflection
            ))

            if sufficient or next_tool == "none":
                break

            tool = next_tool if next_tool in ("vector_rag","graph_rag","none") else "vector_rag"
            tool_input = next_tool_input or tool_input

        answer_user = f"""User question: {user_query}

Intent: {intent}

Most relevant observation:
{last_observation}

Write the final answer in Polish.
Rules:
- Be concise and actionable.
- If you used vector_rag, cite sources as [source:<id>] using returned ids/filenames.
- If you used graph_rag, cite relations briefly like [graph:Squat->Quads].
- Do NOT invent sources. If info is missing, say what's missing.
"""
        answer = self.llm.generate(prompts.SYSTEM, answer_user).text.strip()

        self.memory.add(user_query, answer)
        return AgentResult(answer=answer, trace=trace, sources=sources)

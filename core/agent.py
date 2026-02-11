from __future__ import annotations
import json
from typing import Any, Dict, List

from .llm import get_llm
from .types import AgentResult, TraceStep
from . import prompts
from .utils import env_int

from tools.memory import Memory
from tools import vector_rag, graph_rag, matcher, analytics, graph_build
from tools import whatif
from tools.history import log_event


def _parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
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
        txt = (it.get("text", "") or "").replace("\n", " ").strip()
        lines.append(f"- [{sid}] {txt[:240]}")
    return "\n".join(lines)


def _summarize_graph(out: Dict[str, Any]) -> str:
    mode = out.get("mode", "local")
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


def _summarize_matcher(match_out: Dict[str, Any], plan_out: Dict[str, Any]) -> str:
    top = match_out.get("top", []) or []
    lines = [f"Matcher candidates: {match_out.get('count', 0)}", "Top picks:"]
    for it in top[:6]:
        reasons = ", ".join(it.get("reasons", []) or [])
        lines.append(f"- {it.get('name')} (score={it.get('score')}) {reasons}".strip())

    plan = (plan_out.get("plan") or {})
    if plan:
        lines.append("")
        lines.append("3-day split (draft):")
        for day, items in plan.items():
            names = [x.get("name", "") for x in (items or [])][:8]
            lines.append(f"- {day}: " + "; ".join(names))

    return "\n".join(lines)


class Agent:
    def __init__(self, memory: Memory | None = None):
        self.llm = get_llm()
        self.memory = memory or Memory()
        self.max_steps = env_int("AGENT_MAX_STEPS", 3)

    def run(self, user_query: str) -> AgentResult:
        trace: List[TraceStep] = []
        sources: List[Dict[str, Any]] = []

        ql = (user_query or "").strip().lower()
        if any(k in ql for k in ["what-if", "co jeśli", "co sie stanie", "co się stanie", "symul", "usuń sprzęt", "usun sprzet", "brak sprzętu", "brak sprzetu"]):
            forced_tool = "what_if"
        elif any(k in ql for k in ["policz", "zlicz", "ile ", "ile ćwicze", "ile cwicze", "ile jest", "suma", "średnia", "srednia", "agreg", "filtr", "posort"]):
            forced_tool = "analytics"
        else:
            forced_tool = None

        router_user = f"""Question: {user_query}

Conversation memory:
{self.memory.as_text()}

{prompts.TOOL_ROUTER}
"""
        route_raw = self.llm.generate(prompts.SYSTEM, router_user).text
        route = _parse_json(route_raw)

        intent = (route.get("intent") or "Answer the user request.").strip()
        tool = forced_tool or (route.get("tool") or "vector_rag")
        if tool not in ("matcher", "what_if", "analytics", "graph_build", "vector_rag", "graph_rag", "none"):
            tool = "vector_rag"
        tool_input = (route.get("tool_input") or user_query).strip()

        last_observation = ""
        for step in range(1, self.max_steps + 1):
            if tool == "matcher":
                m = matcher.match_exercises(tool_input)
                p = matcher.build_3day_split(m)
                log_event("match_result", {"query": user_query, "top": m.get("top", []), "plan": p.get("plan", {})});
                sources.append({"type": "matcher", "items": m})
                sources.append({"type": "plan_3day", "items": p})
                observation = _summarize_matcher(m, p)

            elif tool == "what_if":
                patch = _parse_json(tool_input)
                tool_out = whatif.simulate(patch if patch else {"note":"provide JSON patch"})
                sources.append({"type":"what_if","items": tool_out})
                observation = "What-if scenario:\n" + json.dumps(tool_out, ensure_ascii=False, indent=2)

            elif tool == "analytics":
                spec = _parse_json(tool_input)
                tool_out = analytics.run(spec if spec else {"op":"count","by":"tag"})
                sources.append({"type":"analytics","items": tool_out})
                observation = "Analytics:\n" + json.dumps(tool_out, ensure_ascii=False, indent=2)

            elif tool == "graph_build":
                tool_out = graph_build.build_from_docs()
                sources.append({"type":"graph_build","items": tool_out})
                observation = "Graph build (LLM extraction):\n" + json.dumps(tool_out, ensure_ascii=False, indent=2)

            elif tool == "vector_rag":
                tool_out = vector_rag.query(tool_input)
                sources.append({"type": "vector_rag", "items": tool_out.get("items", [])})
                observation = _summarize_vector(tool_out)

            elif tool == "graph_rag":
                tool_out = graph_rag.query(tool_input)
                sources.append({"type": "graph_rag", "items": tool_out})
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
                tool=tool,
                tool_input=tool_input,
                observation=observation,
                reflection=reflection
            ))

            if sufficient or next_tool == "none":
                break

            tool = next_tool if next_tool in ("matcher", "what_if", "analytics", "graph_build", "vector_rag", "graph_rag", "none") else "vector_rag"
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
- If you used matcher, cite picks like [match:<exercise_id>] and mention key reasons (equipment/injury/goal).
- If you used analytics, cite computed results like [calc].
- If you used graph_build, mention that the graph was extracted from docs and then queried.
- Do NOT invent sources. If info is missing, say what's missing.
"""
        answer = self.llm.generate(prompts.SYSTEM, answer_user).text.strip()

        self.memory.add(user_query, answer)
        return AgentResult(answer=answer, trace=trace, sources=sources)

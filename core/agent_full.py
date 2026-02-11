from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.llm import BaseLLM


@dataclass
class ToolCall:
    tool: str
    tool_input: Dict[str, Any]


@dataclass
class StepLog:
    step: int
    intent: str
    tool: str
    tool_input: Dict[str, Any]
    observation_summary: str


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        # sometimes model returns extra text; try to extract a JSON object
        m = None
        try:
            m = __import__("re").search(r"\{[\s\S]*\}", text)
        except Exception:
            m = None
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _truncate(s: str, n: int = 1800) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"



class AgentFull:
    """Tool-using reasoning agent with iterative planning and tool execution."""

    def __init__(self, llm: BaseLLM, max_steps: int | None = None):
        self.llm = llm
        self.max_steps = max_steps or int(os.getenv("AGENT_MAX_STEPS", "4"))

    def run(self, user_query: str, knowledge_mode: str = "auto") -> Tuple[str, Dict[str, Any]]:
        """Return (final_answer, debug_trace)."""
        trace: Dict[str, Any] = {
            "type": "agent_full",
            "knowledge_mode": knowledge_mode,
            "steps": [],
        }

        system = (
            "You are a planning agent for a training advisor app. "
            "You MUST use the provided tools when it improves correctness. "
            "Return STRICT JSON only (no markdown)."
        )

        tool_schema = {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "tool": {
                    "type": "string",
                    "enum": ["matcher", "analytics", "what_if", "vector_rag", "graph_rag", "none"],
                },
                "tool_input": {"type": "object"},
                "sufficient": {"type": "boolean"},
                "final_answer": {"type": "string"},
            },
            "required": ["intent", "tool", "tool_input", "sufficient", "final_answer"],
        }

        # conversation scratch (kept short)
        context_blocks: List[str] = []
        last_obs: str = ""

        for step in range(1, self.max_steps + 1):
            planner_prompt = (
                "Decide next action. If you need structured data or evidence, call a tool. "
                "If already sufficient, set tool=none and provide final_answer.\n\n"
                f"USER_QUERY:\n{user_query}\n\n"
                f"KNOWLEDGE_MODE:\n{knowledge_mode}\n\n"
                f"PREVIOUS_OBSERVATION:\n{_truncate(last_obs, 1200)}\n\n"
                "RETURN_JSON_SCHEMA:\n" + json.dumps(tool_schema) + "\n\n"
                "IMPORTANT RULES:\n"
                "- Use matcher for 'dobierz/dopasuj' and exercise recommendations.\n"
                "- Use analytics for 'policz/zlicz/ile/średnia/rozkład/top' and aggregations.\n"
                "- Use what_if when user asks about changes under constraints/time windows.\n"
                "- Use vector_rag for policy/guidelines justification from documents.\n"
                "- Use graph_rag for relations/constraints captured in graph.\n"
                "- If knowledge_mode is 'vector', prefer vector_rag; if 'graph', prefer graph_rag; if 'compare', you may call both.\n"
                "- Keep tool_input minimal and structured.\n"
            )

            raw = self.llm.generate(system, planner_prompt).text
            plan = _safe_json_loads(raw)
            if not plan:
                # fail safe: return raw as answer
                trace["planner_parse_error"] = True
                trace["planner_raw"] = raw
                return raw, trace

            intent = str(plan.get("intent", ""))
            tool = str(plan.get("tool", "none"))
            tool_input = plan.get("tool_input") or {}
            sufficient = bool(plan.get("sufficient", False))
            final_answer = str(plan.get("final_answer", ""))

            if tool == "none" or sufficient:
                trace["final_step"] = step
                trace["final_answer"] = final_answer
                return final_answer, trace

            obs = self._call_tool(tool, tool_input, user_query=user_query, knowledge_mode=knowledge_mode)
            last_obs = json.dumps(obs, ensure_ascii=False)[:5000]

            trace["steps"].append({
                "step": step,
                "intent": intent,
                "tool": tool,
                "tool_input": tool_input,
                "observation": obs,
            })

        # max steps reached -> synthesize from last observation
        synth_prompt = (
            "Synthesize a concise final answer using the last observation. "
            "If evidence exists, reference it briefly.\n\n"
            f"USER_QUERY:\n{user_query}\n\n"
            f"LAST_OBSERVATION_JSON:\n{_truncate(last_obs, 3500)}"
        )
        final = self.llm.generate("You are a helpful assistant.", synth_prompt).text
        trace["final_step"] = self.max_steps
        trace["final_answer"] = final
        trace["stopped_reason"] = "max_steps"
        return final, trace

    def _call_tool(self, tool: str, tool_input: Dict[str, Any], user_query: str, knowledge_mode: str) -> Dict[str, Any]:
        if tool == "matcher":
            from tools.matcher import match_exercises
            # tool_input may include overrides; if not, try to keep minimal.
            payload = dict(tool_input)
            payload.setdefault("query", user_query)
            return match_exercises(payload)

        if tool == "analytics":
            from tools.analytics import run as analytics_run
            return analytics_run(tool_input)

        if tool == "what_if":
            from tools.matcher import match_exercises
            # expected: {"baseline": {...}, "whatif": {...}, "top_n": 10}
            baseline = tool_input.get("baseline") or {}
            whatif = tool_input.get("whatif") or {}
            top_n = int(tool_input.get("top_n") or 10)
            b = match_exercises(baseline).get("top", [])[:top_n]
            w = match_exercises(whatif).get("top", [])[:top_n]
            b_ids = [x.get("id") for x in b if x.get("id")]
            w_ids = [x.get("id") for x in w if x.get("id")]
            diff = {
                "top_n": top_n,
                "removed": [i for i in b_ids if i not in w_ids],
                "added": [i for i in w_ids if i not in b_ids],
                "kept": [i for i in b_ids if i in w_ids],
            }
            return {"baseline": b, "whatif": w, "diff": diff}

        if tool == "vector_rag":
            from tools.vector_rag import query as vq
            q = tool_input.get("query") or user_query
            return vq(q)

        if tool == "graph_rag":
            from tools.graph_rag import query as gq
            q = tool_input.get("query") or user_query
            return gq(q)

        return {"error": f"Unknown tool: {tool}", "tool_input": tool_input}

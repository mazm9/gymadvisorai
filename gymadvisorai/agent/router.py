import json
from gymadvisorai.llm import chat

ROUTER_PROMPT = """You route gym questions to exactly one tool.
Return ONLY valid JSON with keys: tool, args.

TOOLS:
- count_sessions_last_days(args: {days:int})
- exercises_without_risk(args: {risk:str})
- tonnage_for_exercise_last_days(args: {exercise:str, days:int})
- primary_exercise_for_muscle(args: {muscle:str})
- last_session_for_exercise(args: {exercise:str})
- what_if_add_session(args: {sets:int, reps:int, weight:float})
- workout_summary_last_days(args: {days:int})
- unsupported(args: {reason:str})

HARD ROUTING RULES:
1. If the user asks for an opinion/assessment of their workout or routine
   (e.g. "what do you think about my workout", "is my routine good"),
   Always choose tool = workout_summary_last_days with days=30 (unless the user specifies days).
2. If the question doesn't fit any tool, choose tool=unsupported.

Return JSON only.

Question:
"""


def route(question: str) -> dict:
    raw = (chat(ROUTER_PROMPT + question, max_completion_tokens=200) or "").strip()

    try:
        r = json.loads(raw)
        if isinstance(r, dict) and "tool" in r:
            return r
    except Exception:
        pass

    return {"tool": "unsupported", "args": {"reason": "router_returned_invalid_json"}}

import json
from gymadvisorai.llm import chat

ROUTER_PROMPT = """You route gym analytics questions to one of these tools.
Return ONLY valid JSON with keys: tool, args.

Tools:
1) count_sessions_last_days(args: {days:int})
2) exercises_without_risk(args: {risk:str})
3) tonnage_for_exercise_last_days(args: {exercise:str, days:int})
4) primary_exercise_for_muscle(args: {muscle:str})
5) last_session_for_exercise(args: {exercise:str})
6) what_if_add_session(args: {sets:int, reps:int, weight:float})
7) workout_summary_last_days(args: {days:int})
8) unsupported(args: {reason:str})

Rules:
- If the question is not one of the tools above (general opinion, coaching, etc.), return tool=unsupported.
- If user doesn't specify days, use 30.
- Return JSON only.

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

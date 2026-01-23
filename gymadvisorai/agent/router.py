import json
from gymadvisorai.llm import chat

ROUTER_PROMPT = """You are routing gym analytics questions to one of 6 tools.
Return ONLY valid JSON with keys: tool, args.

Tools:
1) counting_sessions_last_days(args: {days:int})
2) filtering_exercises_without_risk(args: {risk:str})
3) aggregation_tonnage_exercise_last_days(args: {exercise:str, days:int})
4) reasoning_exercises_targeting_muscle(args: {muscle:str})
5) temporal_last_session_for_exercise(args: {exercise:str})
6) what_if_add_session_changes_muscle_tonnage(args: {muscle:str, add_sets:int, add_reps:int, add_weight:float, add_exercise:str, days:int})

Rules:
- If user doesn't specify days, use 30 (or 7 for what-if).
- Use exercise/muscle/risk names exactly as in the database if possible.
- Do not invent data.

Question:
"""

def route(question: str) -> dict:
    raw = chat(ROUTER_PROMPT + question, max_tokens=200)
    return json.loads(raw)

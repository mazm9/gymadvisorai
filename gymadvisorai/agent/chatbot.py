from gymadvisorai.graph.neo4j_client import Neo4jClient
from gymadvisorai.agent import queries
from gymadvisorai.agent.router import route
from gymadvisorai.llm import chat

USER_ID = "u1"


def _run(q: queries.Query) -> list[dict]:
    c = Neo4jClient()
    try:
        return c.run(q.cypher, **q.params)
    finally:
        c.close()


def answer(question: str) -> str:
    r = route(question)
    tool = r["tool"]
    args = r.get("args", {}) or {}

    if tool == "counting_sessions_last_days":
        q = queries.counting_sessions_last_days(USER_ID, days=int(args.get("days", 30)))
    elif tool == "filtering_exercises_without_risk":
        q = queries.filtering_exercises_without_risk(args["risk"])
    elif tool == "aggregation_tonnage_exercise_last_days":
        q = queries.aggregation_tonnage_exercise_last_days(
            USER_ID, args["exercise"], days=int(args.get("days", 30))
        )
    elif tool == "reasoning_exercises_targeting_muscle":
        q = queries.reasoning_can_train_today_based_on_overlap(args["muscle"])
    elif tool == "temporal_last_session_for_exercise":
        q = queries.temporal_last_session_for_exercise(USER_ID, args["exercise"])
    elif tool == "what_if_add_session_changes_muscle_tonnage":
        q = queries.what_if_add_session_changes_muscle_tonnage(
            USER_ID,
            muscle=args["muscle"],
            add_sets=int(args["add_sets"]),
            add_reps=int(args["add_reps"]),
            add_weight=float(args["add_weight"]),
            add_exercise=args["add_exercise"],
            days=int(args.get("days", 7)),
        )
    else:
        return "Unsupported question type."

    rows = _run(q)

    prompt = f"""Answer the user question ONLY using the query result.
Question: {question}
Tool: {tool}
Args: {args}
Result rows: {rows}

Return:
- short answer
- brief explanation of how it was computed (max 3 sentences)
"""
    return chat(prompt, max_tokens=250)

from gymadvisorai.graph.neo4j_client import Neo4jClient
import gymadvisorai.agent.queries as queries
from gymadvisorai.agent.router import route
from gymadvisorai.llm import chat

USER_ID = "u1"


def _run(q: queries.Query) -> list[dict]:
    c = Neo4jClient()
    try:
        return c.run(q.cypher, **q.params)
    finally:
        c.close()


def _missing(name: str) -> str:
    return f"Missing required argument: {name}."


def answer(question: str) -> str:
    r = route(question)
    tool = r.get("tool", "unsupported")
    args = r.get("args", {}) or {}

    if tool == "unsupported":
        return (
            "I can’t answer that with the available tools/data.\n"
            "Try a BI-style question, e.g.:\n"
            "- How many sessions did I do in the last 30 days?\n"
            "- What was my Bench Press tonnage in the last 30 days?\n"
            "- When was my last Deadlift and what were sets/reps/weight?\n"
        )

    match tool:
        case "count_sessions_last_days":
            q = queries.count_sessions_last_days(
                user_id=USER_ID,
                days=int(args.get("days", 30)),
            )

        case "exercises_without_risk":
            risk = args.get("risk")
            if not risk:
                return _missing("risk")
            q = queries.exercises_without_risk(risk=risk)

        case "tonnage_for_exercise_last_days":
            exercise = args.get("exercise")
            if not exercise:
                return _missing("exercise")
            q = queries.tonnage_for_exercise_last_days(
                USER_ID,
                exercise,
                days=int(args.get("days", 30)),
            )

        case "primary_exercise_for_muscle":
            muscle = args.get("muscle")
            if not muscle:
                return _missing("muscle")
            q = queries.primary_exercise_for_muscle(muscle=muscle)

        case "last_session_for_exercise":
            exercise = args.get("exercise")
            if not exercise:
                return _missing("exercise")
            q = queries.last_session_for_exercise(exercise=exercise)

        case "what_if_add_session":
            for k in ("sets", "reps", "weight"):
                if k not in args:
                    return _missing(k)
            q = queries.what_if_add_session(
                sets=int(args["sets"]),
                reps=int(args["reps"]),
                weight=float(args["weight"]),
            )
        
        case "workout_summary_last_days":
            q = queries.workout_summary_last_days(
                user_id=USER_ID,
                days=int(args.get("days", 30)),
            )

        case _:
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
    
    out = chat(prompt, max_completion_tokens=250)
    return out if out else f"No answer generated. Tool={tool}, args={args}, rows={rows}"


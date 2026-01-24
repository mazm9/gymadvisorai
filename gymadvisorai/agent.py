from __future__ import annotations
import re
from gymadvisorai import tools


_RE_DAYS = re.compile(r"(?:last|past)\s+(\d+)\s+days", re.I)
_RE_USER = re.compile(r"\buser\s+(u\d+)\b", re.I)


def _user_id(question: str, default: str = tools.DEFAULT_USER_ID) -> str:
    m = _RE_USER.search(question or "")
    return (m.group(1) if m else default).lower()


def _days(question: str, default: int = 30) -> int:
    m = _RE_DAYS.search(question or "")
    return int(m.group(1)) if m else default


def answer(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return ""

    ql = q.lower()
    uid = _user_id(q)

    # What-if
    if "what if" in ql and ("set" in ql or "sets" in ql) and ("rep" in ql or "reps" in ql):
        m = re.search(r"(\d+)\s*sets?", ql)
        sets = int(m.group(1)) if m else 0
        m = re.search(r"(\d+)\s*reps?", ql)
        reps = int(m.group(1)) if m else 0
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:kg|kgs|kilograms?)", ql)
        weight = float(m.group(1)) if m else 0.0
        return tools.what_if_add_session(sets=sets, reps=reps, weight=weight)

        # What-if reduce volume by x%
    if "what if" in ql and ("reduce" in ql or "less" in ql) and ("volume" in ql or "fatigue" in ql):
        m = re.search(r"(\d+)\s*%?", ql)
        pct = int(m.group(1)) if m else 20
        return tools.what_if_reduce_volume(percent=pct, user_id=uid)

# Counting
    if ("how many" in ql or "count" in ql) and "session" in ql:
        return tools.count_sessions_last_days(days=_days(q), user_id=uid)

    # Aggregation
    if "tonnage" in ql or ("total" in ql and "kg" in ql):
        ex = None
        m = re.search(r"\"([^\"]+)\"", q)
        if m:
            ex = m.group(1)
        if not ex:
            # common patterns
            for cand in ["bench press", "deadlift", "squat", "overhead press", "row"]:
                if cand in ql:
                    ex = cand
                    break
        if not ex:
            ex = q.split()[-1]
        return tools.tonnage_for_exercise_last_days(exercise=ex, days=_days(q), user_id=uid)

    # Temporal
    if "last" in ql and ("when" in ql or "what" in ql) and ("deadlift" in ql or "bench" in ql or "squat" in ql or "exercise" in ql):
        ex = None
        m = re.search(r"last\s+([a-z ]{3,40})", ql)
        if m:
            ex = m.group(1).strip().rstrip("?.")
        if not ex:
            ex = q.split()[-1]
        return tools.last_session_for_exercise(exercise=ex, user_id=uid)

    # Filtering
    if "without" in ql and "risk" in ql:
        m = re.search(r"without\s+([a-z0-9_ -]+)\s+risk", ql)
        risk = (m.group(1).strip() if m else "")
        return tools.exercises_without_risk(risk=risk, user_id=uid)

    # Reasoning
    if "plateau" in ql or "stuck" in ql or "why" in ql:
        ex = None
        for cand in ["bench press", "deadlift", "squat", "overhead press"]:
            if cand in ql:
                ex = cand
                break
        if not ex:
            ex = "exercise"
        return tools.plateau_reasoning(exercise=ex, user_id=uid)

    # Complex scenario
    # Matching (multi-user -> plan)
    if ("match" in ql or "best plan" in ql or "which plan" in ql) and ("plan" in ql or "program" in ql):
        return tools.match_training_plans(user_id=uid, top_k=3)

    if "plan" in ql or "program" in ql:
        goal = "general fitness"
        m = re.search(r"for\s+(.+)$", q, re.I)
        if m:
            goal = m.group(1).strip().rstrip("?.")
        return tools.propose_plan_from_brief(user_id=uid)

    # Fallback
    if "summary" in ql or "summarize" in ql:
        return tools.workout_summary_last_days(days=_days(q), user_id=uid)

    return (
        "I couldn't map your question to a supported tool. Try e.g.:\n"
        "- How many sessions did I do in the last 30 days?\n"
        "- What was my Bench Press tonnage in the last 30 days?\n"
        "- When was my last Deadlift?\n"
        "- Which exercises are without shoulder risk?\n"
        "- Why am I plateauing on bench press?\n"
        "- Plan a week for strength"
    )

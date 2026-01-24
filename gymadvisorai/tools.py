from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

from gymadvisorai.graph import Neo4jClient

DEFAULT_USER_ID = "u1"


def _date_n_days_ago(days: int) -> str:
    d = datetime.utcnow().date() - timedelta(days=int(days))
    return d.isoformat()


def count_sessions_last_days(days: int = 30, user_id: str = DEFAULT_USER_ID) -> str:
    c = Neo4jClient()
    try:
        since = _date_n_days_ago(days)
        res = c.run(
            "MATCH (u:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession) "
            "WHERE ws.date >= $since "
            "RETURN count(ws) AS n",
            u=user_id,
            since=since,
        )
        n = res[0]["n"] if res else 0
        return f"You did {n} session(s) in the last {days} day(s)."
    finally:
        c.close()


def exercises_without_risk(risk: str, user_id: str = DEFAULT_USER_ID) -> str:
    # return exercises that do not have given risk tag
    c = Neo4jClient()
    try:
        risk_in = (risk or "").strip()
        if not risk_in:
            return "Provide a risk tag (e.g., shoulder, lower back)."

        # find best matching risk tag
        rows = c.run(
            "MATCH (r:RiskTag) WHERE toLower(r.name) = toLower($x) RETURN r.name AS name LIMIT 1",
            x=risk_in,
        )
        risk_db = rows[0]["name"] if rows else risk_in

        res = c.run(
            "MATCH (e:Exercise) "
            "WHERE NOT (e)-[:HAS_RISK]->(:RiskTag {name:$risk}) "
            "RETURN e.name AS name ORDER BY name LIMIT 25",
            risk=risk_db,
            )
        names = [r["name"] for r in res]
        if not names:
            return f"No exercises found without risk '{risk}'."
        return "Exercises without risk '%s': %s" % (risk, ", ".join(names))
    finally:
        c.close()


def tonnage_for_exercise_last_days(exercise: str, days: int = 30, user_id: str = DEFAULT_USER_ID) -> str:
    c = Neo4jClient()
    try:
        ex = (exercise or "").strip()
        if not ex:
            return "Provide an exercise name."
        since = _date_n_days_ago(days)
        res = c.run(
            "MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)-[r:INCLUDES]->(e:Exercise {name:$ex}) "
            "WHERE ws.date >= $since "
            "RETURN sum(r.sets * r.reps * r.weight) AS tonnage",
            u=user_id,
            ex=ex,
            since=since,
        )
        t = res[0]["tonnage"] if res else 0
        t = t or 0
        return f"Tonnage for {ex} in the last {days} day(s): {t:.1f}"
    finally:
        c.close()


def primary_exercise_for_muscle(muscle: str) -> str:
    c = Neo4jClient()
    try:
        m = (muscle or "").strip()
        if not m:
            return "Provide a muscle group (e.g., chest, back, quads)."
        res = c.run(
            "MATCH (e:Exercise)-[:TARGETS]->(m:MuscleGroup {name:$m}) "
            "RETURN e.name AS name ORDER BY name LIMIT 1",
            m=m,
        )
        if not res:
            return f"No primary exercise found for muscle '{m}'."
        return f"A primary exercise for {m}: {res[0]['name']}"
    finally:
        c.close()


def last_session_for_exercise(exercise: str, user_id: str = DEFAULT_USER_ID) -> str:
    c = Neo4jClient()
    try:
        ex = (exercise or "").strip()
        if not ex:
            return "Provide an exercise name."
        res = c.run(
            "MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)-[r:INCLUDES]->(e:Exercise {name:$ex}) "
            "RETURN ws.date AS date, r.sets AS sets, r.reps AS reps, r.weight AS weight "
            "ORDER BY ws.date DESC LIMIT 1",
            u=user_id,
            ex=ex,
        )
        if not res:
            return f"No recorded session for {ex}."
        row = res[0]
        return f"Last {ex}: {row['date']} — {row['sets']}x{row['reps']} @ {row['weight']}"
    finally:
        c.close()


def workout_summary_last_days(days: int = 30, user_id: str = DEFAULT_USER_ID) -> str:
    c = Neo4jClient()
    try:
        since = _date_n_days_ago(days)
        res = c.run(
            "MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession) "
            "WHERE ws.date >= $since "
            "OPTIONAL MATCH (ws)-[r:INCLUDES]->(e:Exercise) "
            "RETURN count(DISTINCT ws) AS sessions, count(r) AS entries, count(DISTINCT e) AS exercises, "
            "min(ws.date) AS from, max(ws.date) AS to, sum(r.sets*r.reps*r.weight) AS tonnage",
            u=user_id,
            since=since,
        )
        row = res[0] if res else {}
        return (
            f"Summary last {days} day(s): sessions={row.get('sessions',0)}, "
            f"entries={row.get('entries',0)}, unique_exercises={row.get('exercises',0)}, "
            f"range={row.get('from')}..{row.get('to')}, tonnage={float(row.get('tonnage') or 0):.1f}"
        )
    finally:
        c.close()


def what_if_add_session(sets: int, reps: int, weight: float) -> str:
    sets = int(sets)
    reps = int(reps)
    weight = float(weight)
    tonnage = sets * reps * weight
    return f"What-if tonnage: {sets}x{reps} @ {weight} = {tonnage:.1f}"


# Additional tools to cover reasoning and complex scenario requirements

def plateau_reasoning(exercise: str, user_id: str = DEFAULT_USER_ID) -> str:
    """Reasoning-style query: detect plateau by comparing last 3 vs previous 3 sessions."""
    c = Neo4jClient()
    try:
        ex = (exercise or "").strip()
        if not ex:
            return "Provide an exercise name to analyze plateau."
        rows = c.run(
            "MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)-[r:INCLUDES]->(:Exercise {name:$ex}) "
            "WITH ws.date AS d, (r.weight) AS w, (r.sets*r.reps) AS vol "
            "ORDER BY d DESC "
            "RETURN d AS date, w AS weight, vol AS reps_total LIMIT 6",
            u=user_id,
            ex=ex,
        )
        if len(rows) < 4:
            return f"Not enough history for {ex} to assess plateau (need ~6 sessions)."
        last3 = rows[:3]
        prev3 = rows[3:6]
        avg_last = sum(float(r['weight'] or 0) for r in last3) / len(last3)
        avg_prev = sum(float(r['weight'] or 0) for r in prev3) / len(prev3)
        delta = avg_last - avg_prev
        if abs(delta) < 0.5:
            verdict = "Plateau suspected (avg weight unchanged)."
        elif delta > 0:
            verdict = "Progressing (avg weight increased)."
        else:
            verdict = "Regressing (avg weight decreased)."
        return (
            f"Plateau check for {ex}: avg(last3)={avg_last:.1f}, avg(prev3)={avg_prev:.1f}, delta={delta:.1f}. {verdict}"
        )
    finally:
        c.close()




def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _norm_equipment(s: str) -> str:
    s = _norm(s)
    s = s.replace("pullup bar", "pull-up bar")
    s = s.replace("pull up bar", "pull-up bar")
    return s


def _fetch_latest_brief(c: Neo4jClient, user_id: str) -> dict[str, Any] | None:
    rows = c.run(
        """
        MATCH (:User {user_id:$u})-[:HAS_BRIEF]->(b:WorkoutBrief)
        WITH b
        ORDER BY coalesce(b.updated_at, datetime('1970-01-01T00:00:00Z')) DESC
        LIMIT 1
        OPTIONAL MATCH (b)-[:FOCUS]->(m:MuscleGroup)
        OPTIONAL MATCH (b)-[:CONSTRAINT]->(r:RiskTag)
        OPTIONAL MATCH (b)-[:HAS_EQUIPMENT]->(e:Equipment)
        RETURN
        b.goal AS goal,
        b.days_per_week AS days,
        b.minutes_per_session AS mins,
        b.experience_level AS level,
        collect(DISTINCT m.name) AS focus,
        collect(DISTINCT r.name) AS constraints,
        collect(DISTINCT e.name) AS equipment
        """,
        u=user_id,
    )

    if not rows:
        return None
    b = rows[0]
    return {
        "goal": b.get("goal") or "General fitness",
        "days_per_week": int(b.get("days") or 3),
        "minutes_per_session": int(b.get("mins") or 45),
        "experience_level": b.get("level") or "Intermediate",
        "focus": [x for x in (b.get("focus") or []) if x],
        "constraints": [x for x in (b.get("constraints") or []) if x],
        "equipment": [x for x in (b.get("equipment") or []) if x],
    }


def _fetch_exercises(c: Neo4jClient) -> list[dict[str, Any]]:
    rows = c.run(
        "MATCH (ex:Exercise) "
        "OPTIONAL MATCH (ex)-[:TARGETS]->(m:MuscleGroup) "
        "OPTIONAL MATCH (ex)-[:HAS_RISK]->(r:RiskTag) "
        "OPTIONAL MATCH (ex)-[:USES]->(eq:Equipment) "
        "RETURN ex.name AS name, collect(DISTINCT m.name) AS targets, "
        "       collect(DISTINCT r.name) AS risks, collect(DISTINCT eq.name) AS equipment "
    )
    out = []
    for r in rows:
        out.append(
            {
                "name": r.get("name"),
                "targets": [x for x in (r.get("targets") or []) if x],
                "risks": [x for x in (r.get("risks") or []) if x],
                "equipment": [x for x in (r.get("equipment") or []) if x],
            }
        )
    return out


def _allowed_exercises(exercises: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = {_norm(x) for x in (brief.get("constraints") or [])}
    eq_have = {_norm_equipment(x) for x in (brief.get("equipment") or [])}

    allowed = []
    for ex in exercises:
        name = ex.get("name")
        if not name:
            continue

        risks = {_norm(x) for x in (ex.get("risks") or [])}

        if constraints and (risks & constraints):
            continue

        req_eq = {_norm_equipment(x) for x in (ex.get("equipment") or [])}
        if eq_have and req_eq and not req_eq.issubset(eq_have):
            continue

        allowed.append(ex)
    return allowed


def _has(exs: list[dict[str, Any]], name: str) -> bool:
    n = _norm(name)
    return any(_norm(e.get("name") or "") == n for e in exs)


def _pick_by_keywords(exs: list[dict[str, Any]], keywords: list[str]) -> str | None:
    # best effort exact
    for kw in keywords:
        kwl = _norm(kw)
        for e in exs:
            nm = _norm(e.get("name") or "")
            if nm == kwl:
                return e["name"]
    for kw in keywords:
        kwl = _norm(kw)
        for e in exs:
            nm = _norm(e.get("name") or "")
            if kwl in nm:
                return e["name"]
    return None


def _build_plan_json(brief: dict[str, Any], allowed: list[dict[str, Any]], volume_multiplier: float = 1.0) -> dict[str, Any]:
    """Deterministic plan builder (the 'tool' part). LLM will later polish/justify."""
    goal = _norm(brief.get("goal") or "")
    constraints = brief.get("constraints") or []
    days = int(brief.get("days_per_week") or 3)
    mins = int(brief.get("minutes_per_session") or 45)

    # priorities inferred from goal text
    want_bench = "bench" in goal
    want_pull = ("pull-up" in goal) or ("pullup" in goal) or ("pull up" in goal) or ("pull" in goal and "up" in goal)
    # safe defaults for demo
    bench = _pick_by_keywords(allowed, ["Bench Press"]) if want_bench else _pick_by_keywords(allowed, ["Bench Press"])
    pullup = _pick_by_keywords(allowed, ["Pull-up", "Pull Up"]) if want_pull else _pick_by_keywords(allowed, ["Pull-up"])

    squat = _pick_by_keywords(allowed, ["Squat"])
    hinge = _pick_by_keywords(allowed, ["Romanian Deadlift", "Deadlift"])

    row = _pick_by_keywords(allowed, ["Cable Row", "Row"])
    core = _pick_by_keywords(allowed, ["Plank"])

    # simple set-scaling
    def ceil_int(x: float) -> int:
        return max(1, int(math.ceil(x)))

    def scale_sets(sets: int, is_main: bool) -> int:
        return sets if is_main else ceil_int(sets * volume_multiplier)

    # time-based cap on number of movements
    max_moves = 4 if mins <= 50 else 5

    # Build a sensible 3day template:
    plan_days: list[dict[str, Any]] = []

    def add_day(name: str, movements: list[dict[str, Any]]):
        # cap number of movements for time
        plan_days.append({"name": name, "movements": movements[:max_moves]})

    is_strength = "strength" in goal or "power" in goal

    # rep schemes
    if is_strength:
        mainA = {"sets": 5, "reps": "3", "rir": 2, "rest": "2–3 min"}
        mainB = {"sets": 4, "reps": "4–6", "rir": 2, "rest": "2–3 min"}
        acc = {"sets": 3, "reps": "8–12", "rir": 2, "rest": "60–90s"}
        prehab = {"sets": 2, "reps": "15–20", "rir": 3, "rest": "60s"}
    else:
        mainA = {"sets": 4, "reps": "6–8", "rir": 2, "rest": "2 min"}
        mainB = {"sets": 3, "reps": "8–10", "rir": 2, "rest": "90s"}
        acc = {"sets": 3, "reps": "10–15", "rir": 2, "rest": "60–90s"}
        prehab = {"sets": 2, "reps": "15–20", "rir": 3, "rest": "60s"}

    # Shoulder constraint
    face_pull = _pick_by_keywords(allowed, ["Face Pull"])
    ext_rot = _pick_by_keywords(allowed, ["External Rotations", "External Rotation"])

    # Day 1
    d1 = []
    if bench:
        d1.append({"exercise": bench, "sets": scale_sets(mainA["sets"], True), "reps": mainA["reps"], "rir": mainA["rir"], "rest": mainA["rest"], "tag": "main"})
    if pullup:
        d1.append({"exercise": pullup, "sets": scale_sets(mainA["sets"], True), "reps": mainA["reps"], "rir": mainA["rir"], "rest": mainA["rest"], "tag": "main"})
    if row:
        d1.append({"exercise": row, "sets": scale_sets(acc["sets"], False), "reps": acc["reps"], "rir": acc["rir"], "rest": acc["rest"], "tag": "accessory"})
    if face_pull:
        d1.append({"exercise": face_pull, "sets": scale_sets(prehab["sets"], False), "reps": prehab["reps"], "rir": prehab["rir"], "rest": prehab["rest"], "tag": "prehab"})
    if core:
        d1.append({"exercise": core, "sets": scale_sets(2, False), "reps": "45–60s", "rir": None, "rest": "", "tag": "core"})
    add_day("Day 1 — Upper Strength", d1)

    # Day 2
    d2 = []
    if squat:
        d2.append({"exercise": squat, "sets": scale_sets(mainA["sets"], True), "reps": mainA["reps"], "rir": mainA["rir"], "rest": mainA["rest"], "tag": "main"})
    if hinge:
        d2.append({"exercise": hinge, "sets": scale_sets(mainB["sets"], True), "reps": mainB["reps"], "rir": mainB["rir"], "rest": mainB["rest"], "tag": "main"})
    if core and core not in [m.get("exercise") for m in d2]:
        d2.append({"exercise": core, "sets": scale_sets(2, False), "reps": "30–45s", "rir": None, "rest": "", "tag": "core"})
    add_day("Day 2 — Lower Strength", d2)

    # Day 3
    d3 = []
    if bench:
        d3.append({"exercise": bench, "sets": scale_sets(4, True), "reps": "6" if is_strength else "8", "rir": 2, "rest": "2 min", "tag": "main"})
    if pullup:
        d3.append({"exercise": pullup, "sets": scale_sets(4, True), "reps": "6" if is_strength else "8", "rir": 2, "rest": "2 min", "tag": "main"})
    if row:
        d3.append({"exercise": row, "sets": scale_sets(2 if mins <= 45 else 3, False), "reps": "10–12", "rir": 2, "rest": "60–90s", "tag": "accessory"})
    if ext_rot:
        d3.append({"exercise": ext_rot, "sets": scale_sets(prehab["sets"], False), "reps": prehab["reps"], "rir": prehab["rir"], "rest": prehab["rest"], "tag": "prehab"})
    add_day("Day 3 — Upper Volume", d3)

    # Truncate or extend for different days_per_week
    if days < 3:
        plan_days = plan_days[:days]
    elif days > 3:
        # repeat day1/day2 pattern
        extra = []
        while len(plan_days) + len(extra) < days:
            extra.append(plan_days[(len(plan_days) + len(extra)) % 3])
        plan_days = plan_days + extra

    plan = {
        "meta": {
            "goal": brief.get("goal"),
            "days_per_week": days,
            "minutes_per_session": mins,
            "focus": brief.get("focus") or [],
            "constraints": constraints,
            "equipment": brief.get("equipment") or [],
            "experience_level": brief.get("experience_level"),
        },
        "days": plan_days,
        "progression": {
            "weeks": 4,
            "rule": "Add +1 rep per set weekly until top of range; then add +2.5kg and reset reps.",
            "deload": "Week 4: reduce accessory volume by ~30% (keep main lifts crisp).",
        },
        "allowed_exercises": sorted({e["name"] for e in allowed if e.get("name")}),
        "volume_multiplier": float(volume_multiplier),
    }
    return plan


def _render_plan_deterministic(plan: dict[str, Any]) -> str:
    m = plan["meta"]
    lines = []
    lines.append(
        f"Plan ({m['days_per_week']} days/week, ~{m['minutes_per_session']} min/session) — Goal: {m.get('goal')}"
    )
    if m.get("focus"):
        lines.append(f"Focus: {', '.join(m['focus'])}")
    if m.get("constraints"):
        lines.append(f"Constraints: {', '.join(m['constraints'])}")
    if m.get("equipment"):
        lines.append(f"Equipment: {', '.join(m['equipment'])}")
    lines.append("")
    for d in plan["days"]:
        lines.append(d["name"])
        for mv in d["movements"]:
            bits = [f"{mv['exercise']} — {mv['sets']}x{mv['reps']}"]
            if mv.get("rir") is not None:
                bits.append(f"RIR {mv['rir']}")
            if mv.get("rest"):
                bits.append(f"rest {mv['rest']}")
            lines.append("  - " + " | ".join(bits))
        lines.append("")
    prog = plan.get("progression") or {}
    lines.append("Progression (4 weeks):")
    lines.append(f"  - {prog.get('rule')}")
    lines.append(f"  - {prog.get('deload')}")
    return "\n".join(lines)


def _polish_with_llm(brief: dict[str, Any], plan: dict[str, Any], *, mode: str = "plan", extra: str = "") -> str:
    """LLM does: formatting + coaching rationale + what-if explanation.
    Tools do: constraints, selection, numbers.
    """
    from gymadvisorai.llm import llm_chat

    system = (
        "You are a professional strength coach and a careful planner. "
        "You must obey the user's constraints and equipment. "
        "You MUST NOT invent exercises outside the provided allowed_exercises list. "
        "Be concrete and structured."
    )

    prompt = f"""
USER BRIEF (JSON):
{json.dumps(brief, ensure_ascii=False, indent=2)}

DRAFT PLAN (JSON):
{json.dumps(plan, ensure_ascii=False, indent=2)}

IMPORTANT RULES:
- Use only exercises from plan.allowed_exercises.
- Obey constraints (risk tags already filtered).
- Keep within days_per_week and minutes_per_session.
- Make it specific: sets, reps, RIR, rest, and a 4-week progression.
- Output should be easy to present on slides (clean sections).

TASK:
- If mode=plan: produce the best possible plan and add short rationale.
- If mode=what_if: explain changes and list what changed vs baseline.
{extra}

OUTPUT FORMAT (strict):
Title line
Summary (goal, constraints, equipment, estimated time)
Day-by-day plan with bullets
Progression (4 weeks)
Rationale (3-6 bullets)
"""

    try:
        out = llm_chat(f"SYSTEM:\\n{system}\\n\\nUSER:\\n{prompt}", max_tokens=950)
        return out.strip() if out.strip() else _render_plan_deterministic(plan)
    except Exception:
        # If LLM is not available, fall back to deterministic rendering
        return _render_plan_deterministic(plan)


def propose_plan_from_brief(user_id: str = DEFAULT_USER_ID) -> str:
    """Complex scenario / matching:
    Latest WorkoutBrief (requirements) -> weekly plan (resources) with constraints.
    """
    c = Neo4jClient()
    try:
        brief = _fetch_latest_brief(c, user_id=user_id)
        if not brief:
            return (
                "No WorkoutBrief found for this user. Ingest the sample brief PDF first:\n"
                "  python -m gymadvisorai.app --ingest-pdf gymadvisorai/data/sample_user_brief.pdf\n"
                "Then ask: 'Create a plan'."
            )

        exercises = _fetch_exercises(c)
        allowed = _allowed_exercises(exercises, brief)
        if not allowed:
            return "No exercises match your constraints/equipment. Try relaxing constraints or updating the brief."

        plan = _build_plan_json(brief, allowed, volume_multiplier=1.0)
        return _polish_with_llm(brief, plan, mode="plan")
    finally:
        c.close()

def match_training_plans(user_id: str = DEFAULT_USER_ID, top_k: int = 3) -> str:
    """Match a user profile to the best training plans.

    Transparent score from graph signals:
    + focus overlap
    - risk conflicts
    - missing equipment
    - days-per-week mismatch
    """
    c = Neo4jClient()
    try:
        top_k = max(1, min(10, int(top_k)))

        rows = c.run(
            """
            MATCH (u:User {user_id:$u})-[:HAS_BRIEF]->(b:WorkoutBrief)
            OPTIONAL MATCH (b)-[:FOCUS]->(uf:MuscleGroup)
            OPTIONAL MATCH (b)-[:CONSTRAINT]->(ur:RiskTag)
            OPTIONAL MATCH (b)-[:HAS_EQUIPMENT]->(ue:Equipment)
            WITH b,
                 collect(DISTINCT uf) AS uFocus,
                 collect(DISTINCT ur) AS uRisks,
                 collect(DISTINCT ue) AS uEq
            MATCH (p:TrainingPlan)
            OPTIONAL MATCH (p)-[:FOCUS]->(pf:MuscleGroup)
            OPTIONAL MATCH (p)-[:REQUIRES_EQUIPMENT]->(pe:Equipment)
            OPTIONAL MATCH (p)-[:CONTAINS]->(:Exercise)-[:HAS_RISK]->(pr:RiskTag)
            WITH p,
                 collect(DISTINCT pf) AS pFocus,
                 collect(DISTINCT pe) AS pEq,
                 collect(DISTINCT pr) AS pRisks,
                 uFocus,uRisks,uEq,b
            WITH p,
                 size([x IN pFocus WHERE x IN uFocus]) AS focus_overlap,
                 size([x IN pEq WHERE NOT x IN uEq]) AS missing_eq,
                 size([x IN pRisks WHERE x IN uRisks]) AS risk_conflicts,
                 abs(toInteger(coalesce(p.days_per_week,0)) - toInteger(coalesce(b.days_per_week,0))) AS days_diff
            WITH p, focus_overlap, missing_eq, risk_conflicts, days_diff,
                 (5*focus_overlap - 10*missing_eq - 8*risk_conflicts - 1*days_diff) AS score
            RETURN p.name AS plan,
                   score AS score,
                   focus_overlap AS focus_overlap,
                   missing_eq AS missing_equipment,
                   risk_conflicts AS risk_conflicts,
                   days_diff AS days_diff,
                   p.days_per_week AS plan_days,
                   p.minutes_per_session AS plan_minutes
            ORDER BY score DESC, focus_overlap DESC
            LIMIT $k
            """,
            u=user_id,
            k=top_k,
        )

        if not rows:
            return f"No user/profile found for user_id='{user_id}'. Run seed first: python -m gymadvisorai.app --seed"

        lines = [f"Top {len(rows)} training plan matches for user '{user_id}':"]
        for i, r in enumerate(rows, 1):
            lines.append(
                f"{i}. {r['plan']} (score={float(r['score']):.1f}) | "
                f"focus_overlap={r['focus_overlap']} | risk_conflicts={r['risk_conflicts']} | "
                f"missing_equipment={r['missing_equipment']} | days_diff={r['days_diff']}"
            )
        lines.append("\nTip: ask 'What-if: user u2 can train 1 extra day per week' to recompute ranking.")
        return "\n".join(lines)
    finally:
        c.close()



def what_if_match(user_id: str = DEFAULT_USER_ID, delta_days: int = 1, top_k: int = 3) -> str:
    """
    What-if matching: recompute plan ranking assuming user can train delta_days more/less per week.
    No DB writes — only modifies days_per_week in-query.
    """
    c = Neo4jClient()
    try:
        top_k = max(1, min(10, int(top_k)))
        delta_days = int(delta_days)

        rows = c.run(
            """
            MATCH (u:User {user_id:$u})-[:HAS_BRIEF]->(b:WorkoutBrief)
            WITH b, (toInteger(coalesce(b.days_per_week,0)) + $delta) AS adj_days
            OPTIONAL MATCH (b)-[:FOCUS]->(uf:MuscleGroup)
            OPTIONAL MATCH (b)-[:CONSTRAINT]->(ur:RiskTag)
            OPTIONAL MATCH (b)-[:HAS_EQUIPMENT]->(ue:Equipment)
            WITH b, adj_days,
                 collect(DISTINCT uf) AS uFocus,
                 collect(DISTINCT ur) AS uRisks,
                 collect(DISTINCT ue) AS uEq

            MATCH (p:TrainingPlan)
            OPTIONAL MATCH (p)-[:FOCUS]->(pf:MuscleGroup)
            OPTIONAL MATCH (p)-[:REQUIRES_EQUIPMENT]->(pe:Equipment)
            OPTIONAL MATCH (p)-[:CONTAINS]->(:Exercise)-[:HAS_RISK]->(pr:RiskTag)
            WITH p,
                 collect(DISTINCT pf) AS pFocus,
                 collect(DISTINCT pe) AS pEq,
                 collect(DISTINCT pr) AS pRisks,
                 uFocus, uRisks, uEq, adj_days

            WITH p,
                 size([x IN pFocus WHERE x IN uFocus]) AS focus_overlap,
                 size([x IN pEq WHERE NOT x IN uEq]) AS missing_eq,
                 size([x IN pRisks WHERE x IN uRisks]) AS risk_conflicts,
                 abs(toInteger(coalesce(p.days_per_week,0)) - adj_days) AS days_diff,
                 adj_days AS assumed_user_days

            WITH p, focus_overlap, missing_eq, risk_conflicts, days_diff, assumed_user_days,
                 (5*focus_overlap - 10*missing_eq - 8*risk_conflicts - 1*days_diff) AS score

            RETURN p.name AS plan,
                   score AS score,
                   focus_overlap AS focus_overlap,
                   missing_eq AS missing_equipment,
                   risk_conflicts AS risk_conflicts,
                   days_diff AS days_diff,
                   assumed_user_days AS assumed_user_days,
                   p.days_per_week AS plan_days
            ORDER BY score DESC, focus_overlap DESC
            LIMIT $k
            """,
            u=user_id,
            delta=delta_days,
            k=top_k,
        )

        if not rows:
            return f"No user/profile found for user_id='{user_id}'. Run seed first: python -m gymadvisorai.app --seed"

        sign = "+" if delta_days >= 0 else ""
        lines = [f"What-if match for user '{user_id}' assuming days_per_week {sign}{delta_days}:"]
        lines.append(f"(assumed user days/week = {rows[0]['assumed_user_days']})")
        for i, r in enumerate(rows, 1):
            lines.append(
                f"{i}. {r['plan']} (score={float(r['score']):.1f}) | "
                f"focus_overlap={r['focus_overlap']} | risk_conflicts={r['risk_conflicts']} | "
                f"missing_equipment={r['missing_equipment']} | days_diff={r['days_diff']}"
            )

        lines.append("\nTip: ask 'Compare ranking vs baseline for this user' to explain changes.")
        return "\n".join(lines)

    finally:
        c.close()


def what_if_reduce_volume(percent: int = 20, user_id: str = DEFAULT_USER_ID) -> str:
    """What-if scenario:
    Reduce accessory volume by X% (main lifts unchanged), then explain the differences.
    """
    pct = max(0, min(90, int(percent)))
    mult = 1.0 - (pct / 100.0)

    c = Neo4jClient()
    try:
        brief = _fetch_latest_brief(c, user_id=user_id)
        if not brief:
            return (
                "No WorkoutBrief found for this user. Ingest the sample brief PDF first:\n"
                "  python -m gymadvisorai.app --ingest-pdf gymadvisorai/data/sample_user_brief.pdf"
            )

        exercises = _fetch_exercises(c)
        allowed = _allowed_exercises(exercises, brief)
        if not allowed:
            return "No exercises match your constraints/equipment. Try relaxing constraints or updating the brief."

        baseline = _build_plan_json(brief, allowed, volume_multiplier=1.0)
        after = _build_plan_json(brief, allowed, volume_multiplier=mult)

        def count_accessory_sets(plan: dict[str, Any]) -> int:
            total = 0
            for d in plan["days"]:
                for mv in d["movements"]:
                    if mv.get("tag") in {"accessory", "prehab", "core"}:
                        total += int(mv.get("sets") or 0)
            return total

        b_sets = count_accessory_sets(baseline)
        a_sets = count_accessory_sets(after)
        delta = a_sets - b_sets
        extra = f"\\nBASELINE accessory sets: {b_sets}\\nAFTER accessory sets: {a_sets} (delta {delta})\\n"

        # Attach baseline for the LLM to explain diffs
        after_with_baseline = dict(after)
        after_with_baseline["baseline"] = baseline
        return _polish_with_llm(brief, after_with_baseline, mode="what_if", extra=extra)
    finally:
        c.close()

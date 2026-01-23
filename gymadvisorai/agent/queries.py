from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass(frozen=True)
class Query:
    name: str
    cypher: str
    params: dict

def _range_last_days(days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()

def counting_sessions_last_days(user_id: str, days: int = 30) -> Query:
    start, end = _range_last_days(days)
    return Query(
        name="counting_sessions_last_days",
        cypher="""
            MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)
            WHERE ws.date >= $start AND ws.date <= $end
            RETURN count(ws) AS sessions
        """,
        params={"u": user_id, "start": start, "end": end},
    )

def filtering_exercises_without_risk(risk: str) -> Query:
    return Query(
        name="filtering_exercises_without_risk",
        cypher="""
            MATCH (e:Exercise)
            WHERE NOT (e)-[:HAS_RISK]->(:RiskTag {name:$risk})
            RETURN e.name AS exercise
            ORDER BY exercise
        """,
        params={"risk": risk},
    )

def aggregation_tonnage_exercise_last_days(user_id: str, exercise: str, days: int = 30) -> Query:
    start, end = _range_last_days(days)
    return Query(
        name="aggregation_tonnage_exercise_last_days",
        cypher="""
            MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)-[r:INCLUDES]->(e:Exercise {name:$ex})
            WHERE ws.date >= $start AND ws.date <= $end
            RETURN sum(r.sets * r.reps * r.weight) AS tonnage
        """,
        params={"u": user_id, "ex": exercise, "start": start, "end": end},
    )

def reasoning_can_train_today_based_on_overlap(muscle: str) -> Query:
    return Query(
        name="reasoning_exercises_targeting_muscle",
        cypher="""
            MATCH (e:Exercise)-[:TARGETS]->(m:MuscleGroup {name:$m})
            RETURN e.name AS exercise
            ORDER BY exercise
        """,
        params={"m": muscle},
    )

def temporal_last_session_for_exercise(user_id: str, exercise: str) -> Query:
    return Query(
        name="temporal_last_session_for_exercise",
        cypher="""
            MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)-[r:INCLUDES]->(e:Exercise {name:$ex})
            RETURN ws.date AS date, r.sets AS sets, r.reps AS reps, r.weight AS weight
            ORDER BY ws.date DESC
            LIMIT 1
        """,
        params={"u": user_id, "ex": exercise},
    )

def what_if_add_session_changes_muscle_tonnage(
    user_id: str,
    muscle: str,
    add_sets: int,
    add_reps: int,
    add_weight: float,
    add_exercise: str,
    days: int = 7,
) -> Query:
    start, end = _range_last_days(days)
    return Query(
        name="what_if_add_session_changes_muscle_tonnage",
        cypher="""
            // current tonnage for muscle in window
            MATCH (:User {user_id:$u})-[:PERFORMED]->(ws:WorkoutSession)-[r:INCLUDES]->(e:Exercise)-[:TARGETS]->(m:MuscleGroup {name:$muscle})
            WHERE ws.date >= $start AND ws.date <= $end
            WITH sum(r.sets * r.reps * r.weight) AS current

            // does the hypothetical exercise target this muscle?
            OPTIONAL MATCH (:Exercise {name:$add_ex})-[:TARGETS]->(:MuscleGroup {name:$muscle})
            WITH current, count(*) > 0 AS targets

            WITH current,
                 CASE WHEN targets THEN ($sets * $reps * $weight) ELSE 0 END AS added

            RETURN current, added, (current + added) AS after
        """,
        params={
            "u": user_id,
            "muscle": muscle,
            "start": start,
            "end": end,
            "sets": add_sets,
            "reps": add_reps,
            "weight": add_weight,
            "add_ex": add_exercise,
        },
    )

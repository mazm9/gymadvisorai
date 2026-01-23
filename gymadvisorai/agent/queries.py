from dataclasses import dataclass

@dataclass(frozen=True)
class Query:
    cypher: str
    params: dict


def count_sessions_last_days(user_id: str, days: int) -> Query:
    return Query(
        cypher="""
        MATCH (u:User {user_id: $user_id})-[:PERFORMED]->(s:WorkoutSession)
        WHERE date(s.date) >= date() - duration({days: $days})
        RETURN count(s) AS sessions
        """,
        params={"user_id": user_id, "days": days},
    )


def exercises_without_risk(risk: str) -> Query:
    return Query(
        cypher="""
        MATCH (e:Exercise)
        WHERE NOT (e)-[:HAS_RISK]->(:RiskTag {name: $risk})
        RETURN e.name AS exercise
        ORDER BY exercise
        """,
        params={"risk": risk},
    )



def tonnage_for_exercise_last_days(user_id: str, exercise: str, days: int) -> Query:
    return Query(
        cypher="""
        MATCH (u:User {user_id: $user_id})-[:PERFORMED]->(s:WorkoutSession)-[r:INCLUDES]->(e:Exercise {name: $exercise})
        WHERE date(s.date) >= date() - duration({days: $days})
        RETURN coalesce(sum(r.sets * r.reps * r.weight), 0) AS tonnage
        """,
        params={"user_id": user_id, "exercise": exercise, "days": days},
    )



def primary_exercise_for_muscle(muscle: str) -> Query:
    return Query(
        cypher="""
        MATCH (e:Exercise)-[:TARGETS]->(m:MuscleGroup {name: $muscle})
        RETURN e.name AS exercise
        LIMIT 1
        """,
        params={"muscle": muscle},
    )



def last_session_for_exercise(exercise: str) -> Query:
    return Query(
        cypher="""
        MATCH (s:WorkoutSession)-[r:INCLUDES]->(e:Exercise {name: $exercise})
        RETURN s.date AS date, r.sets AS sets, r.reps AS reps, r.weight AS weight
        ORDER BY s.date DESC
        LIMIT 1
        """,
        params={"exercise": exercise},
    )



def what_if_add_session(sets: int, reps: int, weight: float) -> Query:
    return Query(
        cypher="""
        RETURN 
          0 AS current,
          $sets * $reps * $weight AS added,
          $sets * $reps * $weight AS after
        """,
        params={"sets": sets, "reps": reps, "weight": weight},
    )

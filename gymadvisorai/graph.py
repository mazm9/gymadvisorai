from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from neo4j import GraphDatabase

from gymadvisorai.config import settings


# Minimal schema to support Graph RAG queries.
SCHEMA: list[str] = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
    "CREATE CONSTRAINT exercise_name IF NOT EXISTS FOR (e:Exercise) REQUIRE e.name IS UNIQUE",
    "CREATE CONSTRAINT muscle_name IF NOT EXISTS FOR (m:MuscleGroup) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT equipment_name IF NOT EXISTS FOR (eq:Equipment) REQUIRE eq.name IS UNIQUE",
    "CREATE CONSTRAINT risk_name IF NOT EXISTS FOR (r:RiskTag) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT session_key IF NOT EXISTS FOR (ws:WorkoutSession) REQUIRE (ws.user_id, ws.date) IS UNIQUE",
    "CREATE CONSTRAINT brief_user_id IF NOT EXISTS FOR (b:WorkoutBrief) REQUIRE b.user_id IS UNIQUE",
    "CREATE CONSTRAINT plan_name IF NOT EXISTS FOR (p:TrainingPlan) REQUIRE p.name IS UNIQUE",
]


@dataclass
class Neo4jClient:
    """Neo4j wrapper."""

    uri: str = settings.neo4j_uri
    user: str = settings.neo4j_user
    password: str = settings.neo4j_password
    database: str = settings.neo4j_db

    def __post_init__(self) -> None:
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        self._driver.close()

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session(database=self.database) as sess:
            res = sess.run(query, **params)
            return [r.data() for r in res]


def ensure_schema(client: Neo4jClient) -> None:
    for q in SCHEMA:
        client.run(q)


def upsert_training_plan(
    client: Neo4jClient,
    *,
    name: str,
    days_per_week: int,
    minutes_per_session: int,
    focus: Iterable[str] = (),
    equipment: Iterable[str] = (),
    exercises: Iterable[str] = (),
) -> None:
    ensure_schema(client)
    client.run(
        "MERGE (p:TrainingPlan {name:$n}) "
        "SET p.days_per_week=$d, p.minutes_per_session=$m, "
        "    p.updated_at=datetime(), p.created_at=coalesce(p.created_at, datetime())",
        n=name,
        d=int(days_per_week),
        m=int(minutes_per_session),
    )

    # Reset relations
    client.run(
        "MATCH (p:TrainingPlan {name:$n})-[r:FOCUS|REQUIRES_EQUIPMENT|CONTAINS]->() DELETE r",
        n=name,
    )

    for m in focus:
        client.run("MERGE (mg:MuscleGroup {name:$n})", n=m)
        client.run(
            "MATCH (p:TrainingPlan {name:$p}),(mg:MuscleGroup {name:$m}) MERGE (p)-[:FOCUS]->(mg)",
            p=name,
            m=m,
        )

    for eq in equipment:
        client.run("MERGE (e:Equipment {name:$n})", n=eq)
        client.run(
            "MATCH (p:TrainingPlan {name:$p}),(e:Equipment {name:$q}) MERGE (p)-[:REQUIRES_EQUIPMENT]->(e)",
            p=name,
            q=eq,
        )

    for ex in exercises:
        client.run("MERGE (e:Exercise {name:$e})", e=ex)
        client.run(
            "MATCH (p:TrainingPlan {name:$p}),(e:Exercise {name:$e}) MERGE (p)-[:CONTAINS]->(e)",
            p=name,
            e=ex,
        )


def upsert_exercise_taxonomy(
    client: Neo4jClient,
    *,
    name: str,
    targets: Iterable[str] = (),
    equipment: Iterable[str] = (),
    risks: Iterable[str] = (),
) -> None:
    client.run("MERGE (e:Exercise {name:$n})", n=name)
    for m in targets:
        client.run("MERGE (m:MuscleGroup {name:$n})", n=m)
        client.run(
            "MATCH (e:Exercise {name:$e}),(m:MuscleGroup {name:$m}) MERGE (e)-[:TARGETS]->(m)",
            e=name,
            m=m,
        )
    for eq in equipment:
        client.run("MERGE (eq:Equipment {name:$n})", n=eq)
        client.run(
            "MATCH (e:Exercise {name:$e}),(eq:Equipment {name:$q}) MERGE (e)-[:USES]->(eq)",
            e=name,
            q=eq,
        )
    for r in risks:
        client.run("MERGE (r:RiskTag {name:$n})", n=r)
        client.run(
            "MATCH (e:Exercise {name:$e}),(r:RiskTag {name:$r}) MERGE (e)-[:HAS_RISK]->(r)",
            e=name,
            r=r,
        )


def ingest_sessions(client: Neo4jClient, sessions: list[dict[str, Any]], user_id: str = "u1") -> int:
    """Ingest sessions in the shape:

    {"sessions": [{"date": "YYYY-MM-DD", "items": [{"exercise":.., "sets":.., "reps":.., "weight":..}]}]}
    """

    ensure_schema(client)
    client.run("MERGE (u:User {user_id:$u})", u=user_id)

    ingested = 0
    for s in sessions or []:
        date = s.get("date")
        if not date:
            continue

        client.run("MERGE (ws:WorkoutSession {user_id:$u, date:$d})", u=user_id, d=date)
        client.run(
            "MATCH (u:User {user_id:$u}),(ws:WorkoutSession {user_id:$u, date:$d}) MERGE (u)-[:PERFORMED]->(ws)",
            u=user_id,
            d=date,
        )

        for it in s.get("items", []) or []:
            ex = it.get("exercise")
            if not ex:
                continue
            sets = int(it.get("sets", 0) or 0)
            reps = int(it.get("reps", 0) or 0)
            w = float(it.get("weight", 0) or 0)

            client.run("MERGE (e:Exercise {name:$e})", e=ex)
            client.run(
                "MATCH (ws:WorkoutSession {user_id:$u, date:$d}),(e:Exercise {name:$e}) "
                "MERGE (ws)-[r:INCLUDES]->(e) "
                "SET r.sets=$s, r.reps=$rps, r.weight=$w",
                u=user_id,
                d=date,
                e=ex,
                s=sets,
                rps=reps,
                w=w,
            )

        ingested += 1

    return ingested


def upsert_workout_brief(
    client: Neo4jClient,
    *,
    user_id: str,
    goal: str,
    days_per_week: int,
    minutes_per_session: int,
    focus: Iterable[str] = (),
    constraints: Iterable[str] = (),
    equipment: Iterable[str] = (),
    experience_level: str | None = None,
) -> None:
    """Upsert the latest workout brief for a user.
    """
    ensure_schema(client)
    client.run("MERGE (u:User {user_id:$u})", u=user_id)
    client.run(
        "MERGE (b:WorkoutBrief {user_id:$u}) "
        "SET b.goal=$g, b.days_per_week=$d, b.minutes_per_session=$m, "
        "    b.experience_level=$lvl, "
        "    b.created_at = coalesce(b.created_at, datetime()), "
        "    b.updated_at = datetime()",
        u=user_id,
        g=goal,
        d=int(days_per_week),
        m=int(minutes_per_session),
        lvl=experience_level,
    )
    client.run(
        "MATCH (u:User {user_id:$u}),(b:WorkoutBrief {user_id:$u}) MERGE (u)-[:HAS_BRIEF]->(b)",
        u=user_id,
    )

    # Reset relations
    client.run("MATCH (b:WorkoutBrief {user_id:$u})-[r:FOCUS|CONSTRAINT|HAS_EQUIPMENT]->() DELETE r", u=user_id)

    for m in focus:
        client.run("MERGE (mg:MuscleGroup {name:$n})", n=m)
        client.run(
            "MATCH (b:WorkoutBrief {user_id:$u}),(mg:MuscleGroup {name:$m}) MERGE (b)-[:FOCUS]->(mg)",
            u=user_id,
            m=m,
        )

    for r in constraints:
        client.run("MERGE (rt:RiskTag {name:$n})", n=r)
        client.run(
            "MATCH (b:WorkoutBrief {user_id:$u}),(rt:RiskTag {name:$r}) MERGE (b)-[:CONSTRAINT]->(rt)",
            u=user_id,
            r=r,
        )

    for eq in equipment:
        client.run("MERGE (e:Equipment {name:$n})", n=eq)
        client.run(
            "MATCH (b:WorkoutBrief {user_id:$u}),(e:Equipment {name:$q}) MERGE (b)-[:HAS_EQUIPMENT]->(e)",
            u=user_id,
            q=eq,
        )

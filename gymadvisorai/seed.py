from __future__ import annotations

from pathlib import Path

from gymadvisorai.data_loader import load_json
from gymadvisorai.graph import (
    Neo4jClient,
    ensure_schema,
    ingest_sessions,
    upsert_exercise_taxonomy,
    upsert_training_plan,
    upsert_workout_brief,
)

from gymadvisorai.pdf_ingest import (
    ingest_training_plans_pdf,
    ingest_user_profiles_pdf,
    ingest_workout_logs_pdf,
)


def seed_demo(user_id: str = "u1") -> None:
    seed_demo_multi()

def seed_demo_multi(
    users: list[str] | None = None,
    use_pdfs: bool = False,
    pdf_dir: str | None = None,
) -> None:
    """Seed Neo4j with demo dataset.

    This version seeds:
      - exercise taxonomy
      - multiple users (user briefs)
      - training plans (the thing we *match* users to)
      - sessions for u1 (so temporal/aggregation queries still work)
    """
    c = Neo4jClient()
    try:
        ensure_schema(c)

        users_data = load_json("users.json")
        plans_data = load_json("training_plans.json")
        knowledge = load_json("exercise_knowledge.json")
        workouts = load_json("workouts.json")

        c.run("MATCH (ws:WorkoutSession) DETACH DELETE ws")
        c.run("MATCH (b:WorkoutBrief) DETACH DELETE b")
        c.run("MATCH (p:TrainingPlan) DETACH DELETE p")
        c.run("MATCH (u:User) DETACH DELETE u")

        # Taxonomy
        for ex in knowledge.get("exercises", []):
            name = ex.get("name")
            if not name:
                continue
            upsert_exercise_taxonomy(
                c,
                name=name,
                targets=ex.get("targets", []) or [],
                equipment=ex.get("equipment", []) or [],
                risks=ex.get("risk", []) or [],
            )

        # Plans
        if use_pdfs:
            d = Path(pdf_dir) if pdf_dir else (Path(__file__).parent / "data")
            pdf = next(iter(sorted(d.glob("*plans*pdf"))), None)
            if pdf:
                ingest_training_plans_pdf(str(pdf))
            else:
                for p in plans_data.get("plans", []) or []:
                    upsert_training_plan(
                        c,
                        name=p["name"],
                        days_per_week=int(p.get("days_per_week") or 3),
                        minutes_per_session=int(p.get("minutes_per_session") or 45),
                        focus=p.get("focus", []) or [],
                        equipment=p.get("equipment", []) or [],
                        exercises=p.get("exercises", []) or [],
                    )
        else:
            for p in plans_data.get("plans", []) or []:
                upsert_training_plan(
                    c,
                    name=p["name"],
                    days_per_week=int(p.get("days_per_week") or 3),
                    minutes_per_session=int(p.get("minutes_per_session") or 45),
                    focus=p.get("focus", []) or [],
                    equipment=p.get("equipment", []) or [],
                    exercises=p.get("exercises", []) or [],
                )

        # users + sessions
        requested = set(users or []) if users else None

        if use_pdfs:
            d = Path(pdf_dir) if pdf_dir else (Path(__file__).parent / "data")

            # prefer unstructured profiles PDF if present
            prof_pdf = next(iter(sorted(d.glob("*profile*pdf"))), None)
            if prof_pdf:
                ingest_user_profiles_pdf(str(prof_pdf))
            else:
                # JSON fallback
                for u in users_data.get("users", []) or []:
                    uid = u.get("user_id")
                    if not uid:
                        continue
                    if requested and uid not in requested:
                        continue
                    c.run(
                        "MERGE (u:User {user_id:$u}) SET u.display_name=$n",
                        u=uid,
                        n=u.get("display_name") or uid,
                    )
                    upsert_workout_brief(
                        c,
                        user_id=uid,
                        goal=u.get("goal") or "General fitness",
                        days_per_week=int(u.get("days_per_week") or 3),
                        minutes_per_session=int(u.get("minutes_per_session") or 45),
                        focus=u.get("focus", []) or [],
                        constraints=u.get("constraints", []) or [],
                        equipment=u.get("equipment", []) or [],
                        experience_level=u.get("experience_level") or "Intermediate",
                    )

            # prefer unstructured workout logs PDF if present
            logs_pdf = next(iter(sorted(d.glob("*log*pdf"))), None)
            if logs_pdf:
                ingest_workout_logs_pdf(str(logs_pdf))
            else:
                # JSON fallback
                sessions = workouts.get("sessions", []) or []
                by_user: dict[str, list[dict]] = {}
                for s in sessions:
                    uid = s.get("user_id", "u1")
                    by_user.setdefault(uid, []).append(s)
                for uid, sess in by_user.items():
                    if requested and uid not in requested:
                        continue
                    ingest_sessions(c, sess, user_id=uid)

        else:
            for u in users_data.get("users", []) or []:
                uid = u.get("user_id")
                if not uid:
                    continue
                if requested and uid not in requested:
                    continue
                c.run(
                    "MERGE (u:User {user_id:$u}) SET u.display_name=$n",
                    u=uid,
                    n=u.get("display_name") or uid,
                )
                upsert_workout_brief(
                    c,
                    user_id=uid,
                    goal=u.get("goal") or "General fitness",
                    days_per_week=int(u.get("days_per_week") or 3),
                    minutes_per_session=int(u.get("minutes_per_session") or 45),
                    focus=u.get("focus", []) or [],
                    constraints=u.get("constraints", []) or [],
                    equipment=u.get("equipment", []) or [],
                    experience_level=u.get("experience_level") or "Intermediate",
                )

            sessions = workouts.get("sessions", []) or []
            by_user: dict[str, list[dict]] = {}
            for s in sessions:
                uid = s.get("user_id", "u1")
                by_user.setdefault(uid, []).append(s)
            for uid, sess in by_user.items():
                if requested and uid not in requested:
                    continue
                ingest_sessions(c, sess, user_id=uid)

    finally:
        c.close()

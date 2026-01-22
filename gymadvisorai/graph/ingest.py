from gymadvisorai.data_loader import load_json
from gymadvisorai.graph.neo4j_client import Neo4jClient


def main():
    knowledge = load_json("exercise_knowledge.json")
    workouts = load_json("workouts.json")

    user_id = workouts["user_id"]
    c = Neo4jClient()
    try:
        c.run("MERGE (u:User {user_id:$id})", id=user_id)

        # exercise knowledge
        for ex in knowledge["exercises"]:
            c.run("MERGE (e:Exercise {name:$n})", n=ex["name"])

            for mg in ex.get("targets", []):
                c.run("MERGE (m:MuscleGroup {name:$m})", m=mg)
                c.run(
                    "MATCH (e:Exercise {name:$e}),(m:MuscleGroup {name:$m}) "
                    "MERGE (e)-[:TARGETS]->(m)",
                    e=ex["name"], m=mg
                )

            for eq in ex.get("equipment", []):
                c.run("MERGE (q:Equipment {name:$q})", q=eq)
                c.run(
                    "MATCH (e:Exercise {name:$e}),(q:Equipment {name:$q}) "
                    "MERGE (e)-[:REQUIRES]->(q)",
                    e=ex["name"], q=eq
                )

            for rt in ex.get("risk", []):
                c.run("MERGE (r:RiskTag {name:$r})", r=rt)
                c.run(
                    "MATCH (e:Exercise {name:$e}),(r:RiskTag {name:$r}) "
                    "MERGE (e)-[:HAS_RISK]->(r)",
                    e=ex["name"], r=rt
                )

        # workout sessions
        for s in workouts["sessions"]:
            c.run(
                "MERGE (ws:WorkoutSession {user_id:$u, date:$d})",
                u=user_id, d=s["date"]
            )
            c.run(
                "MATCH (u:User {user_id:$u}),(ws:WorkoutSession {user_id:$u, date:$d}) "
                "MERGE (u)-[:PERFORMED]->(ws)",
                u=user_id, d=s["date"]
            )

            for it in s["items"]:
                c.run("MERGE (e:Exercise {name:$e})", e=it["exercise"])
                c.run(
                    "MATCH (ws:WorkoutSession {user_id:$u, date:$d}),(e:Exercise {name:$e}) "
                    "MERGE (ws)-[r:INCLUDES]->(e) "
                    "SET r.sets=$sets, r.reps=$reps, r.weight=$w",
                    u=user_id, d=s["date"], e=it["exercise"],
                    sets=it["sets"], reps=it["reps"], w=it["weight"]
                )

        print("ingest ok")
    finally:
        c.close()


if __name__ == "__main__":
    main()

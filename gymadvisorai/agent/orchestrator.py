from __future__ import annotations
from gymadvisorai.graph.neo4j_client import Neo4jClient
from gymadvisorai.agent.queries import (
    counting_sessions_last_days,
    filtering_exercises_without_risk,
    aggregation_tonnage_exercise_last_days,
    reasoning_can_train_today_based_on_overlap,
    temporal_last_session_for_exercise,
    what_if_add_session_changes_muscle_tonnage,
)

USER_ID = "u1"  # na start stałe, później z profilu / logowania

def run_query(q):
    c = Neo4jClient()
    try:
        return c.run(q.cypher, **q.params)
    finally:
        c.close()

def demo():
    print("COUNTING:", run_query(counting_sessions_last_days(USER_ID, 30)))
    print("FILTERING:", run_query(filtering_exercises_without_risk("LowBack")))
    print("AGG:", run_query(aggregation_tonnage_exercise_last_days(USER_ID, "Bench Press", 30)))
    print("REASONING:", run_query(reasoning_can_train_today_based_on_overlap("Chest")))
    print("TEMPORAL:", run_query(temporal_last_session_for_exercise(USER_ID, "Deadlift")))
    print("WHAT-IF:", run_query(what_if_add_session_changes_muscle_tonnage(
        USER_ID, muscle="Shoulders", add_sets=3, add_reps=8, add_weight=50, add_exercise="Overhead Press", days=7
    )))

if __name__ == "__main__":
    demo()

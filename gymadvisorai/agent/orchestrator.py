from gymadvisorai.graph.neo4j_client import Neo4jClient
import gymadvisorai.agent.queries as queries

USER_ID = "u1"

def run_query(q: queries.Query):
    c = Neo4jClient()
    try:
        return c.run(q.cypher, **q.params)
    finally:
        c.close()

def demo():
    print("COUNTING:", run_query(queries.count_sessions_last_days(USER_ID, 30)))
    print("FILTERING:", run_query(queries.exercises_without_risk("LowBack")))
    print("AGG:", run_query(queries.tonnage_for_exercise_last_days("Bench Press", 30)))
    print("REASONING:", run_query(queries.primary_exercise_for_muscle("Chest")))
    print("TEMPORAL:", run_query(queries.last_session_for_exercise("Deadlift")))
    print("WHAT-IF:", run_query(queries.what_if_add_session(sets=3, reps=8, weight=50)))

if __name__ == "__main__":
    demo()

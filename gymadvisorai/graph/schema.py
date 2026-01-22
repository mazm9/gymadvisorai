SCHEMA = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
    "CREATE CONSTRAINT exercise_name IF NOT EXISTS FOR (e:Exercise) REQUIRE e.name IS UNIQUE",
    "CREATE CONSTRAINT muscle_name IF NOT EXISTS FOR (m:MuscleGroup) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT equipment_name IF NOT EXISTS FOR (eq:Equipment) REQUIRE eq.name IS UNIQUE",
    "CREATE CONSTRAINT risk_name IF NOT EXISTS FOR (r:RiskTag) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT session_key IF NOT EXISTS FOR (ws:WorkoutSession) REQUIRE (ws.user_id, ws.date) IS UNIQUE",
]

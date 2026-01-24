# GymAdvisorAI — RAG vs GraphRAG evaluation
## Summary
| Mode | Accuracy | Avg latency (ms) | Numeric MAE | List P@5 | List R@5 | Reasoning score |
|---|---:|---:|---:|---:|---:|---:|
| GraphRAG | 0.250 | 1316.2 | 524.333 | 1.0 | 0.217 | 0.111 |
| RAG | 0.000 | 4093.7 | 598.333 | 0.0 | 0.0 | 0.0 |

## Per-case results (short)
| Mode | Case | OK | Latency (ms) | Preview |
|---|---|---:|---:|---|
| graphrag | count_sessions_last_30 | 0 | 1575.3 | You did 4 session(s) in the last 30 day(s). |
| graphrag | bench_tonnage_last_30 | 0 | 1494.8 | Tonnage for bench press in the last 30 day(s): 0.0 |
| graphrag | last_squat_date | 0 | 1436.2 | No recorded session for squat. |
| graphrag | safe_exercises_no_shoulder | 1 | 1507.4 | Exercises without risk 'shoulder': Back Squat, Barbell Row, Biceps Curl, Calf Raise, Cycling, Deadlift, Front Squat, Goblet Squat, Hanging Knee Raise, Hip Thrust, Incline Walk, Kettlebell Swing, Lat Pulldown, Leg Curl, Leg Press, Plank, Pul |
| graphrag | plateau_reasoning_bench | 0 | 1335.5 | Not enough history for bench press to assess plateau (need ~6 sessions). |
| graphrag | what_if_add_sets | 0 | 0.9 | What-if tonnage: 3x10 @ 50.0 = 1500.0 |
| graphrag | matching_u2_best_plan | 0 | 1573.9 | Top 3 training plan matches for user 'u2': 1. Powerbuilding 5D (score=-28.0) \| focus_overlap=1 \| risk_conflicts=0 \| missing_equipment=3 \| days_diff=3 2. Hypertrophy Upper/Lower 4D (score=-32.0) \| focus_overlap=0 \| risk_conflicts=0 \| missing |
| graphrag | matching_u3_best_plan | 1 | 1605.9 | Top 3 training plan matches for user 'u3': 1. Hypertrophy Upper/Lower 4D (score=-31.0) \| focus_overlap=0 \| risk_conflicts=0 \| missing_equipment=3 \| days_diff=1 2. Endurance + Strength 4D (score=-31.0) \| focus_overlap=0 \| risk_conflicts=0 \|  |
| rag | count_sessions_last_30 | 0 | 6279.4 | RAG baseline (retrieval=tfidf). Top snippets: PDF:workout_logs_synthetic.pdf Workout Logs Summary (Synthetic) Total sessions: 173 across 10 users. Date range: 2025-09-25 to 2026-01-23. User u1 - Session Summary Number of sessions: 16. First |
| rag | bench_tonnage_last_30 | 0 | 3841.8 | RAG baseline (retrieval=tfidf). Top snippets: PDF:workout_logs_synthetic.pdf Workout Logs Summary (Synthetic) Total sessions: 173 across 10 users. Date range: 2025-09-25 to 2026-01-23. User u1 - Session Summary Number of sessions: 16. First |
| rag | last_squat_date | 0 | 3785.6 | RAG baseline (retrieval=tfidf). Top snippets: PDF:workout_logs_synthetic.pdf Workout Logs Summary (Synthetic) Total sessions: 173 across 10 users. Date range: 2025-09-25 to 2026-01-23. User u1 - Session Summary Number of sessions: 16. First |
| rag | safe_exercises_no_shoulder | 0 | 3532.6 | RAG baseline (retrieval=tfidf). Top snippets: Exercise: Lateral Raise Targets: Shoulders Equipment: Dumbbells, Cable Risk: Shoulder --- Exercise: Incline Dumbbell Press Targets: Chest, Shoulders, Triceps Equipment: Dumbbells Risk: Shoulder  |
| rag | plateau_reasoning_bench | 0 | 3529.9 | RAG baseline (retrieval=tfidf). Top snippets: UserProfile: u8 Goal: Rehab & mobility DaysPerWeek: 3 Minutes: 40 Focus: General fitness Constraints: Limit spinal loading Equipment: Barbell, Cable, Kettlebell, Machine Level: Beginner --- Trai |
| rag | what_if_add_sets | 0 | 4258.9 | RAG baseline (retrieval=tfidf). Top snippets: PDF:sample_user_brief.pdf GymAdvisorAI - User Profile & Workout Brief User ID: u1 Created: 2026-01-23 Goal: Strength (build bench + pull-up strength) Focus Muscles: Chest, Back Days Per Week: 3  |
| rag | matching_u2_best_plan | 0 | 3421.6 | RAG baseline (retrieval=tfidf). Top snippets: PDF:user_profiles_synthetic.pdf User Profile: User 1 (u1) Goal: Endurance. Experience: Advanced. Preferred training frequency: 2 days/week, 30 minutes/session. Focus areas: Rehab & mobility. Con |
| rag | matching_u3_best_plan | 0 | 4099.5 | RAG baseline (retrieval=tfidf). Top snippets: PDF:user_profiles_synthetic.pdf User Profile: User 1 (u1) Goal: Endurance. Experience: Advanced. Preferred training frequency: 2 days/week, 30 minutes/session. Focus areas: Rehab & mobility. Con |

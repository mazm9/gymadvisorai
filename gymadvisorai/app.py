from __future__ import annotations
import argparse
import json
from gymadvisorai.config import settings
from gymadvisorai.agent import answer as answer_graphrag
from gymadvisorai.pdf_ingest import (
    ingest_training_plans_pdf,
    ingest_user_profiles_pdf,
    ingest_workout_logs_pdf,
    ingest_workout_pdf,
)
from gymadvisorai.rag import answer_with_rag, build_rag_from_local_json
from gymadvisorai.seed import seed_demo, seed_demo_multi
from gymadvisorai.eval import run_eval
import re
from gymadvisorai.tools import match_training_plans, what_if_match, propose_plan_from_brief



HELP_TEXT = """Supported commands:
  help                Show this help
  exit / quit         Exit

Quickstart (Windows + Neo4j Aura TLS):
  1) .\run.ps1 --seed
  2) .\run.ps1 --build-rag
  3) .\run.ps1 --mode graphrag
  4) .\run.ps1 --eval

GraphRAG (Neo4j + tools):
  --seed                        Seed Neo4j with demo data:
                                    - exercise taxonomy
                                    - multi-user profiles (User + WorkoutBrief)
                                    - training plans (TrainingPlan) for matching
                                    - workout sessions (WorkoutSession) for BI/temporal queries
  --seed-pdfs                   Seed Neo4j from unstructured PDFs found in --pdf-dir (profiles/plans/logs)
  --pdf-dir DIR                 Directory with PDFs (default: gymadvisorai/data/raw_pdfs)
  --ingest-pdf PATH             Ingest a single PDF into Neo4j (auto-detect: profile/plan/log)
  --ingest-profiles-pdf PATH    Ingest multi-user profiles PDF (CV-like)
  --ingest-plans-pdf PATH       Ingest training plans PDF (RFP-like)
  --ingest-logs-pdf PATH      Ingest workout logs PDF (BI-like)

Baseline RAG (TF-IDF + optional PDFs):
  --build-rag            Build TF-IDF index from local JSON + PDFs found in:
                         - gymadvisorai/data/**/*.pdf
                         - gymadvisorai/data/raw_pdfs/**/*.pdf
  --mode rag             Answer using baseline RAG (retrieval + LLM)
  --mode graphrag         Answer using graph tools (GraphRAG) (recommended)

Evaluation (TEG-ready):
  --eval                 Run evaluation suite: RAG vs GraphRAG, generate numeric metrics and reports (md/json/csv/pdf)

Example questions (GraphRAG recommended):
  BI / Counting:
    - How many sessions did user u2 do in the last 30 days?
  Temporal:
    - When was user u1's last squat session?
  Aggregation:
    - What is user u1's bench press tonnage in the last 30 days?
  Filtering:
    - Which exercises are without shoulder risk? Give top 5.
  Matching (TalentMatchAI analog):
    - Match the best training plan for user u2. Show top 3 with scores and explain tradeoffs.
  What-if planning:
    - What-if user u2 can train 1 extra day per week? How does the top 3 ranking change?

Notes:
  - Put your PDFs in: gymadvisorai/data/raw_pdfs/
  - For Neo4j Aura on Windows, use run.ps1 to set SSL_CERT_FILE automatically.
"""
WHATIF_RE = re.compile(
    r"\bwhat[- ]?if\b.*\buser\s+(u\d+)\b.*?(?:\bextra\b|\bmore\b|\+)\s*(\d+)\s*(?:day|days)\b",
    re.IGNORECASE,
)
MATCH_RE = re.compile(r"\bmatch\b.*\bplan\b.*\buser\s+(u\d+)\b", re.IGNORECASE)

# wersje jawne (bez pamięci)
WHY_PLAN_EXPLICIT_RE = re.compile(r"^\s*why\s+plan\s+(.+?)\s+for\s+user\s+(u\d+)\s*$", re.IGNORECASE)
SHOW_PLAN_EXPLICIT_RE = re.compile(r"^\s*show\s+plan\s+details\s+(.+?)\s*$", re.IGNORECASE)

# Bulletproof what-if parsing (2-step, robust to word order)
WHATIF_FLAG_RE = re.compile(r"\bwhat[- ]?if\b", re.IGNORECASE)
USER_ID_RE = re.compile(r"\buser\s+(u\d+)\b", re.IGNORECASE)

# Captures:
# - "1 extra day", "1 more day", "1 day"
# - "+1 day", "+ 1 day"
# - "extra 1 day" (fallback handled by second regex)
DAYS_DELTA_RE_1 = re.compile(r"\b\+?\s*(\d+)\s*(?:extra|more)?\s*day\b", re.IGNORECASE)
DAYS_DELTA_RE_2 = re.compile(r"\b(?:extra|more)\s*(\d+)\s*day\b", re.IGNORECASE)


def route_graphrag_query(q: str) -> str | None:
    qq = q.strip()

    # What-if matching
    if WHATIF_FLAG_RE.search(qq):
        um = USER_ID_RE.search(qq)
        dm = DAYS_DELTA_RE_1.search(qq) or DAYS_DELTA_RE_2.search(qq)
        if um and dm:
            user_id = um.group(1)
            delta = int(dm.group(1))
            return what_if_match(user_id=user_id, delta_days=delta, top_k=3)

    # Plan matching
    m = MATCH_RE.search(qq)
    if m:
        return match_training_plans(user_id=m.group(1), top_k=3)

    # Explicit "why plan X for user uY"
    m = WHY_PLAN_EXPLICIT_RE.match(qq)
    if m:
        plan_name = m.group(1).strip()
        user_id = m.group(2)
        # najprościej: ponów matching top_k=5 i wybierz info o planie z wyniku
        return f"Explain why plan '{plan_name}' fits user '{user_id}' (TODO: implement plan-specific explanation)."

    # Explicit "show plan details <plan>"
    m = SHOW_PLAN_EXPLICIT_RE.match(qq)
    if m:
        plan_name = m.group(1).strip()
        return f"Show details for plan '{plan_name}' (TODO: implement plan fetch by name)."

    return None


def main() -> None:
    p = argparse.ArgumentParser(prog="gymadvisorai", description="GymAdvisorAI CLI (GraphRAG vs RAG baseline)")
    p.add_argument("--mode", choices=["graphrag", "rag"], default="graphrag")
    p.add_argument("--seed", action="store_true", help="Seed Neo4j with demo data")
    p.add_argument("--seed-pdfs", action="store_true", help="Seed Neo4j using unstructured PDFs (profiles/plans/logs) in --pdf-dir")
    p.add_argument("--pdf-dir", type=str, default="gymadvisorai/data/raw_pdfs", help="Directory containing PDFs for seeding/ingestion")
    p.add_argument("--build-rag", action="store_true", help="Build baseline TF-IDF index from local JSON + any PDFs in gymadvisorai/data[/raw_pdfs]")
    p.add_argument("--ingest-pdf", type=str, default=None, help="Ingest a workout PDF into Neo4j")
    p.add_argument("--ingest-profiles-pdf", type=str, default=None, help="Ingest a multi-user profiles PDF into Neo4j")
    p.add_argument("--ingest-plans-pdf", type=str, default=None, help="Ingest a training plans (RFP-like) PDF into Neo4j")
    p.add_argument("--ingest-logs-pdf", type=str, default=None, help="Ingest a workout logs PDF into Neo4j")
    p.add_argument("--eval", action="store_true", help="Run a TEG-style RAG vs GraphRAG evaluation (writes reports/)")
    args = p.parse_args()

    # Neo4j seed/ingest/graphrag/eval
    if (
        args.seed
        or args.seed_pdfs
        or args.ingest_pdf
        or args.ingest_profiles_pdf
        or args.ingest_plans_pdf
        or args.ingest_logs_pdf
        or args.mode == "graphrag"
        or args.eval
    ):
        settings.validate_neo4j()

    did_one_shot = False

    if args.seed:
        seed_demo()
        print("Seeded Neo4j with demo data.")
        did_one_shot = True

    if args.seed_pdfs:
        seed_demo_multi(use_pdfs=True, pdf_dir=args.pdf_dir)
        print(f"Seeded Neo4j using PDFs from: {args.pdf_dir}")
        did_one_shot = True

    if args.build_rag:
        n = build_rag_from_local_json()
        print(f"Built baseline RAG store with {n} docs.")
        did_one_shot = True

    if args.ingest_pdf:
        data = ingest_workout_pdf(args.ingest_pdf, user_id="u1")
        sessions_n = len(data.get("sessions", []))
        brief_n = 1 if data.get("brief") else 0
        print(f"Ingested PDF: {args.ingest_pdf}. Sessions: {sessions_n}, Brief: {brief_n}")
        did_one_shot = True

    if args.ingest_profiles_pdf:
        r = ingest_user_profiles_pdf(args.ingest_profiles_pdf)
        print(f"Ingested profiles PDF: {args.ingest_profiles_pdf}. Profiles: {r.get('count', 0)}")
        did_one_shot = True

    if args.ingest_plans_pdf:
        r = ingest_training_plans_pdf(args.ingest_plans_pdf)
        print(f"Ingested plans PDF: {args.ingest_plans_pdf}. Plans: {r.get('count', 0)}")
        did_one_shot = True

    if args.ingest_logs_pdf:
        r = ingest_workout_logs_pdf(args.ingest_logs_pdf)
        print(f"Ingested logs PDF: {args.ingest_logs_pdf}. Users: {len(r.get('users', []))}")
        did_one_shot = True

    if args.eval:
        report = run_eval(seed=True)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        did_one_shot = True

    if did_one_shot and not (args.mode in {"graphrag", "rag"}):
        return

    if did_one_shot:
        return

    print(f"GymAdvisorAI (mode={args.mode}). Type 'help' or 'exit'")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            break
        if q.lower() in {"help", "?"}:
            print(HELP_TEXT)
            continue

        if args.mode == "rag":
            print(answer_with_rag(q))
        else:
            routed = route_graphrag_query(q)
            if routed is not None:
                print(routed)
            else:
                print(answer_graphrag(q))



if __name__ == "__main__":
    main()
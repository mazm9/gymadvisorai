from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Literal

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from gymadvisorai.agent import answer as answer_graphrag
from gymadvisorai.config import settings
from gymadvisorai.data_loader import load_json
from gymadvisorai.rag import answer_with_rag
from gymadvisorai.seed import seed_demo

Mode = Literal["rag", "graphrag"]

_NUM_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _extract_number(text: str) -> float | None:
    if not text:
        return None
    m = _NUM_RE.search(text.replace(",", "."))
    return float(m.group(1)) if m else None


def _extract_date(text: str) -> str | None:
    if not text:
        return None
    m = _DATE_RE.search(text)
    return m.group(1) if m else None


def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _mentioned_exercises(answer: str, known: list[str]) -> list[str]:
    """Return exercise names that appear in the answer (case-insensitive, whole-word-ish)."""
    a = (answer or "").lower()
    found = []
    for name in known:
        n = name.lower()
        if re.search(r"\b" + re.escape(n) + r"\b", a):
            found.append(name)
    return found


def _mentioned_plans(answer: str, known: list[str]) -> list[str]:
    a = (answer or "").lower()
    found = []
    for name in known:
        n = (name or "").lower()
        if n and n in a:
            found.append(name)
    return found


# Truth from demo data


@dataclass(frozen=True)
class DemoTruth:
    today: date
    sessions: list[dict]
    exercises: list[dict]
    exercise_names: list[str]
    risk_by_exercise: dict[str, set[str]]
    users: list[dict]
    plans: list[dict]
    plan_names: list[str]


def load_demo_truth() -> DemoTruth:
    workouts = load_json("workouts.json")
    knowledge = load_json("exercise_knowledge.json")
    users = load_json("users.json")
    plans = load_json("training_plans.json")
    sessions = workouts.get("sessions", []) or []
    exercises = knowledge.get("exercises", []) or []
    max_d = max((date.fromisoformat(s["date"]) for s in sessions), default=date.today())
    names = [e["name"] for e in exercises if e.get("name")]
    risk = {e["name"]: set((e.get("risk") or [])) for e in exercises if e.get("name")}
    plan_list = plans.get("plans", []) or []
    plan_names = [p.get("name") for p in plan_list if p.get("name")]
    return DemoTruth(
        today=max_d,
        sessions=sessions,
        exercises=exercises,
        exercise_names=names,
        risk_by_exercise=risk,
        users=users.get("users", []) or [],
        plans=plan_list,
        plan_names=plan_names,
    )


def count_sessions_last_days(truth: DemoTruth, days: int) -> int:
    since = truth.today - timedelta(days=days)
    return sum(1 for s in truth.sessions if date.fromisoformat(s["date"]) >= since)


def tonnage_last_days(truth: DemoTruth, exercise: str, days: int) -> float:
    since = truth.today - timedelta(days=days)
    total = 0.0
    for s in truth.sessions:
        sd = date.fromisoformat(s["date"])
        if sd < since:
            continue
        for it in s.get("items", []):
            if (it.get("exercise") or "").lower() == exercise.lower():
                sets = float(it.get("sets") or 0)
                reps = float(it.get("reps") or 0)
                w = float(it.get("weight") or 0)
                total += sets * reps * w
    return total


def last_date_for_exercise(truth: DemoTruth, exercise: str) -> str | None:
    last = None
    for s in truth.sessions:
        for it in s.get("items", []):
            if (it.get("exercise") or "").lower() == exercise.lower():
                last = s["date"]
    return last


def exercises_without_risk(truth: DemoTruth, risk: str) -> list[str]:
    r = (risk or "").strip().lower()
    out = []
    for ex in truth.exercise_names:
        risks = {x.lower() for x in truth.risk_by_exercise.get(ex, set())}
        if r not in risks:
            out.append(ex)
    return sorted(out)


def expected_best_plan(truth: DemoTruth, user_id: str) -> str | None:
    """Compute the expected best plan using the same transparent scoring as the GraphRAG tool."""
    u = next((x for x in truth.users if (x.get("user_id") or "").lower() == user_id.lower()), None)
    if not u:
        return None

    u_focus = set((u.get("focus") or []))
    u_eq = set((u.get("equipment") or []))
    u_risks = {str(x) for x in (u.get("constraints") or [])}
    u_days = int(u.get("days_per_week") or 0)

    # Map exercise and risk from knowledge
    risk_by_ex = truth.risk_by_exercise

    def score(plan: dict) -> float:
        p_focus = set((plan.get("focus") or []))
        p_eq = set((plan.get("equipment") or []))
        ex_list = plan.get("exercises") or []

        focus_overlap = len(p_focus.intersection(u_focus))
        missing_eq = len([x for x in p_eq if x not in u_eq])
        # risk conflicts
        risk_conflicts = 0
        for ex in ex_list:
            risks = set(risk_by_ex.get(ex, set()))
            if any(r in u_risks for r in risks):
                risk_conflicts += 1
        days_diff = abs(int(plan.get("days_per_week") or 0) - u_days)

        return 5 * focus_overlap - 10 * missing_eq - 8 * risk_conflicts - 1 * days_diff

    best = None
    best_s = float("-inf")
    for p in truth.plans:
        s = score(p)
        if s > best_s:
            best_s = s
            best = p.get("name")
    return best



# Metrics


def metric_numeric_accuracy(answer: str, expected: float, tol: float = 0.01) -> dict:
    got = _extract_number(answer)
    ok = got is not None and abs(got - expected) <= tol
    return {
        "ok": bool(ok),
        "expected": expected,
        "got": got,
        "abs_err": None if got is None else abs(got - expected),
    }


def metric_date_accuracy(answer: str, expected_iso: str) -> dict:
    got = _extract_date(answer)
    ok = got == expected_iso
    return {"ok": bool(ok), "expected": expected_iso, "got": got}


def metric_list_precision_recall(answer: str, expected: list[str], known: list[str], k: int = 5) -> dict:
    mentioned = _mentioned_exercises(answer, known)
    topk = mentioned[:k]
    exp = set(expected)
    tp = sum(1 for x in topk if x in exp)
    precision = tp / k if k else 0.0
    recall = tp / len(exp) if exp else 0.0
    return {
        "ok": tp > 0,  # minimal success signal
        "k": k,
        "mentioned": mentioned,
        "topk": topk,
        "tp": tp,
        "precision_at_k": round(precision, 3),
        "recall_at_k": round(recall, 3),
        "expected_n": len(exp),
    }


def metric_reasoning_rubric(answer: str, must: list[str], nice: list[str]) -> dict:
    a = (answer or "").lower()
    must_hits = [m for m in must if m.lower() in a]
    nice_hits = [n for n in nice if n.lower() in a]
    ok = len(must_hits) >= max(1, len(must) // 2)  # soft gate
    score = (2 * len(must_hits) + len(nice_hits)) / max(1, (2 * len(must) + len(nice)))
    return {
        "ok": bool(ok),
        "rubric_score": round(score, 3),
        "must_hits": must_hits,
        "nice_hits": nice_hits,
    }


def metric_plan_top1(answer: str, expected_plan: str, known_plans: list[str]) -> dict:
    mentioned = _mentioned_plans(answer, known_plans)
    top1 = mentioned[0] if mentioned else None
    ok = top1 == expected_plan
    return {
        "ok": bool(ok),
        "expected": expected_plan,
        "top1": top1,
        "mentioned": mentioned,
    }


@dataclass(frozen=True)
class TestCase:
    name: str
    question: str
    metric_fn: Callable[[str], dict]
    metric_type: str


def build_test_suite(truth: DemoTruth) -> list[TestCase]:
    n30 = count_sessions_last_days(truth, 30)
    bench30 = tonnage_last_days(truth, "Bench Press", 30)
    last_squat = last_date_for_exercise(truth, "Squat") or "1900-01-01"
    safe_no_shoulder = exercises_without_risk(truth, "Shoulder")
    whatif = 3 * 10 * 50  # sets * reps * kg
    best_u2 = expected_best_plan(truth, "u2") or ""
    best_u3 = expected_best_plan(truth, "u3") or ""

    return [
        TestCase(
            name="count_sessions_last_30",
            question="How many sessions did I do in the last 30 days?",
            metric_fn=lambda ans, exp=n30: metric_numeric_accuracy(ans, exp, tol=0.0),
            metric_type="numeric",
        ),
        TestCase(
            name="bench_tonnage_last_30",
            question="What was my Bench Press tonnage in the last 30 days?",
            metric_fn=lambda ans, exp=bench30: metric_numeric_accuracy(ans, exp, tol=0.01),
            metric_type="numeric",
        ),
        TestCase(
            name="last_squat_date",
            question="When was my last Squat?",
            metric_fn=lambda ans, exp=last_squat: metric_date_accuracy(ans, exp),
            metric_type="date",
        ),
        TestCase(
            name="safe_exercises_no_shoulder",
            question="Which exercises are without shoulder risk? List 5.",
            metric_fn=lambda ans, exp=safe_no_shoulder, known=truth.exercise_names: metric_list_precision_recall(
                ans, exp, known, k=5
            ),
            metric_type="list_p@k",
        ),
        TestCase(
            name="plateau_reasoning_bench",
            question="Why am I plateauing on bench press? Give 3 likely causes and 3 actions.",
            metric_fn=lambda ans: metric_reasoning_rubric(
                ans,
                must=["plateau", "volume", "recovery", "progressive", "sleep", "nutrition"],
                nice=["deload", "technique", "frequency", "variation", "microload", "rest days"],
            ),
            metric_type="reasoning",
        ),
        TestCase(
            name="what_if_add_sets",
            question="What if I add 3 sets 10 reps at 50kg to my plan? How much extra tonnage is that?",
            metric_fn=lambda ans, exp=whatif: metric_numeric_accuracy(ans, exp, tol=0.0),
            metric_type="numeric",
        ),
        TestCase(
            name="matching_u2_best_plan",
            question="Match the best training plan for user u2. Return the top plan first.",
            metric_fn=lambda ans, exp=best_u2, known=truth.plan_names: metric_plan_top1(ans, exp, known),
            metric_type="matching_top1",
        ),
        TestCase(
            name="matching_u3_best_plan",
            question="For user u3, which plan is the best match? Return the top plan first.",
            metric_fn=lambda ans, exp=best_u3, known=truth.plan_names: metric_plan_top1(ans, exp, known),
            metric_type="matching_top1",
        ),
    ]


@dataclass
class PerCaseResult:
    case: str
    metric_type: str
    ok: bool
    latency_ms: float
    answer_preview: str
    metrics: dict


def _answer(mode: Mode, q: str) -> str:
    return answer_graphrag(q) if mode == "graphrag" else answer_with_rag(q)


def _run_mode(mode: Mode, cases: Iterable[TestCase]) -> tuple[dict, list[PerCaseResult]]:
    per: list[PerCaseResult] = []
    lat: list[float] = []
    ok_n = 0

    # aggregated metrics by type
    buckets: dict[str, list[dict]] = {}

    for tc in cases:
        t0 = time.perf_counter()
        try:
            ans = _answer(mode, tc.question)
        except Exception as e:
            ans = f"<ERROR: {type(e).__name__}: {e}>"
        dt = (time.perf_counter() - t0) * 1000.0

        m = tc.metric_fn(ans)
        ok = bool(m.get("ok"))
        ok_n += int(ok)
        lat.append(dt)

        buckets.setdefault(tc.metric_type, []).append(m)

        per.append(
            PerCaseResult(
                case=tc.name,
                metric_type=tc.metric_type,
                ok=ok,
                latency_ms=round(dt, 1),
                answer_preview=_normalize_space(ans)[:240],
                metrics=m,
            )
        )

    n = len(per)
    summary = {
        "n": n,
        "correct": ok_n,
        "accuracy": round(ok_n / n, 3) if n else 0.0,
        "avg_latency_ms": round(sum(lat) / n, 1) if n else 0.0,
    }

    # metric-specific rollups
    rollups = {}
    for mtype, ms in buckets.items():
        if mtype == "numeric":
            errs = [x.get("abs_err") for x in ms if x.get("abs_err") is not None]
            rollups[mtype] = {
                "mean_abs_err": round(sum(errs) / len(errs), 3) if errs else None,
                "median_abs_err": round(sorted(errs)[len(errs)//2], 3) if errs else None,
            }
        elif mtype == "date":
            rollups[mtype] = {"exact_match_rate": round(sum(1 for x in ms if x.get("ok")) / len(ms), 3)}
        elif mtype == "list_p@k":
            ps = [x.get("precision_at_k", 0.0) for x in ms]
            rs = [x.get("recall_at_k", 0.0) for x in ms]
            rollups[mtype] = {
                "mean_precision_at_k": round(sum(ps) / len(ps), 3) if ps else 0.0,
                "mean_recall_at_k": round(sum(rs) / len(rs), 3) if rs else 0.0,
            }
        elif mtype == "reasoning":
            scores = [x.get("rubric_score", 0.0) for x in ms]
            rollups[mtype] = {
                "mean_rubric_score": round(sum(scores) / len(scores), 3) if scores else 0.0
            }
        elif mtype == "matching_top1":
            rollups[mtype] = {
                "exact_match_rate": round(sum(1 for x in ms if x.get("ok")) / len(ms), 3) if ms else 0.0
            }

    return {**summary, "rollups": rollups}, per


def _write_pdf_artifacts(report: dict, out_dir: Path) -> dict[str, str]:
    """Generate submission-friendly PDFs (no external tooling needed)."""
    styles = getSampleStyleSheet()
    paths: dict[str, str] = {}

    # eval_report.pdf
    pdf_eval = out_dir / "eval_report.pdf"
    doc = SimpleDocTemplate(str(pdf_eval), pagesize=A4, title="GymAdvisorAI - RAG vs GraphRAG Evaluation")
    story = []
    story.append(Paragraph("GymAdvisorAI - RAG vs GraphRAG Evaluation", styles["Title"]))
    meta = report.get("meta", {}) or {}
    story.append(Paragraph(f"Eval date (demo): {meta.get('eval_today','-')} | LLM enabled: {meta.get('llm_enabled')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    g = report["summary"]["graphrag"]
    r = report["summary"]["rag"]

    def _roll(s: dict, m: str, k: str):
        v = ((s.get("rollups") or {}).get(m) or {}).get(k)
        return "-" if v is None else str(v)

    table_data = [
        ["Mode", "Accuracy", "Avg latency (ms)", "Numeric MAE", "P@5", "R@5", "Reasoning score", "Match top-1"],
        [
            "GraphRAG",
            g.get("accuracy"),
            g.get("avg_latency_ms"),
            _roll(g, "numeric", "mean_abs_err"),
            _roll(g, "list_p@k", "mean_precision_at_k"),
            _roll(g, "list_p@k", "mean_recall_at_k"),
            _roll(g, "reasoning", "mean_rubric_score"),
            _roll(g, "matching_top1", "exact_match_rate"),
        ],
        [
            "RAG",
            r.get("accuracy"),
            r.get("avg_latency_ms"),
            _roll(r, "numeric", "mean_abs_err"),
            _roll(r, "list_p@k", "mean_precision_at_k"),
            _roll(r, "list_p@k", "mean_recall_at_k"),
            _roll(r, "reasoning", "mean_rubric_score"),
            _roll(r, "matching_top1", "exact_match_rate"),
        ],
    ]
    t = Table(table_data, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Notes", styles["Heading2"]))
    story.append(
        Paragraph(
            "RAG baseline uses retrieval over textual docs (TF-IDF / optional embeddings). GraphRAG answers by querying the Neo4j knowledge graph and applying explicit constraints.",
            styles["Normal"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Per-case (short)", styles["Heading1"]))
    story.append(Paragraph("Preview is truncated for readability.", styles["Normal"]))
    story.append(Spacer(1, 8))
    rows = [["Mode", "Case", "OK", "Latency (ms)", "Preview"]]
    for mode in ["graphrag", "rag"]:
        for row in report["details"][mode]:
            rows.append(
                [
                    mode,
                    row["case"],
                    "1" if row["ok"] else "0",
                    str(row["latency_ms"]),
                    (row["answer_preview"] or "")[:120],
                ]
            )
    t2 = Table(rows, repeatRows=1, colWidths=[70, 170, 30, 70, 200])
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t2)
    doc.build(story)
    paths["pdf_eval"] = str(pdf_eval)

    # matching_overview.pdf
    pdf_match = out_dir / "matching_overview.pdf"
    doc2 = SimpleDocTemplate(str(pdf_match), pagesize=A4, title="GymAdvisorAI - Matching Overview")
    s2 = []
    s2.append(Paragraph("GymAdvisorAI - Matching Overview (TalentMatchAI analogy)", styles["Title"]))
    s2.append(Spacer(1, 10))
    s2.append(Paragraph("Analogy", styles["Heading2"]))
    s2.append(
        Paragraph(
            "TalentMatchAI matches candidates to projects/RFPs under constraints. GymAdvisorAI matches users to training plans under constraints (injury risk, equipment, focus, availability).",
            styles["Normal"],
        )
    )
    s2.append(Spacer(1, 10))
    s2.append(Paragraph("Graph entities", styles["Heading2"]))
    s2.append(
        Paragraph(
            "User -> WorkoutBrief (goals, constraints, equipment, days/week). TrainingPlan -> focus, required equipment, exercises. Exercises link to RiskTags and MuscleGroups.",
            styles["Normal"],
        )
    )
    s2.append(Spacer(1, 10))
    s2.append(Paragraph("Transparent matching score", styles["Heading2"]))
    s2.append(
        Paragraph(
            "score = 5*focus_overlap - 10*missing_equipment - 8*risk_conflicts - 1*days_diff",
            styles["Normal"],
        )
    )
    s2.append(Spacer(1, 10))
    s2.append(Paragraph("How to demo", styles["Heading2"]))
    s2.append(
        Paragraph(
            "Ask: 'Match the best training plan for user u2.' and show the ranked output with explanations of penalties (risk/equipment/days).",
            styles["Normal"],
        )
    )
    doc2.build(s2)
    paths["pdf_matching"] = str(pdf_match)

    return paths


def _write_artifacts(report: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out_dir / "eval_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV
    csv_path = out_dir / "eval_cases.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mode", "case", "metric_type", "ok", "latency_ms", "answer_preview", "metrics_json"])
        for mode in ["graphrag", "rag"]:
            for row in report["details"][mode]:
                w.writerow(
                    [
                        mode,
                        row["case"],
                        row["metric_type"],
                        row["ok"],
                        row["latency_ms"],
                        row["answer_preview"],
                        json.dumps(row["metrics"], ensure_ascii=False),
                    ]
                )

    # Markdown
    md_path = out_dir / "eval_report.md"
    s = report["summary"]
    g = s["graphrag"]
    r = s["rag"]
    lines = []
    lines.append("# GymAdvisorAI — RAG vs GraphRAG evaluation\n")
    lines.append("## Summary\n")
    lines.append("| Mode | Accuracy | Avg latency (ms) | Numeric MAE | List P@5 | List R@5 | Reasoning score |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")

    def _get_roll(mode, key, sub, default="—"):
        return mode.get("rollups", {}).get(key, {}).get(sub, default)

    lines.append(
        f"| GraphRAG | {g['accuracy']:.3f} | {g['avg_latency_ms']:.1f} | "
        f"{_get_roll(g,'numeric','mean_abs_err')} | "
        f"{_get_roll(g,'list_p@k','mean_precision_at_k')} | "
        f"{_get_roll(g,'list_p@k','mean_recall_at_k')} | "
        f"{_get_roll(g,'reasoning','mean_rubric_score')} |\n"
    )
    lines.append(
        f"| RAG | {r['accuracy']:.3f} | {r['avg_latency_ms']:.1f} | "
        f"{_get_roll(r,'numeric','mean_abs_err')} | "
        f"{_get_roll(r,'list_p@k','mean_precision_at_k')} | "
        f"{_get_roll(r,'list_p@k','mean_recall_at_k')} | "
        f"{_get_roll(r,'reasoning','mean_rubric_score')} |\n"
    )

    lines.append("\n## Per-case results (short)\n")
    lines.append("| Mode | Case | OK | Latency (ms) | Preview |\n")
    lines.append("|---|---|---:|---:|---|\n")
    for mode in ["graphrag", "rag"]:
        for row in report["details"][mode]:
            preview = row["answer_preview"].replace("|", "\\|")
            lines.append(f"| {mode} | {row['case']} | {int(row['ok'])} | {row['latency_ms']} | {preview} |\n")

    md_path.write_text("".join(lines), encoding="utf-8")

    pdf_paths = _write_pdf_artifacts(report, out_dir)

    paths = {"json": str(json_path), "csv": str(csv_path), "md": str(md_path)}
    paths.update(pdf_paths)
    return paths


def run_eval(seed: bool = True, out_dir: str | None = "reports") -> dict:
    if seed:
        settings.validate_neo4j()
        seed_demo()

    truth = load_demo_truth()
    cases = build_test_suite(truth)

    g_summary, g_per = _run_mode("graphrag", cases)
    r_summary, r_per = _run_mode("rag", cases)

    report = {
        "meta": {
            "llm_enabled": bool(settings.llm_enabled),
            "eval_today": truth.today.isoformat(),
        },
        "summary": {
            "graphrag": g_summary,
            "rag": r_summary,
        },
        "details": {
            "graphrag": [vars(x) for x in g_per],
            "rag": [vars(x) for x in r_per],
        },
    }

    if out_dir:
        paths = _write_artifacts(report, Path(out_dir))
        report["meta"]["artifacts"] = paths

    return report

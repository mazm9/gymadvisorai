from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gymadvisorai.llm import llm_chat
from gymadvisorai.graph import (
    Neo4jClient,
    ingest_sessions,
    upsert_training_plan,
    upsert_workout_brief,
)

_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_KEYVAL_RE = re.compile(r"^([A-Za-z ][A-Za-z ]+):\s*(.+)$")
_USER_HEADER_RE = re.compile(r"User Profile:\s*(.+?)\s*\((u\d+)\)")
_PLAN_HEADER_RE = re.compile(r"Plan:\s*(.+)$")


def extract_text_from_pdf(pdf_path: str) -> str:
    p = Path(pdf_path)
    if not p.exists():
        raise FileNotFoundError(pdf_path)

    # Try pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(p))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise RuntimeError(
                "No PDF reader available."
            ) from e


# Workout brief extraction
def _heuristic_parse_brief(text: str) -> dict[str, Any] | None:
    """ Fallback parser for simple workout briefs.
    Supports lines like:
      Goal: Strength
      Days Per Week: 3
      Minutes Per Session: 45
      Focus Muscles: Chest, Back
    And bullet lists under headings:
      Constraints / Injuries:
      - Shoulder (avoid overhead pressing)
      Available Equipment:
      - Barbell, Bench, Dumbbells
    """
    data: dict[str, Any] = {"focus": [], "constraints": [], "equipment": []}

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _KEYVAL_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()

        if key in {"user id", "user"}:
            data["user_id"] = val
        elif key == "goal":
            data["goal"] = val
        elif key in {"days per week", "days/week"}:
            nums = re.findall(r"\d+", val)
            if nums:
                data["days_per_week"] = int(nums[0])
        elif key in {"minutes per session", "minutes/session"}:
            nums = re.findall(r"\d+", val)
            if nums:
                data["minutes_per_session"] = int(nums[0])
        elif key in {"focus muscles", "focus"}:
            data["focus"] = [v.strip() for v in re.split(r",|;", val) if v.strip()]
        elif key in {"experience level", "level"}:
            data["experience_level"] = val

    current_section: str | None = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "constraints" in low or "injuries" in low:
            current_section = "constraints"
            continue
        if "available equipment" in low or low.startswith("equipment"):
            current_section = "equipment"
            continue
        if line.startswith("- "):
            item = line[2:].strip()
            if current_section == "constraints":
                risk = item.split("(")[0].strip()
                if risk:
                    data["constraints"].append(risk)
            elif current_section == "equipment":
                parts = [p.strip() for p in re.split(r",|;", item) if p.strip()]
                data["equipment"].extend(parts)

    # validation
    if data.get("goal") and data.get("days_per_week") and data.get("minutes_per_session"):
        data.setdefault("user_id", "u1")
        return data
    return None


def extract_brief(text: str) -> dict[str, Any] | None:
    """Extract workout brief using LLM if available; fall back to heuristic parsing."""
    prompt = f"""Extract a workout brief (goal, constraints, equipment, schedule) into JSON.

Return ONLY valid JSON:
{{
  "user_id": "u1",
  "goal": "Strength",
  "days_per_week": 3,
  "minutes_per_session": 45,
  "experience_level": "Intermediate",
  "focus": ["Chest","Back"],
  "constraints": ["Shoulder"],
  "equipment": ["Barbell","Bench","Dumbbells"]
}}

TEXT:
{text}
"""
    out = llm_chat(prompt, max_tokens=400)
    if out:
        try:
            obj = json.loads(out)
            if isinstance(obj, dict) and obj.get("goal") and obj.get("days_per_week") and obj.get("minutes_per_session"):
                obj.setdefault("user_id", "u1")
                obj.setdefault("focus", [])
                obj.setdefault("constraints", [])
                obj.setdefault("equipment", [])
                return obj
        except Exception:
            pass
    return _heuristic_parse_brief(text)


# Workout session extraction

def _heuristic_parse_sessions(text: str) -> dict[str, Any]:
    """Fallback parser for simple logs.

    Expected pattern examples:
      2026-01-20
      Bench Press 3x10 80
      Deadlift 3x5 140
    """
    sessions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        m = _DATE_RE.search(line)
        if m:
            if current:
                sessions.append(current)
            current = {"date": m.group(1), "items": []}
            continue

        if current is None:
            continue

        m2 = re.match(r"(.+?)\s+(\d+)\s*[xX]\s*(\d+)\s+([0-9]+(?:\.[0-9]+)?)", line)
        if m2:
            ex = m2.group(1).strip()
            sets = int(m2.group(2))
            reps = int(m2.group(3))
            weight = float(m2.group(4))
            current["items"].append({"exercise": ex, "sets": sets, "reps": reps, "weight": weight})

    if current:
        sessions.append(current)

    return {"user_id": "u1", "sessions": sessions}


def extract_sessions(text: str) -> dict[str, Any]:
    """Extract workout sessions from unstructured text using LLM if available."""
    prompt = f"""Extract workout log data from the text into JSON.

Return ONLY valid JSON in this schema:
{{
  "user_id": "u1",
  "sessions": [
    {{
      "date": "YYYY-MM-DD",
      "items": [
        {{"exercise": "...", "sets": 3, "reps": 10, "weight": 80}}
      ]
    }}
  ]
}}

Rules:
- If a weight unit appears (kg/lbs), ignore the unit and keep the number.
- If date is missing, skip that session.
- If sets/reps/weight are unclear, omit the item.

TEXT:
{text}
"""

    out = llm_chat(prompt, max_tokens=600)
    if out:
        try:
            return json.loads(out)
        except Exception:
            pass

    return _heuristic_parse_sessions(text)


def ingest_workout_pdf(pdf_path: str, user_id: str = "u1") -> dict[str, Any]:
    """Ingest a PDF that may contain a workout brief and/or workout sessions."""
    text = extract_text_from_pdf(pdf_path)

    brief = extract_brief(text)
    sessions_data = extract_sessions(text)

    uid = user_id or (brief.get("user_id") if brief else None) or sessions_data.get("user_id") or "u1"

    c = Neo4jClient()
    try:
        if brief:
            upsert_workout_brief(
                c,
                user_id=uid,
                goal=str(brief.get("goal", "")),
                days_per_week=int(brief.get("days_per_week", 3)),
                minutes_per_session=int(brief.get("minutes_per_session", 45)),
                focus=brief.get("focus", []) or [],
                constraints=brief.get("constraints", []) or [],
                equipment=brief.get("equipment", []) or [],
                experience_level=brief.get("experience_level"),
            )

        ingest_sessions(c, sessions_data.get("sessions", []), user_id=uid)
    finally:
        c.close()

    return {"user_id": uid, "brief": brief, "sessions": sessions_data.get("sessions", [])}

# multi-document ingestion


def _extract_user_profiles_heuristic(text: str) -> list[dict[str, Any]]:
    """Extract multiple user profiles from a single PDF.

    Supports the synthetic format generated for this project:
      "User Profile: User 7 (u7)"
      "Goal: ... Experience: ... Preferred training frequency: X days/week, Y minutes/session."
      "Focus areas: ... Constraints/limitations: ... Available equipment: ..."
    """
    profiles: list[dict[str, Any]] = []
    # split by header occurrences
    matches = list(_USER_HEADER_RE.finditer(text or ""))
    if not matches:
        return profiles

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = (text or "")[start:end]

        display_name = m.group(1).strip()
        user_id = m.group(2).strip()

        # key attributes from sentences
        goal = _first_group(chunk, r"Goal:\s*([^\.]+)\.")
        exp = _first_group(chunk, r"Experience:\s*([^\.]+)\.")
        dpw = _first_int(chunk, r"frequency:\s*(\d+)\s*days/week")
        mps = _first_int(chunk, r"(\d+)\s*minutes/session")
        focus_raw = _first_group(chunk, r"Focus areas:\s*([^\.]+)\.")
        constraints_raw = _first_group(chunk, r"Constraints/limitations:\s*([^\.]+)\.")
        equipment_raw = _first_group(chunk, r"Available equipment:\s*([^\.]+)\.")

        focus = _split_list(focus_raw)
        constraints = []
        if constraints_raw and constraints_raw.lower() not in {"none reported", "none"}:
            constraints = _split_list(constraints_raw)
        equipment = _split_list(equipment_raw)

        profiles.append(
            {
                "user_id": user_id,
                "display_name": display_name,
                "goal": goal or "General fitness",
                "days_per_week": dpw or 3,
                "minutes_per_session": mps or 45,
                "experience_level": exp or "Intermediate",
                "focus": focus,
                "constraints": constraints,
                "equipment": equipment,
            }
        )

    return profiles


def _extract_training_plans_heuristic(text: str) -> list[dict[str, Any]]:
    """Extract multiple plans from a synthetic RFP-like PDF."""
    plans: list[dict[str, Any]] = []
    matches = list(_PLAN_HEADER_RE.finditer(text or ""))
    if not matches:
        return plans

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = (text or "")[start:end]

        name = m.group(1).strip()
        dpw = _first_int(chunk, r"Schedule:\s*(\d+)\s*days/week")
        mps = _first_int(chunk, r"about\s*(\d+)\s*minutes/session")
        focus_raw = _first_group(chunk, r"Primary focus:\s*([^\.]+)\.")
        eq_raw = _first_group(chunk, r"Required equipment:\s*([^\.]+)\.")
        ex_raw = _first_group(chunk, r"Core exercises \(selection\):\s*([^\.]+)\.")

        focus = _split_list(focus_raw)
        equipment = []
        if eq_raw and eq_raw.lower() not in {"none", "none."}:
            equipment = _split_list(eq_raw)
        exs = _split_list(ex_raw)

        plans.append(
            {
                "name": name,
                "days_per_week": dpw or 3,
                "minutes_per_session": mps or 45,
                "focus": focus,
                "equipment": equipment,
                "exercises": exs,
            }
        )
    return plans


def ingest_user_profiles_pdf(pdf_path: str) -> dict[str, Any]:
    """Ingest a PDF containing multiple user profiles into Neo4j."""
    text = extract_text_from_pdf(pdf_path)
    profiles = _extract_user_profiles_heuristic(text)
    c = Neo4jClient()
    try:
        for u in profiles:
            c.run(
                "MERGE (usr:User {user_id:$u}) SET usr.display_name=$n",
                u=u["user_id"],
                n=u.get("display_name") or u["user_id"],
            )
            upsert_workout_brief(
                c,
                user_id=u["user_id"],
                goal=u.get("goal") or "General fitness",
                days_per_week=int(u.get("days_per_week") or 3),
                minutes_per_session=int(u.get("minutes_per_session") or 45),
                focus=u.get("focus") or [],
                constraints=u.get("constraints") or [],
                equipment=u.get("equipment") or [],
                experience_level=u.get("experience_level") or "Intermediate",
            )
    finally:
        c.close()
    return {"profiles": profiles, "count": len(profiles)}


def ingest_training_plans_pdf(pdf_path: str) -> dict[str, Any]:
    """Ingest a PDF containing multiple training plans into Neo4j."""
    text = extract_text_from_pdf(pdf_path)
    plans = _extract_training_plans_heuristic(text)
    c = Neo4jClient()
    try:
        for p in plans:
            upsert_training_plan(
                c,
                name=p["name"],
                days_per_week=int(p.get("days_per_week") or 3),
                minutes_per_session=int(p.get("minutes_per_session") or 45),
                focus=p.get("focus") or [],
                equipment=p.get("equipment") or [],
                exercises=p.get("exercises") or [],
            )
    finally:
        c.close()
    return {"plans": plans, "count": len(plans)}


def ingest_workout_logs_pdf(pdf_path: str, user_id: str | None = None) -> dict[str, Any]:
    """Ingest a workout logs PDF.

    The synthetic logs PDF contains per-user pages, so this method will ingest
    sessions for *all* users it can detect.
    """
    text = extract_text_from_pdf(pdf_path)

    blocks = re.split(r"User\s+(u\d+)\s+-\s+Session Summary", text)
    parsed: dict[str, list[dict[str, Any]]] = {}
    if len(blocks) > 1:
        it = iter(blocks[1:])
        for uid, chunk in zip(it, it):
            # parse
            sessions: list[dict[str, Any]] = []
            for line in chunk.splitlines():
                if not line.strip():
                    continue
                m = re.search(r"(20\d{2}-\d{2}-\d{2})", line)
                if not m:
                    continue
                dt = m.group(1)
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                items_txt = parts[1]
                items: list[dict[str, Any]] = []
                for token in items_txt.split(";"):
                    t = token.strip()
                    if not t:
                        continue
                    # cardio:
                    m_cardio = re.match(r"(.+?)\s+(\d+)\s*min", t)
                    if m_cardio:
                        items.append({"exercise": m_cardio.group(1).strip(), "minutes": int(m_cardio.group(2))})
                        continue
                    m_lift = re.match(r"(.+?)\s+(\d+)x(\d+)@([0-9]+)kg", t)
                    if m_lift:
                        items.append(
                            {
                                "exercise": m_lift.group(1).strip(),
                                "sets": int(m_lift.group(2)),
                                "reps": int(m_lift.group(3)),
                                "weight_kg": int(m_lift.group(4)),
                            }
                        )
                if items:
                    sessions.append({"date": dt, "items": items})
            parsed[uid] = sessions

    c = Neo4jClient()
    try:
        if user_id:
            ingest_sessions(c, parsed.get(user_id, []), user_id=user_id)
        else:
            for uid, sess in parsed.items():
                ingest_sessions(c, sess, user_id=uid)
    finally:
        c.close()
    return {"users": list(parsed.keys()), "session_counts": {k: len(v) for k, v in parsed.items()}}


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in re.split(r",|;|\|", raw) if p.strip()]


def _first_group(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _first_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

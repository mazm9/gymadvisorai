from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .json_io import (
    load_profile, load_catalog,
    default_profile_path, default_catalog_path,
    UserProfile,
)

def _has_equipment(ex_eq: List[str], available: List[str]) -> bool:
    if not ex_eq:
        return True
    avail = {a.lower().strip() for a in available}
    return all(e.lower().strip() in avail for e in ex_eq)

def _contra_ok(contras: List[str], injuries: List[str], avoid: List[str]) -> bool:
    bad = {x.lower().strip() for x in injuries + avoid}
    return not any(c.lower().strip() in bad for c in contras)

def _score_exercise(ex: Dict[str, Any], profile: UserProfile) -> Tuple[float, Dict[str, float], List[str]]:
    score = 0.0
    breakdown: Dict[str, float] = {}
    reasons: List[str] = []

    goal = profile.goal.lower()
    tags = {t.lower() for t in ex.get("tags", [])}

    if goal == "hypertrophy" and "hypertrophy" in tags:
        breakdown["goal"] = 2.0
        reasons.append("tag: hypertrophy")
    elif goal == "strength" and "strength" in tags:
        breakdown["goal"] = 2.0
        reasons.append("tag: strength")
    else:
        breakdown["goal"] = 0.5

    injuries = {x.lower() for x in profile.injuries_limitations}
    if "shoulder_pressing_pain" in injuries and ("shoulder_friendly" in tags or "neutral_grip" in tags):
        breakdown["injury"] = 1.5
        reasons.append("shoulder-friendly")
    else:
        breakdown["injury"] = 0.0

    prefs = {p.lower() for p in profile.preferences}
    eq = {e.lower() for e in ex.get("equipment", [])}
    if "dumbbells" in prefs and "dumbbell" in eq:
        breakdown["prefs"] = 0.8
        reasons.append("pref: dumbbells")
    else:
        breakdown["prefs"] = 0.0

    lvl = profile.level.lower()
    diff = (ex.get("difficulty","intermediate") or "intermediate").lower()
    if lvl == diff:
        breakdown["level"] = 0.6
    elif lvl == "beginner" and diff in ("intermediate","advanced"):
        breakdown["level"] = -0.4
        reasons.append("harder than level")
    else:
        breakdown["level"] = 0.2

    score = sum(breakdown.values())
    return score, breakdown, reasons


def _normalize_limitations(vals: List[str]) -> List[str]:
    """Map UI-friendly limitation labels to internal ones."""
    out = []
    for v in vals or []:
        k = (v or "").strip().lower()
        if not k:
            continue
        if k in {"shoulder_pain", "shoulder_pressing_pain", "bark_bol", "bark"}:
            out.append("shoulder_pressing_pain")
        elif k in {"knee_pain", "knee_pain_deep_flexion", "kolano_bol", "kolano"}:
            out.append("knee_pain_deep_flexion")
        else:
            out.append(k)
    # stable order
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


def _override_profile(profile: UserProfile, req: Dict[str, Any]) -> UserProfile:
    """Return a copy of profile with overrides from tool input.

    Supported keys (loose): goal, equipment/equipment_available, limitations/injuries.
    """
    p = profile.model_copy(deep=True)

    goal = (req.get("goal") or req.get("cel") or "").strip()
    if goal:
        p.goal = goal

    eq = req.get("equipment") or req.get("sprzet") or req.get("equipment_available")
    if isinstance(eq, str):
        eq = [e.strip() for e in eq.split(",") if e.strip()]
    if isinstance(eq, list) and eq:
        p.equipment_available = [str(e).strip().lower() for e in eq if str(e).strip()]

    lim = req.get("limitations") or req.get("ograniczenia") or req.get("injuries") or req.get("injuries_limitations")
    if isinstance(lim, str):
        lim = [x.strip() for x in lim.split(",") if x.strip()]
    if isinstance(lim, list) and lim:
        p.injuries_limitations = _normalize_limitations([str(x) for x in lim])

    return p

def match_exercises(user_request: Any = "", *, profile_path: str | None = None, catalog_path: str | None = None, top_k: int = 10) -> Dict[str, Any]:
    profile_path = profile_path or default_profile_path()
    catalog_path = catalog_path or default_catalog_path()

    profile = load_profile(profile_path)
    if isinstance(user_request, dict):
        profile = _override_profile(profile, user_request)
    catalog = load_catalog(catalog_path)

    available = profile.equipment_available
    injuries = profile.injuries_limitations
    avoid = profile.avoid

    candidates: List[Dict[str, Any]] = []
    for ex in catalog.exercises:
        exd = ex.model_dump()
        if not _has_equipment(exd.get("equipment", []), available):
            continue
        if not _contra_ok(exd.get("contraindications", []), injuries, avoid):
            continue

        s, br, reasons = _score_exercise(exd, profile)
        candidates.append({
            "id": exd["id"],
            "name": exd["name"],
            "score": round(s, 3),
            "score_breakdown": {k: round(v, 3) for k, v in br.items()},
            "reasons": reasons,
            "muscles_primary": exd.get("muscles_primary", []),
            "equipment": exd.get("equipment", []),
            "tags": exd.get("tags", []),
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return {
        "type": "matcher",
        "profile": profile.model_dump(),
        "top": candidates[:top_k],
        "count": len(candidates),
        "note": "Hard filters: equipment + contraindications. Ranking: goal/injury/preferences/level.",
    }

def build_3day_split(match_result: Dict[str, Any]) -> Dict[str, Any]:
    top = match_result.get("top", [])
    push, pull, legs, prehab = [], [], [], []
    for ex in top:
        muscles = {m.lower() for m in (ex.get("muscles_primary") or [])}
        tags = {t.lower() for t in (ex.get("tags") or [])}
        if {"rotator_cuff","scapular","prehab"} & tags:
            prehab.append(ex)
        elif muscles & {"chest","shoulders","triceps"}:
            push.append(ex)
        elif muscles & {"back","lats","biceps","rear delts"}:
            pull.append(ex)
        elif muscles & {"quads","hamstrings","glutes","calves"}:
            legs.append(ex)

    def pick(lst, n): return lst[:n] if lst else []
    return {
        "type": "plan_3day",
        "plan": {
            "day1_push": pick(push, 5) + pick(prehab, 2),
            "day2_pull": pick(pull, 5) + pick(prehab, 2),
            "day3_legs": pick(legs, 5) + pick(prehab, 1),
        },
        "guidance": "Main: 3–4 sets x 6–12 reps. Accessories/prehab: 2–3 sets x 12–20 reps.",
    }

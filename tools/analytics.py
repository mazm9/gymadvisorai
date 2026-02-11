from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Literal, Optional

from .history import read_events
from .json_io import default_catalog_path, load_catalog

Op = Literal[
    "count",
    "filter",
    "aggregate",
    "aggregate_muscles",
    "latest_match",
    "diff_matches",
]

def _latest_match_event() -> Optional[Dict[str, Any]]:
    events = [e for e in read_events() if e.get("type") == "match_result"]
    return events[-1] if events else None

def run(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic analytics tool.

    Supported ops:
      - count: count exercises by tag/movement/difficulty (optional filter by value)
      - filter: filter exercises by simple constraints (equipment/tags/exclude contra)
      - aggregate / aggregate_muscles: aggregate muscles coverage for a list of exercise ids
      - latest_match: return last matcher result (from history)
      - diff_matches: compare last two matcher results
    """
    op: str = (spec.get("op") or "").strip()

    if op not in (
        "count",
        "filter",
        "aggregate",
        "aggregate_muscles",
        "latest_match",
        "diff_matches",
    ):
        return {
            "error": f"Unsupported op: {op}",
            "supported": [
                "count",
                "filter",
                "aggregate",
                "aggregate_muscles",
                "latest_match",
                "diff_matches",
            ],
        }

    # --- temporal / history ---
    if op in ("latest_match", "diff_matches"):
        events = [e for e in read_events() if e.get("type") == "match_result"]
        if not events:
            return {"op": op, "items": [], "note": "No match history yet."}

        if op == "latest_match":
            return {"op": op, "match": events[-1]}

        if len(events) < 2:
            return {"op": op, "note": "Need at least two match runs to compute diff.", "match": events[-1]}

        a, b = events[-2], events[-1]
        a_ids = [x.get("id") for x in a.get("payload", {}).get("top", [])]
        b_ids = [x.get("id") for x in b.get("payload", {}).get("top", [])]
        a_set = set([i for i in a_ids if i])
        b_set = set([i for i in b_ids if i])

        return {
            "op": op,
            "added": [i for i in b_ids if i and i not in a_set],
            "removed": [i for i in a_ids if i and i not in b_set],
            "a_ts": a.get("ts"),
            "b_ts": b.get("ts"),
        }

    # --- catalog-backed analytics ---
    catalog = load_catalog(default_catalog_path())
    exercises = [e.model_dump() for e in catalog.exercises]

    # COUNT
    if op == "count":
        by = (spec.get("by") or "tag").strip()
        value = (spec.get("value") or "").strip().lower()

        counter = Counter()
        if by == "tag":
            for e in exercises:
                for t in e.get("tags", []):
                    counter[t] += 1
        elif by in ("movement", "difficulty"):
            for e in exercises:
                counter[str(e.get(by, ""))] += 1
        else:
            return {"error": f"Unsupported count.by: {by}", "supported_by": ["tag", "movement", "difficulty"]}

        if value:
            return {"op": op, "by": by, "value": value, "count": int(counter.get(value, 0))}
        return {"op": op, "by": by, "counts": dict(counter)}

    # FILTER
    if op == "filter":
        equipment = set([x.lower().strip() for x in (spec.get("equipment") or [])])
        tags = set([x.lower().strip() for x in (spec.get("tags") or [])])

        # support both names: exclude_contraindications and exclude_contra
        exclude_raw = spec.get("exclude_contraindications")
        if exclude_raw is None:
            exclude_raw = spec.get("exclude_contra")
        exclude_contras = set([x.lower().strip() for x in (exclude_raw or [])])

        out = []
        for e in exercises:
            eq = set([x.lower().strip() for x in e.get("equipment", [])])
            t = set([x.lower().strip() for x in e.get("tags", [])])
            contras = set([x.lower().strip() for x in e.get("contraindications", [])])

            if equipment and not equipment.issubset(eq):
                continue
            if tags and not tags.issubset(t):
                continue
            if exclude_contras and (exclude_contras & contras):
                continue

            out.append(
                {
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "movement": e.get("movement"),
                    "tags": e.get("tags", []),
                    "equipment": e.get("equipment", []),
                }
            )

        return {"op": op, "items": out[: int(spec.get("limit") or 20)], "total": len(out)}

    # AGGREGATE MUSCLES
    if op in ("aggregate", "aggregate_muscles"):
        # either explicit ids, or use last matcher top
        ids = spec.get("exercise_ids")
        if not ids and spec.get("input") == "last_match_top":
            ev = _latest_match_event()
            if ev:
                ids = [x.get("id") for x in ev.get("payload", {}).get("top", [])]

        ids_set = set([str(x) for x in (ids or []) if x])
        counter = Counter()

        for e in exercises:
            if e.get("id") not in ids_set:
                continue
            for m in e.get("muscles_primary", []):
                counter[m] += 1
            for m in e.get("muscles_secondary", []):
                counter[m] += 0.5

        return {"op": op, "exercise_ids": list(ids_set), "muscle_coverage": dict(counter)}

    return {"error": "unreachable"}

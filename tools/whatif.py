from __future__ import annotations
import os, json, copy
from typing import Any, Dict

from .json_io import load_profile, default_profile_path
from .matcher import match_exercises, build_3day_split
from .history import log_event

SCENARIO_PATH = "data/history/profile_scenario.json"

def simulate(profile_patch: Dict[str, Any], *, top_k: int = 10) -> Dict[str, Any]:
    """What-if scenario planning: patch profile fields and rerun matching.
    Returns new top picks + draft plan. Also logs an event.
    """
    base = load_profile(default_profile_path())
    data = base.model_dump()
    for k, v in (profile_patch or {}).items():
        data[k] = v

    os.makedirs(os.path.dirname(SCENARIO_PATH), exist_ok=True)
    with open(SCENARIO_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    m = match_exercises("", profile_path=SCENARIO_PATH, top_k=top_k)
    p = build_3day_split(m)
    out = {"profile_patch": profile_patch, "match": m, "plan": p}
    log_event("what_if", out)
    return out

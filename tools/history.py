from __future__ import annotations
import json, os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

DEFAULT_LOG_PATH = "data/history/events.jsonl"

def log_event(event_type: str, payload: Dict[str, Any], *, path: str = DEFAULT_LOG_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def read_events(*, path: str = DEFAULT_LOG_PATH, limit: int = 200) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out[-limit:]

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class GeminiQuotaState:
    date: str
    requests: int


def load_quota_state(path: str) -> GeminiQuotaState:
    today = today_key()
    file = Path(path)
    if not file.exists():
        return GeminiQuotaState(date=today, requests=0)
    try:
        parsed = json.loads(file.read_text(encoding="utf-8"))
        if parsed.get("date") == today and isinstance(parsed.get("requests"), int):
            return GeminiQuotaState(date=today, requests=int(parsed["requests"]))
    except Exception:
        pass
    return GeminiQuotaState(date=today, requests=0)


def save_quota_state(path: str, state: GeminiQuotaState) -> None:
    Path(path).write_text(json.dumps({"date": state.date, "requests": state.requests}, indent=2), encoding="utf-8")


def consume_quota(state: GeminiQuotaState) -> GeminiQuotaState:
    return GeminiQuotaState(date=state.date, requests=state.requests + 1)


def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


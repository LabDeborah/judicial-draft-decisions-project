from __future__ import annotations

import sys
from pathlib import Path

from app.services.gemini_quota import GeminiQuotaState, save_quota_state, today_key


def _read_arg_value(argv: list[str], key: str) -> str | None:
    try:
        idx = argv.index(key)
    except ValueError:
        return None
    return argv[idx + 1] if idx + 1 < len(argv) else None


def main() -> None:
    quota_file = _read_arg_value(sys.argv[1:], "--quota-file") or "outputs/reports/gemini_quota_state.json"
    Path(quota_file).parent.mkdir(parents=True, exist_ok=True)
    save_quota_state(quota_file, GeminiQuotaState(date=today_key(), requests=0))
    print(f"Quota resetada: {quota_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Falha ao resetar quota: {error}", file=sys.stderr)
        raise SystemExit(1)


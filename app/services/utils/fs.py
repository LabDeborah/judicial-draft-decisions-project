from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def write_text(file_path: str, content: str) -> str:
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 4):
        try:
            target.write_text(content, encoding="utf-8")
            return str(target)
        except OSError as exc:
            msg = str(exc)
            if ("EBUSY" not in msg and "EACCES" not in msg) or attempt == 3:
                break
            time.sleep(0.25 * attempt)

    stamp = datetime.utcnow().isoformat().replace(":", "-")
    fallback = target.with_name(f"{target.stem}-{stamp}{target.suffix}")
    try:
        fallback.write_text(content, encoding="utf-8")
        return str(fallback)
    except OSError:
        alt_dir = Path("outputs/reports/fallback-writes")
        alt_dir.mkdir(parents=True, exist_ok=True)
        alt_file = alt_dir / f"{target.stem}-{stamp}{target.suffix or '.txt'}"
        alt_file.write_text(content, encoding="utf-8")
        return str(alt_file)


def is_dir_writable(path: str) -> bool:
    target = Path(path)
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False

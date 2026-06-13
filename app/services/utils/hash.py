from __future__ import annotations

import hashlib


def sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


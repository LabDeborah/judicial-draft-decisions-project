from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    fixed = _repair_mojibake_if_needed(text)
    return re.sub(r"\s+", " ", fixed).strip()


def normalize_for_matching(text: str) -> str:
    normalized = normalize_text(text)
    decomp = unicodedata.normalize("NFD", normalized)
    no_accents = "".join(ch for ch in decomp if unicodedata.category(ch) != "Mn")
    return no_accents.lower()


def _repair_mojibake_if_needed(text: str) -> str:
    if not _has_mojibake_pattern(text):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    return text if _has_mojibake_pattern(repaired) else repaired


def _has_mojibake_pattern(text: str) -> bool:
    return bool(re.search(r"Ã.|Â.|â.|�", text))


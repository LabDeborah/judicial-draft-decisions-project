from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    fixed = _repair_mojibake_if_needed(str(text))
    return re.sub(r"\s+", " ", fixed).strip()


def normalize_for_matching(text: str) -> str:
    normalized = normalize_text(text)
    decomp = unicodedata.normalize("NFD", normalized)
    no_accents = "".join(ch for ch in decomp if unicodedata.category(ch) != "Mn")
    return no_accents.lower()


def _repair_mojibake_if_needed(text: str) -> str:
    if not _has_mojibake_pattern(text):
        return text
    repaired = text
    for _ in range(2):
        next_value = _repair_mojibake_once(repaired)
        if next_value == repaired:
            break
        repaired = next_value
        if not _has_mojibake_pattern(repaired):
            break
    return repaired


def _repair_mojibake_once(text: str) -> str:
    for source_encoding in ("cp1252", "latin1"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except UnicodeError:
            continue
        if _repair_score(repaired) <= _repair_score(text):
            return repaired
    return text


def _repair_score(text: str) -> int:
    score = len(re.findall(r"Ã.|Â.|â.|ï¿½|�", text))
    score += text.count("Ã") + text.count("Â") + text.count("â")
    return score


def _has_mojibake_pattern(text: str) -> bool:
    return bool(re.search(r"Ã.|Â.|â.|ï¿½|�", text))

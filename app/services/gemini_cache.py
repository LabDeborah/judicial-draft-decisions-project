from __future__ import annotations

import json
from pathlib import Path

from app.domain.types import AnalysisOutput, TnuTheme, Trf2Decision
from app.utils.hash import sha1
from app.utils.text import normalize_for_matching


def load_gemini_cache(path: str) -> dict[str, dict]:
    file = Path(path)
    if not file.exists():
        return {}
    try:
        parsed = json.loads(file.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def save_gemini_cache(path: str, cache: dict[str, dict]) -> None:
    Path(path).write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def build_gemini_cache_key(decision: Trf2Decision, themes: list[TnuTheme]) -> str:
    decision_fingerprint = sha1(f"{decision.numeroProcesso}|{normalize_for_matching(decision.assuntos)}")
    theme_signature_raw = "||".join(
        [
            f"{item.temaNumero}|{normalize_for_matching(item.questaoSubmetidaJulgamento)}|{normalize_for_matching(item.teseFirmada)}"
            for item in themes
        ]
    )
    theme_signature = sha1(theme_signature_raw)
    return f"{decision_fingerprint}:{theme_signature}"


def to_analysis_output(data: dict) -> AnalysisOutput:
    return AnalysisOutput(
        decisionId=str(data.get("decisionId", "")),
        temaTnu=str(data.get("temaTnu", "NENHUM_TEMA")),
        consonancia=str(data.get("consonancia", "NAO_APLICAVEL")),  # type: ignore[arg-type]
        validade=str(data.get("validade", "INVALIDA")),  # type: ignore[arg-type]
        justificativa=str(data.get("justificativa", "Sem justificativa fornecida.")),
    )


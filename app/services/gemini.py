from __future__ import annotations

import json
from functools import lru_cache

import requests

from app.domain.types import AnalysisOutput, TnuTheme, Trf2Decision

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL_RESOLUTION_CACHE: dict[str, str] = {}


def analyze_decision_with_gemini(
    decision: Trf2Decision, themes: list[TnuTheme], api_key: str, model: str
) -> AnalysisOutput:
    prompt = _build_prompt(decision, themes)
    parsed = _request_gemini(prompt, api_key, model)
    return AnalysisOutput(
        decisionId=decision.decisionId,
        temaTnu=parsed["temaTnu"],
        consonancia=parsed["consonancia"],  # type: ignore[arg-type]
        validade=parsed["validade"],  # type: ignore[arg-type]
        justificativa=parsed["justificativa"],
    )


def _request_gemini(prompt: str, api_key: str, model: str) -> dict[str, str]:
    requested_model = model.strip()
    active_model = _MODEL_RESOLUTION_CACHE.get(requested_model, requested_model)
    try:
        body = _generate_content(prompt, api_key, active_model)
    except RuntimeError as error:
        reason = str(error)
        if "404" not in reason:
            raise
        fallback_model = _resolve_fallback_model(requested_model, api_key, exclude={active_model})
        if not fallback_model:
            raise RuntimeError(
                f"Gemini HTTP 404 (modelo '{requested_model}' nao encontrado e sem fallback disponivel)."
            ) from error
        _MODEL_RESOLUTION_CACHE[requested_model] = fallback_model
        body = _generate_content(prompt, api_key, fallback_model)

    raw = (
        body.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return _parse_gemini_json(str(raw))

def _generate_content(prompt: str, api_key: str, model: str) -> dict:
    url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    resp = requests.post(url, json=payload, timeout=60)
    if not resp.ok:
        if resp.status_code == 429:
            raise RuntimeError("Gemini HTTP 429")
        detail = _extract_error_message(resp)
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")
    return resp.json()


def _extract_error_message(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200].strip() or "sem detalhe"
    message = body.get("error", {}).get("message")
    return str(message).strip() if message else "sem detalhe"


def _resolve_fallback_model(requested_model: str, api_key: str, exclude: set[str]) -> str | None:
    available = _list_generate_content_models(api_key)
    candidates = _build_model_candidates(requested_model)
    for candidate in candidates:
        if candidate in exclude:
            continue
        if candidate in available:
            return candidate
    return None


@lru_cache(maxsize=8)
def _list_generate_content_models(api_key: str) -> tuple[str, ...]:
    resp = requests.get(f"{MODEL_LIST_URL}?key={api_key}", timeout=30)
    if not resp.ok:
        return tuple()
    body = resp.json()
    models = []
    for item in body.get("models", []):
        methods = item.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = str(item.get("name", "")).replace("models/", "").strip()
        if name:
            models.append(name)
    return tuple(models)


def _build_model_candidates(requested_model: str) -> list[str]:
    normalized = requested_model.strip().removeprefix("models/")
    candidates: list[str] = []

    def add(value: str) -> None:
        clean = value.strip()
        if clean and clean not in candidates:
            candidates.append(clean)

    add(normalized)
    add(f"{normalized}-preview")
    add(f"{normalized}-latest")
    if "flash-lite" in normalized:
        add(normalized.replace("flash-lite", "flash-lite-preview"))
    if normalized == "gemini-3.1-flash-lite":
        add("gemini-3.1-flash-lite-preview")
    add("gemini-flash-lite-latest")
    add("gemini-2.5-flash-lite")
    add("gemini-2.0-flash-lite")
    add("gemini-2.0-flash-lite-001")
    add("gemini-2.5-flash")
    add("gemini-flash-latest")
    return candidates


def _build_prompt(decision: Trf2Decision, themes: list[TnuTheme]) -> str:
    compact_themes = [
        {
            "temaNumero": theme.temaNumero,
            "questaoSubmetidaJulgamento": theme.questaoSubmetidaJulgamento,
            "teseFirmada": theme.teseFirmada,
        }
        for theme in themes
    ]
    lines = [
        "Classifique uma decisao judicial em um tema da TNU.",
        "Responda APENAS em JSON valido, sem markdown e sem texto fora do JSON.",
        'Formato exato: {"temaTnu":"string","consonancia":"CONSONANCIA|DISSONANCIA|NAO_APLICAVEL","validade":"VALIDA|INCOMPLETA|INVALIDA","justificativa":"string"}',
        'Se nenhum tema se encaixar, use "NENHUM_TEMA" em temaTnu e "NAO_APLICAVEL" em consonancia.',
        "Use a tese firmada para avaliar consonancia somente quando existir tese.",
        "",
        f"Decisao: {json.dumps(decision.to_dict(), ensure_ascii=False)}",
        f"Temas: {json.dumps(compact_themes, ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def _parse_gemini_json(raw: str) -> dict[str, str]:
    normalized = raw.strip()
    if normalized.lower().startswith("```json"):
        normalized = normalized[7:].strip()
    if normalized.endswith("```"):
        normalized = normalized[:-3].strip()
    candidate = _extract_json_object(normalized)
    if not candidate:
        raise RuntimeError("Resposta Gemini nao contem JSON valido.")
    parsed = json.loads(candidate)
    consonancia = _normalize_consonancia(parsed.get("consonancia"))
    validade = _normalize_validade(parsed.get("validade"))
    return {
        "temaTnu": str(parsed.get("temaTnu", "NENHUM_TEMA")).strip() or "NENHUM_TEMA",
        "consonancia": consonancia,
        "validade": validade,
        "justificativa": str(parsed.get("justificativa", "Sem justificativa fornecida.")).strip()
        or "Sem justificativa fornecida.",
    }


def _extract_json_object(text: str) -> str | None:
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first : last + 1]


def _normalize_consonancia(value) -> str:
    if value in ("CONSONANCIA", "DISSONANCIA", "NAO_APLICAVEL"):
        return value
    return "NAO_APLICAVEL"


def _normalize_validade(value) -> str:
    if value in ("VALIDA", "INCOMPLETA", "INVALIDA"):
        return value
    return "INVALIDA"

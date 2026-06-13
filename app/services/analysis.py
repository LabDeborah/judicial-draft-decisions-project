from __future__ import annotations

import re
import time
from dataclasses import dataclass

from app.domain.types import AnalysisMode, AnalysisOutput, TnuTheme, Trf2Decision
from app.services.gemini import analyze_decision_with_gemini
from app.services.gemini_cache import build_gemini_cache_key, load_gemini_cache, save_gemini_cache
from app.services.gemini_quota import consume_quota, load_quota_state, save_quota_state
from app.utils.text import normalize_for_matching


@dataclass(slots=True)
class AnalysisOptions:
    analysis_mode: AnalysisMode
    gemini_api_key: str | None
    gemini_model: str
    gemini_delay_ms: int
    gemini_cooldown_ms: int
    gemini_429_threshold: int
    gemini_max_quota_errors: int
    gemini_cache_file: str
    gemini_requests_per_minute: int
    gemini_requests_per_day: int
    gemini_quota_state_file: str


def analyze_decisions(
    decisions: list[Trf2Decision], themes: list[TnuTheme], options: AnalysisOptions
) -> list[AnalysisOutput]:
    if options.analysis_mode == "local":
        return [analyze_decision_local(decision, themes) for decision in decisions]
    if not options.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY nao configurada para --analysis-mode gemini.")

    cache = load_gemini_cache(options.gemini_cache_file)
    quota_state = load_quota_state(options.gemini_quota_state_file)
    outputs: list[AnalysisOutput] = []
    consecutive_429 = 0
    total_429_errors = 0
    quota_exhausted = False
    last_gemini_request_at = 0.0
    min_interval_s = 60.0 / options.gemini_requests_per_minute

    for index, decision in enumerate(decisions):
        cache_key = build_gemini_cache_key(decision, themes)
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("validade") == "VALIDA":
            outputs.append(
                AnalysisOutput(
                    decisionId=decision.decisionId,
                    temaTnu=str(cached.get("temaTnu", "NENHUM_TEMA")),
                    consonancia=str(cached.get("consonancia", "NAO_APLICAVEL")),  # type: ignore[arg-type]
                    validade=str(cached.get("validade", "INVALIDA")),  # type: ignore[arg-type]
                    justificativa=f"{cached.get('justificativa', '')} | Resultado reutilizado do cache Gemini.",
                )
            )
            continue

        if index > 0 and options.gemini_delay_ms > 0:
            time.sleep(options.gemini_delay_ms / 1000.0)

        if quota_exhausted or quota_state.requests >= options.gemini_requests_per_day:
            local_fallback = analyze_decision_local(decision, themes)
            outputs.append(
                AnalysisOutput(
                    decisionId=local_fallback.decisionId,
                    temaTnu=local_fallback.temaTnu,
                    consonancia=local_fallback.consonancia,
                    validade="INVALIDA",
                    justificativa=(
                        f"{local_fallback.justificativa} | Fallback local informativo: quota Gemini diaria "
                        "esgotada ou indisponivel; classificacao marcada como INVALIDA para evitar decisao automatica."
                    ),
                )
            )
            continue

        resolved = False
        queue_cooldown_used = False
        while not resolved:
            try:
                elapsed = time.time() - last_gemini_request_at
                if elapsed < min_interval_s:
                    time.sleep(min_interval_s - elapsed)
                quota_state = consume_quota(quota_state)
                save_quota_state(options.gemini_quota_state_file, quota_state)
                last_gemini_request_at = time.time()

                candidate_themes = _select_candidate_themes_for_gemini(decision, themes)
                output = analyze_decision_with_gemini(
                    decision,
                    candidate_themes,
                    options.gemini_api_key,
                    options.gemini_model,
                )
                consecutive_429 = 0
                cache[cache_key] = output.to_dict()
                outputs.append(output)
                resolved = True
            except Exception as error:
                reason = str(error)
                if "429" in reason:
                    consecutive_429 += 1
                    total_429_errors += 1
                    if total_429_errors >= options.gemini_max_quota_errors:
                        quota_exhausted = True
                    if not queue_cooldown_used and consecutive_429 >= options.gemini_429_threshold:
                        queue_cooldown_used = True
                        consecutive_429 = 0
                        time.sleep(options.gemini_cooldown_ms / 1000.0)
                        continue
                    if queue_cooldown_used and consecutive_429 >= options.gemini_429_threshold:
                        quota_exhausted = True
                else:
                    consecutive_429 = 0

                local_fallback = analyze_decision_local(decision, themes)
                outputs.append(
                    AnalysisOutput(
                        decisionId=local_fallback.decisionId,
                        temaTnu=local_fallback.temaTnu,
                        consonancia=local_fallback.consonancia,
                        validade="INVALIDA",
                        justificativa=(
                            f"{local_fallback.justificativa} | Fallback local informativo por erro Gemini ({reason}); "
                            "classificacao marcada como INVALIDA para evitar decisao automatica."
                        ),
                    )
                )
                resolved = True

    save_gemini_cache(options.gemini_cache_file, cache)
    return outputs


def analyze_decision_local(decision: Trf2Decision, themes: list[TnuTheme]) -> AnalysisOutput:
    theme = _match_theme(decision, themes)
    if not theme:
        return AnalysisOutput(
            decisionId=decision.decisionId,
            temaTnu="NENHUM_TEMA",
            consonancia="NAO_APLICAVEL",
            validade="VALIDA",
            justificativa="Nenhum tema com palavras-chave em comum.",
        )
    consonancia = _infer_consonancia(decision, theme)
    validade = _infer_validade(theme, consonancia)
    return AnalysisOutput(
        decisionId=decision.decisionId,
        temaTnu=theme.temaNumero,
        consonancia=consonancia,
        validade=validade,
        justificativa=f"Tema {theme.temaNumero} selecionado por semelhanca de assunto.",
    )


def _match_theme(decision: Trf2Decision, themes: list[TnuTheme]) -> TnuTheme | None:
    decision_tokens = _decision_tokens(decision)
    winner = None
    best_score = 0
    for theme in themes:
        theme_tokens = _theme_tokens(theme)
        score = len(decision_tokens.intersection(theme_tokens))
        if score > best_score:
            best_score = score
            winner = theme
    return winner if best_score > 0 else None


def _select_candidate_themes_for_gemini(decision: Trf2Decision, themes: list[TnuTheme]) -> list[TnuTheme]:
    if len(themes) <= 12:
        return themes
    decision_tokens = _decision_tokens(decision)
    ranked = sorted(
        themes,
        key=lambda theme: (
            len(decision_tokens.intersection(_theme_tokens(theme))),
            1 if normalize_for_matching(theme.ramoDireito) in _decision_theme_text(decision) else 0,
            len(theme.teseFirmada),
            len(theme.questaoSubmetidaJulgamento),
        ),
        reverse=True,
    )
    positive = [
        theme for theme in ranked if len(decision_tokens.intersection(_theme_tokens(theme))) > 0
    ]
    if positive:
        return positive[:12]
    return ranked[:12]


def _infer_consonancia(decision: Trf2Decision, theme: TnuTheme):
    if not theme.teseFirmada.strip():
        return "NAO_APLICAVEL"
    return "DISSONANCIA" if any(w in decision.assuntos.lower() for w in ["nao", "invalido", "improcedente", "negado"]) else "CONSONANCIA"


def _infer_validade(theme: TnuTheme, consonancia: str):
    if not theme.temaNumero.strip():
        return "INVALIDA"
    if theme.teseFirmada.strip() and consonancia == "NAO_APLICAVEL":
        return "INCOMPLETA"
    return "VALIDA"


def _tokenize(text: str) -> set[str]:
    normalized = normalize_for_matching(text)
    return {token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) > 2}


def _decision_theme_text(decision: Trf2Decision) -> str:
    return " ".join(
        part
        for part in [decision.assuntos, decision.classe, decision.competencia]
        if part and part != "NAO_INFORMADO"
    )


def _decision_tokens(decision: Trf2Decision) -> set[str]:
    return _tokenize(_decision_theme_text(decision))


def _theme_tokens(theme: TnuTheme) -> set[str]:
    return _tokenize(f"{theme.questaoSubmetidaJulgamento} {theme.teseFirmada} {theme.ramoDireito}")

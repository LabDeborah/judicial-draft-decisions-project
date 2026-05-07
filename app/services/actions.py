from __future__ import annotations

from app.domain.types import AnalysisOutput, DocumentDecision, TnuTheme


def derive_document_action(analysis: AnalysisOutput, theme: TnuTheme | None) -> DocumentDecision:
    if analysis.validade != "VALIDA" or analysis.temaTnu == "NENHUM_TEMA" or theme is None:
        return DocumentDecision(decisionId=analysis.decisionId, temaTnu=analysis.temaTnu, action="SEM_ACAO")
    action = _pick_action(theme, analysis.consonancia)
    return DocumentDecision(decisionId=analysis.decisionId, temaTnu=analysis.temaTnu, action=action)


def _pick_action(theme: TnuTheme, consonancia: str) -> str:
    if not theme.dataJulgamento or not theme.transitoJulgado:
        return "SOBRESTAR"
    if consonancia == "CONSONANCIA":
        return "NEGAR_SEGUIMENTO"
    if consonancia == "DISSONANCIA":
        return "DETERMINAR_ADEQUACAO"
    return "SEM_ACAO"


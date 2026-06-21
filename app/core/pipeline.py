from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import CliConfig
from app.domain.types import TnuTheme, Trf2Decision
from app.services.actions import derive_document_action
from app.services.analysis import AnalysisOptions, analyze_decision_local, analyze_decisions
from app.services.collectors import collect_tnu_themes, collect_trf2_decisions
from app.services.csv import write_csv
from app.services.documents import generate_decision_drafts
from app.services.gemini_quota import load_quota_state
from app.services.semantic import SemanticRunContext, generate_semantic_artifacts
from app.services.source_artifacts import materialize_source_artifacts
from app.utils.fs import ensure_dir
from app.utils.text import normalize_for_matching


@dataclass(slots=True)
class PipelineSummary:
    run_dir: str
    themes: int
    decisions: int
    analyses: int
    generated_drafts: int
    generated_pdfs: int
    semantic_documents: int
    semantic_execution_graph: str
    data_csv_dir: str


def run_pipeline(config: CliConfig) -> PipelineSummary:
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = f"outputs/runs/{run_id}"
    reports_dir = f"{run_dir}/reports"
    documents_dir = f"{run_dir}/documents"
    semantic_dir = f"{run_dir}/semantic"
    data_csv_dir = f"{run_dir}/data"
    ensure_dir(run_dir)
    ensure_dir(reports_dir)
    ensure_dir(documents_dir)
    ensure_dir(semantic_dir)
    ensure_dir(data_csv_dir)
    _log_progress(
        "pipeline",
        (
            f"run={run_id} mode={config.mode} analysis={config.analysis_mode} "
            f"limit={config.limit} analysis_limit={config.analysis_limit or 'auto'} "
            f"compile_pdf={config.compile_pdf}"
        ),
    )

    theme_limit = _theme_collection_limit(config)
    _log_progress("collect", f"collecting TNU themes target={theme_limit}")
    themes = collect_tnu_themes(
        config.mode,
        theme_limit,
        config.browser_automation,
        import_csv_file=config.import_tnu_csv_file,
    )
    _log_progress("collect", f"TNU themes collected={len(themes)}")
    _log_progress("collect", f"collecting TRF2 decisions target={config.limit}")
    decisions = collect_trf2_decisions(
        config.mode,
        config.limit,
        config.browser_automation,
        import_csv_file=config.import_trf2_csv_file,
        themes=themes,
    )
    _log_progress("collect", f"TRF2 decisions collected={len(decisions)}")
    decisions_for_analysis = _select_decisions_for_analysis(decisions, themes, config)
    _log_progress("analysis", f"decisions selected for analysis={len(decisions_for_analysis)}")
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip() if config.analysis_mode == "gemini" else None
    analyses = analyze_decisions(
        decisions_for_analysis,
        themes,
        AnalysisOptions(
            analysis_mode=config.analysis_mode,
            gemini_api_key=gemini_api_key or None,
            gemini_model=config.gemini_model,
            gemini_delay_ms=config.gemini_delay_ms,
            gemini_cooldown_ms=config.gemini_cooldown_ms,
            gemini_429_threshold=config.gemini_429_threshold,
            gemini_max_quota_errors=config.gemini_max_quota_errors,
            gemini_cache_file=config.gemini_cache_file,
            gemini_requests_per_minute=config.gemini_requests_per_minute,
            gemini_requests_per_day=config.gemini_requests_per_day,
            gemini_quota_state_file=config.gemini_quota_state_file,
        ),
    )
    _log_progress("analysis", f"analyses produced={len(analyses)}")

    docs = [
        derive_document_action(analysis, next((t for t in themes if t.temaNumero == analysis.temaTnu), None))
        for analysis in analyses
    ]
    actionable_docs = len([doc for doc in docs if doc.action != "SEM_ACAO"])
    _log_progress("documents", f"document actions derived={actionable_docs}/{len(docs)} actionable")
    artifact_themes = _themes_for_artifacts(themes, analyses)
    _log_progress(
        "artifacts",
        f"materializing source PDFs decisions={len(decisions_for_analysis)} themes={len(artifact_themes)}",
    )
    materialize_source_artifacts(
        data_dir=data_csv_dir,
        themes=artifact_themes,
        decisions=decisions_for_analysis,
        latex_engine=config.latex_engine,
        trf2_chrome_profile=config.trf2_chrome_profile,
    )
    _log_progress("artifacts", "source artifacts materialized")

    _log_progress("reports", "writing CSV outputs")
    write_csv(f"{data_csv_dir}/tnu_temas.csv", [item.to_dict() for item in themes])
    write_csv(f"{data_csv_dir}/trf2_decisoes.csv", [item.to_dict() for item in decisions])
    write_csv(f"{reports_dir}/analises.csv", [item.to_dict() for item in analyses])
    write_csv(f"{reports_dir}/acoes_documentais.csv", [item.to_dict() for item in docs])
    comparados = []
    by_decision = {item.decisionId: item for item in decisions}
    for analysis in analyses:
        decision = by_decision.get(analysis.decisionId)
        comparados.append(
            {
                "ID DECISÃO TRF2": analysis.decisionId,
                "NUMERO PROCESSO": decision.numeroProcesso if decision else "",
                "TEMA TNU": analysis.temaTnu,
                "CONSONÂNCIA OU DISSONÂNCIA": analysis.consonancia,
            }
        )
    write_csv(f"{reports_dir}/comparados_compat.csv", comparados)
    _log_progress("documents", "generating draft documents")
    generated_drafts = generate_decision_drafts(
        docs,
        analyses,
        decisions,
        themes,
        output_dir=documents_dir,
        compile_pdf=config.compile_pdf,
        latex_engine=config.latex_engine,
    )
    generated_pdfs = len([draft for draft in generated_drafts if draft.pdf_path])
    _log_progress(
        "documents",
        f"drafts generated={len(generated_drafts)} compiled_pdfs={generated_pdfs}",
    )
    _log_progress("semantic", "generating RDF artifacts")
    semantic = generate_semantic_artifacts(
        run_id=run_id,
        output_dir=semantic_dir,
        context=SemanticRunContext(
            mode=config.mode,
            analysis_mode=config.analysis_mode,
            browser_automation=config.browser_automation,
            compile_pdf=config.compile_pdf,
            gemini_model=config.gemini_model,
            gemini_cache_file=config.gemini_cache_file,
            gemini_quota_state_file=config.gemini_quota_state_file,
        ),
        themes=themes,
        decisions=decisions,
        analyses=analyses,
        docs=docs,
        drafts=generated_drafts,
    )
    _log_progress(
        "semantic",
        f"RDF generated document_graphs={len(semantic.document_graph_paths)} execution_graph=1",
    )
    return PipelineSummary(
        run_dir=run_dir,
        themes=len(themes),
        decisions=len(decisions),
        analyses=len(analyses),
        generated_drafts=len(generated_drafts),
        generated_pdfs=generated_pdfs,
        semantic_documents=len(semantic.document_graph_paths),
        semantic_execution_graph=semantic.execution_graph_path,
        data_csv_dir=data_csv_dir,
    )


def _theme_collection_limit(config: CliConfig) -> int:
    if config.mode != "live":
        return config.limit
    return max(config.limit, 40)


def _themes_for_artifacts(themes: list[TnuTheme], analyses) -> list[TnuTheme]:
    matched_numbers = {
        analysis.temaTnu
        for analysis in analyses
        if analysis.temaTnu and analysis.temaTnu != "NENHUM_TEMA"
    }
    if not matched_numbers:
        return []
    return [theme for theme in themes if theme.temaNumero in matched_numbers]


def _select_decisions_for_analysis(
    decisions: list[Trf2Decision], themes: list[TnuTheme], config: CliConfig
) -> list[Trf2Decision]:
    if not decisions:
        return []
    ranked_decisions = sorted(
        decisions,
        key=lambda decision: _decision_priority_key(decision, themes, config.analysis_mode),
        reverse=True,
    )
    if config.analysis_limit is not None:
        return ranked_decisions[: min(config.analysis_limit, len(ranked_decisions))]
    if config.analysis_mode != "gemini":
        return ranked_decisions
    quota_state = load_quota_state(config.gemini_quota_state_file)
    remaining_quota = max(0, config.gemini_requests_per_day - quota_state.requests)
    if remaining_quota <= 0:
        return []
    return ranked_decisions[: min(len(ranked_decisions), remaining_quota)]


def _decision_analysis_richness(decision: Trf2Decision) -> int:
    score = 0
    if decision.assuntos and decision.assuntos != "NAO_INFORMADO":
        score += min(400, len(decision.assuntos))
    if decision.classe and decision.classe != "NAO_INFORMADO":
        score += 60
    if decision.relatorOriginario:
        score += 20
    if decision.dataAutuacao:
        score += 10
    return score


def _decision_priority_key(
    decision: Trf2Decision,
    themes: list[TnuTheme],
    analysis_mode: str,
) -> tuple[int, int, int, int]:
    overlap = _decision_theme_overlap_score(decision, themes)
    richness = _decision_analysis_richness(decision)
    if analysis_mode != "gemini":
        return (overlap, richness, 0, 0)
    local_analysis = analyze_decision_local(decision, themes)
    local_theme = next((theme for theme in themes if theme.temaNumero == local_analysis.temaTnu), None)
    local_action = derive_document_action(local_analysis, local_theme).action
    actionable = 1 if local_action != "SEM_ACAO" else 0
    matched_theme = 1 if local_analysis.temaTnu != "NENHUM_TEMA" else 0
    return (actionable, matched_theme, overlap, richness)


def _decision_theme_overlap_score(decision: Trf2Decision, themes: list[TnuTheme]) -> int:
    decision_tokens = _analysis_tokens(
        f"{decision.classe} {decision.assuntos} {decision.competencia} {decision.relatorOriginario}"
    )
    if not decision_tokens:
        return 0
    best = 0
    for theme in themes:
        theme_tokens = _analysis_tokens(
            f"{theme.ramoDireito} {theme.questaoSubmetidaJulgamento} {theme.teseFirmada}"
        )
        score = len(decision_tokens.intersection(theme_tokens))
        if score > best:
            best = score
    return best


def _analysis_tokens(text: str) -> set[str]:
    normalized = normalize_for_matching(text)
    return {token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) > 2}


def _log_progress(stage: str, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{stage}] {message}", file=sys.stderr)

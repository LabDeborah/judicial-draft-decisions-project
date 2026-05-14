from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.config import CliConfig
from app.services.actions import derive_document_action
from app.services.analysis import AnalysisOptions, analyze_decisions
from app.services.collectors import collect_tnu_themes, collect_trf2_decisions
from app.services.csv import write_csv
from app.services.documents import generate_decision_drafts
from app.services.semantic import SemanticRunContext, generate_semantic_artifacts
from app.utils.fs import ensure_dir, is_dir_writable


@dataclass(slots=True)
class PipelineSummary:
    themes: int
    decisions: int
    analyses: int
    generated_drafts: int
    generated_pdfs: int
    semantic_documents: int
    semantic_execution_graph: str
    data_csv_dir: str


def run_pipeline(config: CliConfig) -> PipelineSummary:
    ensure_dir("outputs/reports")
    ensure_dir("outputs/documents")
    data_csv_dir = "data/csv" if is_dir_writable("data/csv") else "outputs/data/csv"
    ensure_dir(data_csv_dir)

    themes = collect_tnu_themes(
        config.mode,
        config.limit,
        config.browser_automation,
        import_csv_file=config.import_tnu_csv_file,
    )
    decisions = collect_trf2_decisions(
        config.mode,
        config.limit,
        config.browser_automation,
        import_csv_file=config.import_trf2_csv_file,
    )
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip() if config.analysis_mode == "gemini" else None
    analyses = analyze_decisions(
        decisions,
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

    docs = [
        derive_document_action(analysis, next((t for t in themes if t.temaNumero == analysis.temaTnu), None))
        for analysis in analyses
    ]

    write_csv(f"{data_csv_dir}/tnu_temas.csv", [item.to_dict() for item in themes])
    write_csv(f"{data_csv_dir}/trf2_decisoes.csv", [item.to_dict() for item in decisions])
    write_csv("outputs/reports/analises.csv", [item.to_dict() for item in analyses])
    write_csv("outputs/reports/acoes_documentais.csv", [item.to_dict() for item in docs])
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
    write_csv("outputs/reports/comparados_compat.csv", comparados)
    generated_drafts = generate_decision_drafts(
        docs,
        analyses,
        decisions,
        themes,
        compile_pdf=config.compile_pdf,
        latex_engine=config.latex_engine,
    )
    semantic = generate_semantic_artifacts(
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
    return PipelineSummary(
        themes=len(themes),
        decisions=len(decisions),
        analyses=len(analyses),
        generated_drafts=len(generated_drafts),
        generated_pdfs=len([draft for draft in generated_drafts if draft.pdf_path]),
        semantic_documents=len(semantic.document_graph_paths),
        semantic_execution_graph=semantic.execution_graph_path,
        data_csv_dir=data_csv_dir,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from app.domain.types import AnalysisOutput, DocumentDecision, TnuTheme, Trf2Decision
from app.services.documents import GeneratedDraft
from app.utils.fs import ensure_dir, write_text

BASE_IRI = "https://example.org/tcc/"
PROV_IRI = "http://www.w3.org/ns/prov#"
TERMS_IRI = "http://purl.org/dc/terms/"
XSD_IRI = "http://www.w3.org/2001/XMLSchema#"
TCC_IRI = f"{BASE_IRI}ontology#"


@dataclass(slots=True)
class SemanticArtifacts:
    execution_graph_path: str
    document_graph_paths: list[str]


@dataclass(slots=True)
class SemanticRunContext:
    mode: str
    analysis_mode: str
    browser_automation: bool
    compile_pdf: bool
    gemini_model: str
    gemini_cache_file: str
    gemini_quota_state_file: str


def generate_semantic_artifacts(
    *,
    context: SemanticRunContext,
    themes: list[TnuTheme],
    decisions: list[Trf2Decision],
    analyses: list[AnalysisOutput],
    docs: list[DocumentDecision],
    drafts: list[GeneratedDraft],
) -> SemanticArtifacts:
    ensure_dir("outputs/semantic")
    execution_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    execution_graph_path = write_text(
        f"outputs/semantic/{execution_id}.ttl",
        _build_execution_graph(
            execution_id=execution_id,
            context=context,
            themes=themes,
            decisions=decisions,
            analyses=analyses,
            docs=docs,
            drafts=drafts,
        ),
    )

    document_graph_paths: list[str] = []
    by_analysis = {item.decisionId: item for item in analyses}
    by_decision = {item.decisionId: item for item in decisions}
    by_theme = {item.temaNumero: item for item in themes}
    by_doc = {item.decisionId: item for item in docs}
    for draft in drafts:
        analysis = by_analysis.get(draft.decision_id)
        decision = by_decision.get(draft.decision_id)
        doc = by_doc.get(draft.decision_id)
        theme = by_theme.get(analysis.temaTnu) if analysis else None
        if not analysis or not decision or not doc or not theme:
            continue
        document_graph_paths.append(
            write_text(
                f"outputs/semantic/{_slug(draft.decision_id)}-{_slug(draft.action)}.ttl",
                _build_document_graph(
                    execution_id=execution_id,
                    context=context,
                    draft=draft,
                    decision=decision,
                    theme=theme,
                    analysis=analysis,
                    doc=doc,
                ),
            )
        )

    return SemanticArtifacts(
        execution_graph_path=execution_graph_path,
        document_graph_paths=document_graph_paths,
    )


def _build_execution_graph(
    *,
    execution_id: str,
    context: SemanticRunContext,
    themes: list[TnuTheme],
    decisions: list[Trf2Decision],
    analyses: list[AnalysisOutput],
    docs: list[DocumentDecision],
    drafts: list[GeneratedDraft],
) -> str:
    now = _timestamp()
    lines = _prefixes()
    run_ref = _res("run", execution_id)
    classifier_ref = _agent_ref(context.analysis_mode, context.gemini_model)
    pipeline_ref = _res("agent", "pipeline")
    lines.extend(
        [
            f"{run_ref} a prov:Activity, tcc:PipelineRun ;",
            f'  dcterms:created "{now}"^^xsd:dateTime ;',
            f'  tcc:collectionMode {_literal(context.mode)} ;',
            f'  tcc:analysisMode {_literal(context.analysis_mode)} ;',
            f"  tcc:browserAutomation {_bool_literal(context.browser_automation)} ;",
            f"  tcc:compilePdf {_bool_literal(context.compile_pdf)} ;",
            f'  tcc:geminiModel {_literal(context.gemini_model)} ;',
            f'  tcc:geminiCacheFile {_literal(context.gemini_cache_file)} ;',
            f'  tcc:geminiQuotaStateFile {_literal(context.gemini_quota_state_file)} ;',
            f"  prov:wasAssociatedWith {pipeline_ref}, {classifier_ref} .",
            "",
            f"{pipeline_ref} a prov:Agent, tcc:SoftwarePipeline ;",
            '  dcterms:title "TCC Pipeline" .',
            "",
            _agent_block(context.analysis_mode, context.gemini_model),
            "",
        ]
    )

    theme_catalog_ref = _res("catalog", f"{execution_id}-themes")
    lines.extend(
        [
            f"{theme_catalog_ref} a prov:Entity, tcc:ThemeCatalog ;",
            f"  tcc:themeCount {_number_literal(len(themes))} ;",
            f"  prov:wasGeneratedBy {run_ref} .",
            "",
        ]
    )

    for theme in themes:
        theme_ref = _theme_ref(theme.temaNumero)
        lines.extend(
            [
                f"{theme_ref} a tcc:TnuTheme, prov:Entity ;",
                f'  tcc:temaNumero {_literal(theme.temaNumero)} ;',
                f'  tcc:situacaoTema {_literal(theme.situacaoTema)} ;',
                f'  tcc:ramoDireito {_literal(theme.ramoDireito)} ;',
                f'  tcc:questaoSubmetidaJulgamento {_literal(theme.questaoSubmetidaJulgamento)} ;',
                f'  tcc:teseFirmada {_literal(theme.teseFirmada)} ;',
                f"  prov:wasDerivedFrom {theme_catalog_ref} .",
                "",
            ]
        )

    by_doc = {item.decisionId: item for item in docs}
    by_theme = {item.temaNumero: item for item in themes}
    draft_by_decision = {item.decision_id: item for item in drafts}
    for decision in decisions:
        decision_ref = _decision_ref(decision.decisionId)
        lines.extend(
            [
                f"{decision_ref} a tcc:LegalDecision, prov:Entity ;",
                f'  tcc:decisionId {_literal(decision.decisionId)} ;',
                f'  tcc:numeroProcesso {_literal(decision.numeroProcesso)} ;',
                f'  tcc:classe {_literal(decision.classe)} ;',
                f'  tcc:tipoJulgamento {_literal(decision.tipoJulgamento)} ;',
                f'  tcc:assuntos {_literal(decision.assuntos)} ;',
                f'  tcc:competencia {_literal(decision.competencia)} ;',
                f'  tcc:relatorOriginario {_literal(decision.relatorOriginario)} ;',
                f"  prov:wasUsedBy {run_ref} .",
                "",
            ]
        )

        analysis = next((item for item in analyses if item.decisionId == decision.decisionId), None)
        if not analysis:
            continue
        analysis_ref = _analysis_ref(decision.decisionId)
        classification_ref = _res("activity", f"classification-{_slug(decision.decisionId)}")
        lines.extend(
            [
                f"{classification_ref} a prov:Activity, tcc:ClassificationActivity ;",
                f"  prov:used {decision_ref}, {theme_catalog_ref} ;",
                f"  prov:generated {analysis_ref} ;",
                f"  prov:wasAssociatedWith {classifier_ref} .",
                "",
                f"{analysis_ref} a tcc:AnalysisResult, prov:Entity ;",
                f'  tcc:temaTnu {_literal(analysis.temaTnu)} ;',
                f'  tcc:consonancia {_literal(analysis.consonancia)} ;',
                f'  tcc:validade {_literal(analysis.validade)} ;',
                f'  tcc:justificativa {_literal(analysis.justificativa)} ;',
                f"  tcc:aboutDecision {decision_ref} ;",
                f"  prov:wasGeneratedBy {classification_ref} .",
                "",
            ]
        )

        doc = by_doc.get(decision.decisionId)
        theme = by_theme.get(analysis.temaTnu)
        draft = draft_by_decision.get(decision.decisionId)
        if not doc or not theme or not draft:
            continue
        semantic_doc_ref = _draft_ref(decision.decisionId, doc.action)
        generation_ref = _res("activity", f"draft-generation-{_slug(decision.decisionId)}")
        lines.extend(
            [
                f"{generation_ref} a prov:Activity, tcc:DraftGenerationActivity ;",
                f"  prov:used {analysis_ref}, {decision_ref}, {_theme_ref(theme.temaNumero)} ;",
                f"  prov:generated {semantic_doc_ref} ;",
                f"  prov:wasAssociatedWith {pipeline_ref} .",
                "",
                f"{semantic_doc_ref} a tcc:LegalDraft, prov:Entity ;",
                f'  tcc:action {_literal(doc.action)} ;',
                f'  tcc:texPath {_literal(_rel_path(draft.tex_path))} ;',
                f'  tcc:pdfPath {_literal(_rel_path(draft.pdf_path) if draft.pdf_path else "")} ;',
                f"  tcc:generatedFromDecision {decision_ref} ;",
                f"  tcc:generatedFromAnalysis {analysis_ref} ;",
                f"  prov:wasGeneratedBy {generation_ref} .",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _build_document_graph(
    *,
    execution_id: str,
    context: SemanticRunContext,
    draft: GeneratedDraft,
    decision: Trf2Decision,
    theme: TnuTheme,
    analysis: AnalysisOutput,
    doc: DocumentDecision,
) -> str:
    classifier_ref = _agent_ref(context.analysis_mode, context.gemini_model)
    pipeline_ref = _res("agent", "pipeline")
    run_ref = _res("run", execution_id)
    decision_ref = _decision_ref(decision.decisionId)
    theme_ref = _theme_ref(theme.temaNumero)
    analysis_ref = _analysis_ref(decision.decisionId)
    classification_ref = _res("activity", f"classification-{_slug(decision.decisionId)}")
    generation_ref = _res("activity", f"draft-generation-{_slug(decision.decisionId)}")
    semantic_doc_ref = _draft_ref(decision.decisionId, doc.action)

    lines = _prefixes()
    lines.extend(
        [
            f"{run_ref} a prov:Activity, tcc:PipelineRun .",
            "",
            f"{pipeline_ref} a prov:Agent, tcc:SoftwarePipeline .",
            "",
            _agent_block(context.analysis_mode, context.gemini_model),
            "",
            f"{decision_ref} a tcc:LegalDecision, prov:Entity ;",
            f'  tcc:decisionId {_literal(decision.decisionId)} ;',
            f'  tcc:numeroProcesso {_literal(decision.numeroProcesso)} ;',
            f'  tcc:assuntos {_literal(decision.assuntos)} .',
            "",
            f"{theme_ref} a tcc:TnuTheme, prov:Entity ;",
            f'  tcc:temaNumero {_literal(theme.temaNumero)} ;',
            f'  tcc:teseFirmada {_literal(theme.teseFirmada)} .',
            "",
            f"{classification_ref} a prov:Activity, tcc:ClassificationActivity ;",
            f"  prov:used {decision_ref}, {theme_ref} ;",
            f"  prov:generated {analysis_ref} ;",
            f"  prov:wasAssociatedWith {classifier_ref} ;",
            f"  prov:wasInformedBy {run_ref} .",
            "",
            f"{analysis_ref} a tcc:AnalysisResult, prov:Entity ;",
            f'  tcc:temaTnu {_literal(analysis.temaTnu)} ;',
            f'  tcc:consonancia {_literal(analysis.consonancia)} ;',
            f'  tcc:validade {_literal(analysis.validade)} ;',
            f'  tcc:justificativa {_literal(analysis.justificativa)} ;',
            f"  prov:wasGeneratedBy {classification_ref} .",
            "",
            f"{generation_ref} a prov:Activity, tcc:DraftGenerationActivity ;",
            f"  prov:used {analysis_ref}, {decision_ref}, {theme_ref} ;",
            f"  prov:generated {semantic_doc_ref} ;",
            f"  prov:wasAssociatedWith {pipeline_ref} ;",
            f"  prov:wasInformedBy {classification_ref} .",
            "",
            f"{semantic_doc_ref} a tcc:LegalDraft, prov:Entity ;",
            f'  tcc:action {_literal(doc.action)} ;',
            f'  tcc:texPath {_literal(_rel_path(draft.tex_path))} ;',
            f'  tcc:pdfPath {_literal(_rel_path(draft.pdf_path) if draft.pdf_path else "")} ;',
            f"  tcc:generatedFromDecision {decision_ref} ;",
            f"  tcc:generatedFromAnalysis {analysis_ref} ;",
            f"  prov:wasGeneratedBy {generation_ref} .",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _prefixes() -> list[str]:
    return [
        f"@prefix prov: <{PROV_IRI}> .",
        f"@prefix dcterms: <{TERMS_IRI}> .",
        f"@prefix xsd: <{XSD_IRI}> .",
        f"@prefix tcc: <{TCC_IRI}> .",
        "",
    ]


def _agent_block(analysis_mode: str, gemini_model: str) -> str:
    agent_ref = _agent_ref(analysis_mode, gemini_model)
    if analysis_mode == "gemini":
        return "\n".join(
            [
                f"{agent_ref} a prov:Agent, tcc:LargeLanguageModel ;",
                f'  dcterms:title {_literal(gemini_model)} ;',
                '  tcc:analysisStrategy "gemini" .',
            ]
        )
    return "\n".join(
        [
            f"{agent_ref} a prov:Agent, tcc:LocalClassifier ;",
            '  dcterms:title "local-text-similarity" ;',
            '  tcc:analysisStrategy "local" .',
        ]
    )


def _agent_ref(analysis_mode: str, gemini_model: str) -> str:
    if analysis_mode == "gemini":
        return _res("agent", _slug(gemini_model))
    return _res("agent", "local-text-similarity")


def _decision_ref(decision_id: str) -> str:
    return _res("decision", decision_id)


def _theme_ref(theme_id: str) -> str:
    return _res("theme", theme_id)


def _analysis_ref(decision_id: str) -> str:
    return _res("analysis", decision_id)


def _draft_ref(decision_id: str, action: str) -> str:
    return _res("draft", f"{decision_id}-{action}")


def _res(kind: str, value: str) -> str:
    return f"<{BASE_IRI}{kind}/{_slug(value)}>"


def _slug(value: str) -> str:
    lowered = value.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "-", lowered)
    return compact.strip("-") or "item"


def _literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", " ")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _bool_literal(value: bool) -> str:
    return f'"{"true" if value else "false"}"^^xsd:boolean'


def _number_literal(value: int) -> str:
    return f'"{value}"^^xsd:integer'


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel_path(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).as_posix()
    except OSError:
        return path

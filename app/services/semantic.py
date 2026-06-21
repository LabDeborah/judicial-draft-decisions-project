from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.domain.types import AnalysisOutput, DocumentDecision, TnuTheme, Trf2Decision
from app.services.documents import GeneratedDraft
from app.services.graph_visualization import render_rdf_graph_visualization
from app.utils.fs import ensure_dir, write_text
from app.utils.identifiers import generated_decision_uuid, process_uuid, stable_uuid

ORS_IRI = "https://ontojur.com.br/ontors#"
TEMA_IRI = "https://ontojur.com.br/tnu/tema/"
TESE_IRI = "https://ontojur.com.br/tnu/tese/"
TRES_IRI = "https://ontojur.com.br/tres/"
GEMINI_IRI = "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/"
JDD_IRI = "https://ontojur.com.br/judicial-decision-draft/"
PROV_IRI = "http://www.w3.org/ns/prov#"
RDFS_IRI = "http://www.w3.org/2000/01/rdf-schema#"
PT_BR = "pt-BR"


@dataclass(slots=True)
class SemanticArtifacts:
    execution_graph_path: str
    document_graph_paths: list[str]
    visualization_paths: list[str]


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
    run_id: str,
    output_dir: str = "outputs/semantic",
    context: SemanticRunContext,
    themes: list[TnuTheme],
    decisions: list[Trf2Decision],
    analyses: list[AnalysisOutput],
    docs: list[DocumentDecision],
    drafts: list[GeneratedDraft],
) -> SemanticArtifacts:
    ensure_dir(output_dir)
    visualization_dir = f"{output_dir}/visualizations"
    execution_id = run_id
    execution_graph_path = write_text(
        f"{output_dir}/{execution_id}.ttl",
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
    visualization_paths: list[str] = []
    execution_visualization = render_rdf_graph_visualization(
        execution_graph_path,
        output_dir=visualization_dir,
    )
    if execution_visualization:
        visualization_paths.append(execution_visualization.dot_path)
        if execution_visualization.svg_path:
            visualization_paths.append(execution_visualization.svg_path)

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
        graph_path = write_text(
            f"{output_dir}/{draft.process_uuid}-{_slug(draft.action)}.ttl",
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
        document_graph_paths.append(graph_path)
        document_visualization = render_rdf_graph_visualization(
            graph_path,
            output_dir=visualization_dir,
        )
        if document_visualization:
            visualization_paths.append(document_visualization.dot_path)
            if document_visualization.svg_path:
                visualization_paths.append(document_visualization.svg_path)

    return SemanticArtifacts(
        execution_graph_path=execution_graph_path,
        document_graph_paths=document_graph_paths,
        visualization_paths=visualization_paths,
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
    lines = _prefixes()
    run_ref = _run_ref(execution_id)
    pipeline_ref = "jdd:pipeline"
    classifier_ref = _agent_ref(context.analysis_mode, context.gemini_model)
    theme_catalog_ref = _theme_catalog_ref(execution_id)
    draft_by_decision = {item.decision_id: item for item in drafts}
    analysis_by_decision = {item.decisionId: item for item in analyses}
    doc_by_decision = {item.decisionId: item for item in docs}
    theme_by_number = {item.temaNumero: item for item in themes}

    lines.extend(
        [
            f"{pipeline_ref} a prov:SoftwareAgent .",
            "",
            _agent_block(context.analysis_mode, context.gemini_model),
            "",
            f"{run_ref} a prov:Activity ;",
            f'  rdfs:label {_lang_literal(f"Pipeline run {execution_id}")} ;',
            f"  prov:wasAssociatedWith {pipeline_ref}, {classifier_ref} .",
            "",
            f"{theme_catalog_ref} a prov:Collection ;",
            f'  rdfs:label {_lang_literal("Collected TNU themes")} .',
            "",
        ]
    )

    for theme in themes:
        theme_ref = _theme_ref(theme.temaNumero)
        thesis_ref = _theme_thesis_ref(theme.temaNumero)
        lines.extend(_theme_lines(theme_ref, thesis_ref, theme))
        lines.extend(
            [
                f"{theme_catalog_ref} prov:hadMember {theme_ref} .",
                "",
            ]
        )

    for decision in decisions:
        analysis = analysis_by_decision.get(decision.decisionId)
        doc = doc_by_decision.get(decision.decisionId)
        draft = draft_by_decision.get(decision.decisionId)
        theme = theme_by_number.get(analysis.temaTnu) if analysis else None
        lines.extend(
            _decision_bundle_lines(
                execution_id=execution_id,
                context=context,
                decision=decision,
                analysis=analysis,
                doc=doc,
                draft=draft,
                theme=theme,
                include_run_link=True,
            )
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
    lines = _prefixes()
    run_ref = _run_ref(execution_id)
    pipeline_ref = "jdd:pipeline"
    lines.extend(
        [
            f"{pipeline_ref} a prov:SoftwareAgent .",
            "",
            _agent_block(context.analysis_mode, context.gemini_model),
            "",
            f"{run_ref} a prov:Activity .",
            "",
        ]
    )
    lines.extend(_theme_lines(_theme_ref(theme.temaNumero), _theme_thesis_ref(theme.temaNumero), theme))
    lines.extend(
        _decision_bundle_lines(
            execution_id=execution_id,
            context=context,
            decision=decision,
            analysis=analysis,
            doc=doc,
            draft=draft,
            theme=theme,
            include_run_link=False,
        )
    )
    return "\n".join(lines).strip() + "\n"


def _decision_bundle_lines(
    *,
    execution_id: str,
    context: SemanticRunContext,
    decision: Trf2Decision,
    analysis: AnalysisOutput | None,
    doc: DocumentDecision | None,
    draft: GeneratedDraft | None,
    theme: TnuTheme | None,
    include_run_link: bool,
) -> list[str]:
    decision_ref = _decision_ref(decision)
    decision_number = _decision_number(decision)
    lines = [
        f"{decision_ref}",
        "    a ors:AppellateDecisionOnSFCA, prov:Entity ;",
        f"    ors:decisionNumber {_literal(decision_number)} ;",
        f"    ors:subject {_lang_literal(decision.assuntos or decision.classe or 'Unknown subject')} ;",
    ]
    if include_run_link:
        lines.append(f"    prov:wasUsedBy {_run_ref(execution_id)} ;")
    if theme:
        lines.append(f"    ors:adoptsThesis {_theme_thesis_ref(theme.temaNumero)} .")
    else:
        lines[-1] = lines[-1].rstrip(" ;") + " ."
    lines.append("")

    if not analysis or not doc or not draft or not theme or doc.action == "SEM_ACAO":
        return lines

    classification_ref = _classification_ref(decision, analysis.temaTnu)
    generated_ref = _draft_ref(decision, doc.action)
    admissibility_ref = _admissibility_ref(decision, doc.action)
    classifier_ref = _agent_ref(context.analysis_mode, context.gemini_model)
    thesis_ref = _theme_thesis_ref(theme.temaNumero)

    lines.extend(
        [
            f"{generated_ref}",
            f"    a {_document_class(doc.action)}, prov:Entity ;",
            f'    rdfs:label {_lang_literal(_generated_label(doc.action, decision_number))} ;',
        ]
    )
    lines.extend(
        [
            f"    ors:adoptsThesis {thesis_ref} .",
            "",
            f"{admissibility_ref}",
            "    a ors:AdmissibilityDecision, prov:Entity ;",
            f"    ors:ruledIn {generated_ref} .",
            "",
            f"{classification_ref}",
            "    a prov:Activity ;",
            f"    prov:used {decision_ref} ;",
            f"    prov:used {_theme_ref(theme.temaNumero)} ;",
            f"    prov:generated {generated_ref} ;",
            f"    prov:wasAssociatedWith {classifier_ref} .",
            "",
        ]
    )
    return lines


def _theme_lines(theme_ref: str, thesis_ref: str, theme: TnuTheme) -> list[str]:
    theme_label = f"Tema {theme.temaNumero}"
    if theme.situacaoTema:
        theme_label = f"{theme_label} - {theme.situacaoTema}"
    return [
        f"{theme_ref}",
        "    a ors:Theme, prov:Entity ;",
        f"    ors:themeNumber {_literal(theme.temaNumero)} ;",
        f"    rdfs:label {_lang_literal(theme_label)} .",
        "",
        f"{thesis_ref}",
        "    a ors:Thesis, prov:Entity ;",
        f'    rdfs:label {_lang_literal(f"Theme {theme.temaNumero} Thesis")} ;',
        f"    ors:description {_lang_literal(theme.teseFirmada or 'No thesis text available')} ;",
        f"    ors:hasTheme {theme_ref} .",
        "",
    ]


def _prefixes() -> list[str]:
    return [
        f"@prefix ors: <{ORS_IRI}> .",
        f"@prefix tema: <{TEMA_IRI}> .",
        f"@prefix tese: <{TESE_IRI}> .",
        f"@prefix tres: <{TRES_IRI}> .",
        f"@prefix gemini: <{GEMINI_IRI}> .",
        f"@prefix jdd: <{JDD_IRI}> .",
        f"@prefix prov: <{PROV_IRI}> .",
        f"@prefix rdfs: <{RDFS_IRI}> .",
        "",
    ]


def _agent_block(analysis_mode: str, gemini_model: str) -> str:
    agent_ref = _agent_ref(analysis_mode, gemini_model)
    return f"{agent_ref} a prov:SoftwareAgent ."


def _agent_ref(analysis_mode: str, gemini_model: str) -> str:
    return f"gemini:{_gemini_resource_local(gemini_model)}"


def _decision_uuid(decision: Trf2Decision) -> str:
    return process_uuid(decision.numeroProcesso, decision.decisionId)


def _decision_number(decision: Trf2Decision) -> str:
    return (decision.numeroProcesso or "").strip() or _decision_uuid(decision)


def _decision_ref(decision: Trf2Decision) -> str:
    return f"tres:{_resource_local(_decision_number(decision))}"


def _theme_ref(theme_id: str) -> str:
    return f"tema:{_resource_local(theme_id)}"
def _draft_ref(decision: Trf2Decision, action: str) -> str:
    return _jdd_ref(f"ars-{_generated_decision_uuid(decision, action)}")


def _jdd_ref(value: str) -> str:
    return f"jdd:{_slug(value)}"


def _theme_thesis_ref(theme_id: str) -> str:
    return f"tese:{_resource_local(theme_id)}"


def _run_ref(execution_id: str) -> str:
    return _jdd_ref(f"pipeline-run-{stable_uuid('run', execution_id)}")


def _theme_catalog_ref(execution_id: str) -> str:
    return _jdd_ref(f"theme-catalog-{stable_uuid('catalog', execution_id)}")


def _classification_ref(decision: Trf2Decision, theme_id: str) -> str:
    return _jdd_ref(f"classification-{stable_uuid('classification', _decision_uuid(decision), theme_id)}")


def _admissibility_ref(decision: Trf2Decision, action: str) -> str:
    return _jdd_ref(f"admissibility-{_generated_decision_uuid(decision, action)}")


def _generated_decision_uuid(decision: Trf2Decision, action: str) -> str:
    return generated_decision_uuid(decision.numeroProcesso, action, decision.decisionId)


def _classification_label(decision_number: str, theme_number: str, analysis: AnalysisOutput) -> str:
    return (
        f"Classification for process {decision_number} and theme {theme_number} "
        f"({analysis.consonancia}; {analysis.validade})"
    )


def _generated_label(action: str, decision_number: str) -> str:
    return f"{action.replace('_', ' ').title()} draft for process {decision_number}"


def _document_class(action: str) -> str:
    classes = {
        "NEGAR_SEGUIMENTO": "ors:NotEntertainedRS",
        "SOBRESTAR": "ors:SuspendedRS",
        "DETERMINAR_ADEQUACAO": "ors:RSGrantedToRevokeDecision",
    }
    return classes.get(action, "prov:Entity")


def _resource_local(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", cleaned)
    return cleaned.strip("-") or "item"


def _gemini_resource_local(model_name: str) -> str:
    normalized = model_name.strip().lower()
    aliases = {
        "gemini-flash-lite-latest": "3-1-flash-lite",
        "models/gemini-flash-lite-latest": "3-1-flash-lite",
    }
    if normalized in aliases:
        return aliases[normalized]
    normalized = normalized.removeprefix("models/")
    normalized = normalized.removeprefix("gemini-")
    normalized = normalized.removesuffix("-latest")
    normalized = normalized.replace("2.5", "2-5")
    normalized = normalized.replace("1.5", "1-5")
    normalized = normalized.replace("3.1", "3-1")
    normalized = normalized.replace("1.0", "1-0")
    normalized = normalized.replace(".", "-")
    return _resource_local(normalized)


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


def _lang_literal(value: str, lang: str = PT_BR) -> str:
    return f'{_literal(value)}@{lang}'


def _rel_path(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).as_posix()
    except OSError:
        return path

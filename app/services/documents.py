from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from app.domain.types import AnalysisOutput, DocumentDecision, TnuTheme, Trf2Decision
from app.utils.fs import ensure_dir, write_text


def generate_decision_drafts(
    docs: list[DocumentDecision],
    analyses: list[AnalysisOutput],
    decisions: list[Trf2Decision],
    themes: list[TnuTheme],
    *,
    compile_pdf: bool = True,
    latex_engine: str | None = None,
) -> int:
    ensure_dir("outputs/documents")
    generated_pdfs = 0
    for doc in docs:
        if doc.action == "SEM_ACAO":
            continue
        analysis = next((item for item in analyses if item.decisionId == doc.decisionId), None)
        decision = next((item for item in decisions if item.decisionId == doc.decisionId), None)
        theme = next((item for item in themes if item.temaNumero == doc.temaTnu), None)
        if not analysis or not decision or not theme:
            continue
        tex = _create_latex_template(doc, decision, theme, analysis.justificativa)
        output_file = Path("outputs/documents") / f"{doc.decisionId}-{doc.action}.tex"
        write_text(str(output_file), tex)
        if compile_pdf and _compile_tex_to_pdf(output_file, latex_engine):
            generated_pdfs += 1
    return generated_pdfs


def _create_latex_template(
    doc: DocumentDecision,
    decision: Trf2Decision,
    theme: TnuTheme,
    justification: str,
) -> str:
    heading = _action_heading(doc.action)
    return f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\begin{{document}}
\\section*{{Minuta - {heading}}}
Decisao TRF2: {_sanitize(decision.decisionId)} ({_sanitize(decision.numeroProcesso)})\\\\
Tema TNU: {_sanitize(theme.temaNumero)}\\\\
Situacao do tema: {_sanitize(theme.situacaoTema)}\\\\
\\textbf{{Questao submetida:}} {_sanitize(theme.questaoSubmetidaJulgamento)}\\\\
\\textbf{{Tese firmada:}} {_sanitize(theme.teseFirmada or "Nao disponivel")}\\\\
\\textbf{{Fundamento da analise:}} {_sanitize(justification)}\\\\
\\textbf{{Ato sugerido:}} {_sanitize(heading)}
\\end{{document}}
"""


def _action_heading(action: str) -> str:
    if action == "SOBRESTAR":
        return "Sobrestamento"
    if action == "NEGAR_SEGUIMENTO":
        return "Negar Seguimento"
    if action == "DETERMINAR_ADEQUACAO":
        return "Determinacao de Adequacao"
    return "Sem Acao"


def _sanitize(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def _compile_tex_to_pdf(tex_file: Path, preferred_engine: str | None) -> bool:
    engine = _resolve_latex_engine(preferred_engine)
    if not engine:
        return False
    cmd = _build_latex_command(engine, tex_file)
    run_env = os.environ.copy()
    # Keep tectonic cache inside workspace to avoid permission issues on restricted environments.
    run_env["TECTONIC_CACHE_DIR"] = str(Path("outputs/.tectonic-cache"))
    ensure_dir(run_env["TECTONIC_CACHE_DIR"])
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=run_env,
            check=False,
        )
    except OSError:
        return False
    if completed.returncode != 0:
        return False
    pdf_file = tex_file.with_suffix(".pdf")
    return pdf_file.exists()


def _resolve_latex_engine(preferred_engine: str | None) -> str | None:
    if preferred_engine:
        return preferred_engine if shutil.which(preferred_engine) else None
    local_tectonic = Path("tools/tectonic/tectonic.exe")
    if local_tectonic.exists():
        return str(local_tectonic)
    for candidate in ("tectonic", "pdflatex"):
        if shutil.which(candidate):
            return candidate
    return None


def _build_latex_command(engine: str, tex_file: Path) -> list[str]:
    if Path(engine).stem.lower() == "tectonic":
        return [engine, "--keep-logs", "--outdir", str(tex_file.parent), str(tex_file)]
    return [engine, "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(tex_file.parent), str(tex_file)]

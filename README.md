# TCC Pipeline

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-in%20development-orange)](#)

Python pipeline for collecting TNU themes and TRF2 decisions, comparing both sources, recommending a procedural action, generating legal draft documents from a formal template provided by experts, and emitting a semantic RDF/Turtle layer with provenance.

Detailed architecture: [WORKFLOW.md](./WORKFLOW.md)

## What This Project Does

The pipeline was designed to support a legal-document workflow with two outputs produced in parallel:

- a human-readable document layer (`.docx`, `.tex`, `.pdf`);
- a machine-readable semantic layer (`.ttl`) with traceability.

In practice, one execution can:

- collect TNU representative themes;
- collect TRF2 decisions;
- match decisions against themes;
- classify the relationship between both texts;
- infer the proper document action;
- generate legal drafts from a document template;
- compile PDFs when a LaTeX engine is available;
- generate RDF graphs that describe the execution, the inputs, the analysis, and the produced artifacts.

## Core Design

The project follows a "dual-layer" approach:

- LaTeX is the legal presentation layer.
- RDF/Turtle is the semantic and auditable layer.

This means that every generated draft can also be represented as linked semantic artifacts describing:

- which decision was analyzed;
- which TNU theme was associated with it;
- which analysis mode produced the result;
- which action was recommended;
- which `.docx`, `.tex`, `.pdf`, and `.ttl` files were created;
- which activity and agent produced each artifact.

## Semantic Layer

The RDF graph models, at minimum:

- `tcc:LegalDecision` for the TRF2 decision;
- `tcc:TnuTheme` for the TNU theme;
- `tcc:AnalysisResult` for the classification output;
- `tcc:LegalDraft` for the generated draft;
- `prov:Activity` for collection, analysis, and draft generation;
- `prov:Agent` for the local analyzer, Gemini, and the pipeline itself.

This enables questions such as:

- Which decision originated a given draft?
- Which theme was linked to that decision?
- Was the analysis produced locally or by Gemini?
- Which model configuration was used?
- Which files were generated during the execution?

## Requirements

- Python 3.11+
- Dependencies from `requirements.txt`
- Optional for browser-based scraping: `playwright` + Chromium
- Optional for PDF compilation: `tectonic` or `pdflatex`
- Optional for capturing the official decision PDF directly from the public TRF2/JFES page: a local Chrome profile passed with `--trf2-chrome-profile`

## Quick Start

```bash
python -m pip install -r requirements.txt
python -m app.cli.main --mode sample --analysis-mode local --limit 10
```

On Windows, define `GEMINI_API_KEY=...` in the root `.env` file before using Gemini-based analysis.

## Execution Modes

### `sample`

Runs the pipeline against the local offline sample dataset.

```bash
python -m app.cli.main --mode sample --analysis-mode local --limit 10
```

### `live`

Collects data from the official online sources.

```bash
python -m app.cli.main --mode live --analysis-mode local --limit 20 --browser-automation true
```

### `live` with official TRF2 decision PDF capture

Uses a local Chrome profile to access and save the official printable decision PDF from the source site.

```bash
python -m app.cli.main --mode live --analysis-mode local --limit 20 --browser-automation true --trf2-chrome-profile "Profile 1"
```

### `import`

Imports data from an external package or local dataset root.

```bash
python -m app.cli.main --mode import --analysis-mode local --limit 100 --import-root incoming_tcc_pack_20260404/TCC
```

### `gemini`

Runs the same pipeline with Gemini as the analysis engine.

```bash
python -m app.cli.main --mode live --analysis-mode gemini --limit 20 --gemini-model gemini-flash-lite-latest
```

### With PDF compilation enabled

```bash
python -m app.cli.main --mode import --analysis-mode local --limit 20 --import-root incoming_tcc_pack_20260404/TCC --compile-pdf true --latex-engine tools/tectonic/tectonic.exe
```

## Outputs

Each execution writes to a run-specific directory under `outputs/runs/<run-id>/`.

Typical outputs include:

- collected CSV files under `outputs/runs/<run-id>/data/`;
- generated reports under `outputs/runs/<run-id>/reports/`;
- generated drafts under `outputs/runs/<run-id>/documents/`;
- semantic graphs under `outputs/runs/<run-id>/semantic/`;
- copied source PDFs for themes and decisions under `outputs/runs/<run-id>/data/themes/` and `outputs/runs/<run-id>/data/decisions/`.

Common artifacts:

- `data/csv/tnu_temas.csv`
- `data/csv/trf2_decisoes.csv`
- `outputs/reports/analises.csv`
- `outputs/reports/acoes_documentais.csv`
- `outputs/reports/comparados_compat.csv`
- `outputs/runs/<run-id>/documents/*.docx`
- `outputs/runs/<run-id>/documents/*.tex`
- `outputs/runs/<run-id>/documents/*.pdf`
- `outputs/runs/<run-id>/semantic/run-*.ttl`
- `outputs/runs/<run-id>/semantic/<decision-id>-<action>.ttl`

If `data/csv` is not writable, collected CSV files are redirected to `outputs/data/csv`.

## Example Provenance

Simplified example of a generated graph:

```ttl
<https://example.org/tcc/activity/classification-trf2-0002> a prov:Activity, tcc:ClassificationActivity ;
  prov:used <https://example.org/tcc/decision/trf2-0002>, <https://example.org/tcc/theme/309> ;
  prov:generated <https://example.org/tcc/analysis/trf2-0002> ;
  prov:wasAssociatedWith <https://example.org/tcc/agent/local-text-similarity> .

<https://example.org/tcc/activity/draft-generation-trf2-0002> a prov:Activity, tcc:DraftGenerationActivity ;
  prov:used <https://example.org/tcc/analysis/trf2-0002>, <https://example.org/tcc/decision/trf2-0002>, <https://example.org/tcc/theme/309> ;
  prov:generated <https://example.org/tcc/draft/trf2-0002-negar-seguimento> .
```

This structure makes the transformation from legal analysis into an auditable draft explicit.

## Repository Layout

### Root Level

- `README.md`: project overview, setup instructions, execution modes, outputs, and repository map.
- `WORKFLOW.md`: more detailed explanation of the pipeline architecture and execution flow.
- `AGENTS.md`: local orchestration instructions used in this workspace.
- `requirements.txt`: Python dependencies.
- `package.json`: JavaScript tooling metadata used for repository validation commands such as `pnpm tsc` and `pnpm lint`.
- `pnpm-lock.yaml`: exact dependency lockfile for the PNPM-based validation toolchain.
- `pnpm-workspace.yaml`: PNPM workspace configuration.
- `pyrightconfig.json`: static type-checking configuration.
- `.gitignore`: repository ignore rules.
- `.env`: local environment variables such as API keys.
- `rodar-tcc.cmd`: Windows convenience script to run the project.
- `tmp_tnu.html`: local temporary HTML artifact used during debugging or inspection.

### `app/`

Main Python application package.

#### `app/__init__.py`

Marks `app` as a Python package.

#### `app/cli/`

Command-line entrypoints.

- `app/cli/main.py`: primary CLI entrypoint for running the pipeline in `sample`, `live`, `import`, or Gemini-based modes.
- `app/cli/reset_quota.py`: helper command for resetting local Gemini quota state.
- `app/cli/__init__.py`: package marker.

#### `app/core/`

Execution orchestration and configuration.

- `app/core/config.py`: central configuration model, CLI/runtime options, paths, and feature flags.
- `app/core/pipeline.py`: end-to-end orchestration of collection, analysis, artifact materialization, document generation, and RDF generation.
- `app/core/__init__.py`: package marker.

#### `app/domain/`

Project data models and typed structures.

- `app/domain/types.py`: core domain types representing themes, decisions, analyses, and generated artifacts.
- `app/domain/__init__.py`: package marker.

#### `app/services/`

Business logic modules used by the pipeline.

- `app/services/actions.py`: rules that convert analysis results into procedural document actions.
- `app/services/analysis.py`: decision-versus-theme comparison logic and classification routines.
- `app/services/collectors.py`: data collection layer for TNU themes and TRF2 decisions in sample, live, and import modes.
- `app/services/csv.py`: CSV serialization and export helpers.
- `app/services/documents.py`: draft generation, LaTeX rendering, and PDF compilation flow.
- `app/services/document_template.py`: template loading and placeholder replacement logic for the decision template.
- `app/services/gemini.py`: Gemini integration used when the analysis mode is model-based.
- `app/services/gemini_cache.py`: local caching layer for Gemini requests and responses.
- `app/services/gemini_quota.py`: local quota/rate-limit state management for Gemini usage.
- `app/services/semantic.py`: RDF/Turtle generation for execution provenance and per-document semantic artifacts.
- `app/services/source_artifacts.py`: copying, extracting, or materializing source PDFs and related evidence into the run output.
- `app/services/__init__.py`: package marker.

#### `app/utils/`

Low-level reusable helpers.

- `app/utils/fs.py`: filesystem and path helpers.
- `app/utils/hash.py`: hashing helpers for stable identifiers or caching.
- `app/utils/text.py`: text normalization and string-processing utilities.
- `app/utils/__init__.py`: package marker.

### `data/`

Base data directory for collected or imported source material.

- `data/csv/`: canonical CSV dataset files such as `tnu_temas.csv` and `trf2_decisoes.csv`.
- `data/pdf/`: local PDF storage for source material or imported artifacts.

### `templates/`

Document template assets used to generate legal drafts.

- `templates/decision_template.docx`: original template variant.
- `templates/decision_template.tmp.docx`: intermediate working copy created during template editing or extraction.
- `templates/decision_template_v2.docx`: current refined template used by the generation flow.
- `templates/README.md`: notes specific to the template assets.

### `tools/`

Support scripts used for inspection, debugging, template building, and report generation.

- `tools/build_decision_template.py`: utility for preparing or reconstructing the document template.
- `tools/debug_trf2_page.py`: debugging helper for inspecting TRF2 pages.
- `tools/generate_impl_report_docx.py`: generates an implementation report document.
- `tools/inspect_remote.py`: generic remote inspection helper.
- `tools/inspect_trf2_chrome_profile.py`: validates or inspects a local Chrome profile used in TRF2 automation.
- `tools/inspect_trf2_playwright.py`: Playwright-based TRF2 inspection tool.
- `tools/inspect_trf2_print.py`: helper for inspecting printable TRF2 decision views or PDFs.
- `tools/inspect_trf2_process_profile.py`: TRF2 process-specific profile inspection script.
- `tools/inspect_trf2_search_profile.py`: TRF2 search-profile inspection script.
- `tools/inspect_virtus_search.py`: helper for the CJF Virtus search flow used to retrieve official decision PDFs.
- `tools/search_trf2_process_profile.py`: process-focused TRF2 search helper.
- `tools/tectonic/`: bundled LaTeX engine assets used when compiling PDFs locally.

### `outputs/`

Generated artifacts and execution history.

- `outputs/runs/`: canonical per-run outputs. Each run keeps isolated `data`, `reports`, `documents`, and `semantic` folders.
- `outputs/reports/`: shared report/cache area used across runs for support files and caches.
- `outputs/semantic/`: legacy or shared semantic outputs kept outside the run-scoped structure.
- `outputs/documents/`: legacy or shared generated document outputs kept outside the run-scoped structure.
- `outputs/data/`: fallback location when writing to `data/` is not possible.

### `incoming_tcc_pack_20260404/`

Imported offline package with themes, decisions, and PDFs used for robust local runs and dataset expansion.

### `tasks/`

Working notes for task tracking and lessons learned in this workspace.

- `tasks/todo.md`: active checklist for the current task.
- `tasks/lessons.md`: local notes that capture repeated mistakes or coordination lessons.

## Validation

Use the following commands to validate the repository after changes:

```bash
python -m compileall app
corepack pnpm tsc
corepack pnpm lint
python -m app.cli.main --mode sample --analysis-mode local --limit 2
```

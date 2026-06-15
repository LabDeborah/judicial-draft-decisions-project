# Project Workflow

## Overview

This project runs an end-to-end legal-document pipeline that:

1. collects TNU themes;
2. collects TRF2 decisions from 1ª TRES and 2ªTRES;
3. compares decisions against themes;
4. classifies the legal relationship between both texts;
5. derives the procedural action to be taken;
6. generates draft documents from the decision template;
7. emits a semantic RDF/Turtle layer with provenance.

The result is not only a generated legal draft, but also a complete execution trail describing how that draft was produced.

## Dual-Layer Architecture

The pipeline produces two complementary outputs in parallel:

- presentation layer: `.docx`, `.tex`, and optionally `.pdf`;
- semantic layer: `.ttl`.

This separation keeps the legal text readable for humans while preserving traceability, reproducibility, and auditability for the full process.

## End-to-End Execution Flow

```text
[CLI]
python -m app.cli.main --mode live --analysis-mode gemini --limit 10
        |
        v
[app/cli/main.py]
- loads .env
- parses CLI arguments
- builds CliConfig
        |
        v
[app/core/pipeline.py]
1) collect TNU themes --------------------------> [app/services/collectors.py]
2) collect TRF2 decisions ----------------------> [app/services/collectors.py]
3) materialize source artifacts ----------------> [app/services/source_artifacts.py]
4) select decisions for analysis ---------------> [app/core/pipeline.py]
5) analyze decisions ---------------------------> [app/services/analysis.py]
   - local mode: text similarity
   - gemini mode: [app/services/gemini.py]
6) derive document actions ---------------------> [app/services/actions.py]
7) write CSV outputs ---------------------------> [app/services/csv.py]
8) generate drafts (.docx/.tex/.pdf) ----------> [app/services/documents.py]
9) generate RDF/Turtle artifacts --------------> [app/services/semantic.py]
        |
        v
[outputs/runs/<run-id>/]
- data/
- reports/
- documents/
- semantic/
```

## Pipeline Stages

### 1. CLI Entry

`app/cli/main.py` is the main entrypoint.

Its responsibilities are:

- loading environment variables;
- parsing command-line arguments;
- creating the runtime configuration object;
- triggering the pipeline execution.

The CLI delegates most runtime behavior to `CliConfig` in `app/core/config.py`.

## 2. Runtime Configuration

`app/core/config.py` centralizes the operational configuration for the project, including:

- collection mode (`sample`, `live`, `import`);
- analysis mode (`local`, `gemini`);
- collection limits;
- Gemini model and quota settings;
- browser automation settings;
- PDF compilation settings;
- import paths and cache files.

This keeps the pipeline behavior explicit and reproducible.

## 3. Collection Stage

Collection is handled by `app/services/collectors.py`.

Depending on the mode:

- `sample` loads the local offline sample dataset;
- `live` queries the official sources and can use browser automation when needed;
- `import` reads a supplied local dataset package or CSV files.

### TNU collection

The TNU side yields a list of `TnuTheme` records with fields such as:

- theme number;
- legal branch;
- issue submitted for judgment;
- thesis;
- current theme status.

### TRF2 collection

The TRF2 side yields a list of `Trf2Decision` records with fields such as:

- decision identifier;
- process number;
- class;
- subject;
- judging body;
- rapporteur;
- publication and judgment metadata.

## 4. Source Artifact Materialization

After collection, `app/services/source_artifacts.py` copies or extracts source evidence into the current run directory.

This stage is responsible for materializing:

- official or imported theme PDFs;
- official or imported decision PDFs;
- auxiliary `.tex` source representations when available.

These artifacts are stored under:

- `outputs/runs/<run-id>/data/themes/`
- `outputs/runs/<run-id>/data/decisions/`

This makes each run self-contained and easier to audit later.

## 5. Decision Selection for Analysis

Before analysis, `app/core/pipeline.py` ranks the collected decisions and decides which ones should actually be sent to the classifier.

This step exists mainly to:

- avoid wasting Gemini quota on weak candidates;
- prioritize richer and more actionable decisions;
- keep live executions scalable when the collected dataset is larger than the requested analysis capacity.

For Gemini mode, the pipeline also checks the locally tracked quota state before selecting the final subset.

## 6. Analysis Stage

Analysis is coordinated by `app/services/analysis.py`.

Two strategies are available:

- `local`: uses text-based similarity and rule-driven matching;
- `gemini`: sends the decision/theme comparison to Gemini through `app/services/gemini.py`.

The output is a list of `AnalysisOutput` records that include:

- selected TNU theme;
- consonance or dissonance result;
- validity status;
- justification text.

### Gemini operational controls

Gemini mode respects runtime controls such as:

- requests per minute;
- requests per day;
- per-request delay;
- cooldown window after quota stress;
- cache reuse;
- quota state persistence.

Supporting modules:

- `app/services/gemini.py`
- `app/services/gemini_cache.py`
- `app/services/gemini_quota.py`

## 7. Procedural Action Derivation

`app/services/actions.py` converts each analysis result into a document action.

The main action outputs are:

- `SOBRESTAR`
- `NEGAR_SEGUIMENTO`
- `DETERMINAR_ADEQUACAO`
- `SEM_ACAO`

This is the bridge between text analysis and the actual document-generation workflow.

## 8. CSV Export Stage

`app/services/csv.py` serializes the collected and computed data into CSV outputs.

Typical files produced during a run:

- `outputs/runs/<run-id>/data/tnu_temas.csv`
- `outputs/runs/<run-id>/data/trf2_decisoes.csv`
- `outputs/runs/<run-id>/reports/analises.csv`
- `outputs/runs/<run-id>/reports/acoes_documentais.csv`
- `outputs/runs/<run-id>/reports/comparados_compat.csv`

These reports are the easiest place to inspect the pipeline result without reading semantic graphs.

## 9. Document Generation Stage

Draft generation is handled by `app/services/documents.py`.

For each actionable result:

1. the pipeline chooses the proper template scenario;
2. it builds the replacement context;
3. it renders a `.docx` version when the template is available;
4. it renders a `.tex` version;
5. it optionally compiles the `.tex` file into `.pdf`.

Template-specific logic lives in `app/services/document_template.py`.

### Output behavior

Generated documents are stored under:

- `outputs/runs/<run-id>/documents/*.docx`
- `outputs/runs/<run-id>/documents/*.tex`
- `outputs/runs/<run-id>/documents/*.pdf`

If no `.docx` template is available, the service falls back to a simpler legacy LaTeX structure.

### PDF compilation

PDF compilation is optional and controlled by `--compile-pdf true|false`.

The project supports:

- a bundled `tectonic` binary under `tools/tectonic/`;
- a system `tectonic`;
- a system `pdflatex`.

Compilation is parallelized to improve throughput for larger runs.

## 10. Semantic Generation Stage

`app/services/semantic.py` produces RDF/Turtle artifacts for both the full run and each generated draft.

The semantic layer captures:

- execution metadata;
- collection mode and analysis mode;
- input decisions and themes;
- analysis results;
- derived document actions;
- generated document files;
- provenance relationships between all those artifacts.

### Semantic outputs

Each run typically produces:

- one execution graph:
  - `outputs/runs/<run-id>/semantic/run-<timestamp>.ttl`
- one per-document graph for each generated draft:
  - `outputs/runs/<run-id>/semantic/<decision-id>-<action>.ttl`

## Semantic Model

The RDF layer uses a lightweight domain model combined with PROV-O.

Main classes represented in the generated graphs include:

- `ors:Decision`
- `ors:Theme`
- `tcc:AnalysisResult`
- `tcc:LegalDraft`
- `tcc:PipelineRun`
- `tcc:ClassificationActivity`
- `tcc:DraftGenerationActivity`
- `prov:Agent`
- `prov:Activity`
- `prov:Entity`

Namespace prefixes currently emitted by the generator include:

- `prov`
- `dcterms`
- `xsd`
- `ors`
- `tnu`
- `tres`
- `tcc`

## What the Graph Lets You Audit

The generated `.ttl` files allow you to recover:

- which TRF2 decision was analyzed;
- which TNU theme was linked to it;
- which justification was produced;
- which analysis strategy was active;
- which Gemini model was configured, when applicable;
- which `.tex` and `.pdf` files were generated;
- which activity produced each artifact;
- which run a document belongs to.

## Run Directory Structure

The canonical output layout is run-scoped:

```text
outputs/
  runs/
    run-<timestamp>/
      data/
        tnu_temas.csv
        trf2_decisoes.csv
        themes/
        decisions/
      reports/
        analises.csv
        acoes_documentais.csv
        comparados_compat.csv
      documents/
        *.docx
        *.tex
        *.pdf
      semantic/
        run-*.ttl
        <decision-id>-<action>.ttl
```

This structure keeps each execution isolated, reproducible, and easy to archive in the repository.

## Execution Modes

### `--mode sample`

- offline;
- intended for quick testing and reproducible local validation;
- uses the packaged sample dataset.

### `--mode live`

- collects from official online sources;
- can use browser automation for JavaScript-heavy pages;
- can capture official source PDFs when the required access path is available.

### `--mode import`

- loads an external dataset from `--import-root` or explicit CSV files;
- useful for larger offline datasets and robust repository outputs.

## Analysis Modes

### `--analysis-mode local`

- does not use an external LLM API;
- relies on local similarity and rule-based heuristics.

### `--analysis-mode gemini`

- uses Gemini through the configured API key;
- obeys cache, quota, delay, and daily request controls.

## Diagnostic Checklist

When verifying a run:

1. Confirm that the CLI reports the pipeline completed successfully.
2. Check `outputs/runs/<run-id>/reports/analises.csv`.
3. Check `outputs/runs/<run-id>/reports/acoes_documentais.csv`.
4. Check `outputs/runs/<run-id>/data/trf2_decisoes.csv`.
5. Check whether source PDFs were materialized under `data/themes/` and `data/decisions/`.
6. Check at least one generated document under `documents/`.
7. Check the execution graph under `semantic/run-*.ttl`.
8. Check at least one per-document `.ttl` graph.

If Gemini mode produced fewer analyses than expected, inspect the quota state and cache behavior before assuming the collector failed.

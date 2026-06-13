# TCC Pipeline

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)](#)

Pipeline em Python para:
- coletar dados TNU e TRF2 (`sample`, `live` ou `import`);
- classificar decisoes por tema;
- definir acao recursal;
- gerar minutas a partir de template documental (`.docx` -> `.tex` -> `.pdf`);
- gerar uma camada semantica paralela em RDF/Turtle com provenance em PROV-O.

Arquitetura detalhada: [WORKFLOW.md](./WORKFLOW.md)

## Ideia central implementada

Com base na proposta do professor Jean, o projeto agora segue a estrategia de "dupla camada":

- LaTeX como camada de apresentacao juridica.
- RDF/Turtle como camada semantica e auditavel.

Na pratica, a pipeline passa a produzir:

- artefatos humanos: `.tex` e `.pdf`;
- artefatos semanticos: `.ttl` por execucao e `.ttl` por minuta.

O desenho adotado foi o mais direto e robusto sugerido no PDF:

- RDF paralelo ao LaTeX;
- PROV-O para modelar atividades, entidades e agentes;
- o resultado de analise e a geracao da minuta ficam explicitamente rastreaveis.

## O que a camada semantica modela

O grafo RDF minimo cobre:

- `tcc:LegalDecision` para a decisao do TRF2;
- `tcc:TnuTheme` para o tema da TNU;
- `tcc:AnalysisResult` para a classificacao produzida;
- `tcc:LegalDraft` para a minuta gerada;
- `prov:Activity` para classificacao e geracao da minuta;
- `prov:Agent` para o classificador local ou modelo Gemini e para a pipeline.

Exemplos de perguntas que os `.ttl` passam a responder:

- qual decisao originou a minuta;
- qual tema TNU foi associado;
- qual estrategia de analise foi usada (`local` ou `gemini`);
- qual modelo Gemini estava configurado;
- quais arquivos `.tex` e `.pdf` foram produzidos;
- qual atividade gerou cada artefato.

## Requisitos

- Python 3.11+
- Dependencias de `requirements.txt`
- Opcional para scraping JS pesado: `playwright` + Chromium
- Opcional para PDF: `tectonic` ou `pdflatex`
- Opcional para capturar o PDF oficial da pagina publica do acordao no TRF2/JFES: perfil local do Chrome informado em `--trf2-chrome-profile`

## Quickstart

```bash
python -m pip install -r requirements.txt
python -m app.cli.main --mode sample --analysis-mode local --limit 10
```

## Modos de execucao

Modo `sample`:

```bash
python -m app.cli.main --mode sample --analysis-mode local --limit 10
```

Modo `live`:

```bash
python -m app.cli.main --mode live --analysis-mode local --limit 20 --browser-automation true
```

Modo `live` com perfil local do Chrome para capturar o PDF oficial da pagina publica da decisao:

```bash
python -m app.cli.main --mode live --analysis-mode local --limit 20 --browser-automation true --trf2-chrome-profile "Profile 1"
```

Modo `import`:

```bash
python -m app.cli.main --mode import --analysis-mode local --limit 100 --import-root incoming_tcc_pack_20260404/TCC
```

Modo `gemini`:

```bash
python -m app.cli.main --mode live --analysis-mode gemini --limit 20 --gemini-model gemini-flash-lite-latest
```

Com compilacao de PDF:

```bash
python -m app.cli.main --mode import --analysis-mode local --limit 20 --import-root incoming_tcc_pack_20260404/TCC --compile-pdf true --latex-engine tools/tectonic/tectonic.exe
```

No Windows, defina `GEMINI_API_KEY=...` no arquivo `.env` da raiz.

## Saidas

Dados e relatorios:

- `data/csv/tnu_temas.csv`
- `data/csv/trf2_decisoes.csv`
- `outputs/reports/analises.csv`
- `outputs/reports/acoes_documentais.csv`
- `outputs/reports/comparados_compat.csv`

Documentos:

- `templates/decision_template_v2.docx`
- `outputs/documents/*.tex`
- `outputs/documents/*.docx`
- `outputs/documents/*.pdf`

Camada semantica:

- `outputs/semantic/run-*.ttl`
- `outputs/semantic/<decisionId>-<action>.ttl`

Se `data/csv` nao estiver gravavel, os CSVs de dados sao redirecionados para `outputs/data/csv`.

## Exemplo de provenance

Trecho simplificado de um grafo gerado:

```ttl
<https://example.org/tcc/activity/classification-trf2-0002> a prov:Activity, tcc:ClassificationActivity ;
  prov:used <https://example.org/tcc/decision/trf2-0002>, <https://example.org/tcc/theme/309> ;
  prov:generated <https://example.org/tcc/analysis/trf2-0002> ;
  prov:wasAssociatedWith <https://example.org/tcc/agent/local-text-similarity> .

<https://example.org/tcc/activity/draft-generation-trf2-0002> a prov:Activity, tcc:DraftGenerationActivity ;
  prov:used <https://example.org/tcc/analysis/trf2-0002>, <https://example.org/tcc/decision/trf2-0002>, <https://example.org/tcc/theme/309> ;
  prov:generated <https://example.org/tcc/draft/trf2-0002-negar-seguimento> .
```

Esse modelo deixa explicito como um resultado de classificacao vira uma minuta juridica auditavel.

## Estrutura do projeto

```text
app/
  cli/         # entrada e comandos
  core/        # config e pipeline
  domain/      # modelos de dados
  services/    # coletores, analise, Gemini, documentos e semantic web
  utils/       # filesystem, hash, normalizacao de texto
```

## Validacao

```bash
python -m compileall app
corepack pnpm tsc
corepack pnpm lint
python -m app.cli.main --mode sample --analysis-mode local --limit 2
```

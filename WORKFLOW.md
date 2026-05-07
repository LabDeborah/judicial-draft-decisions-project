# Workflow do Projeto

## Visao geral

O projeto executa uma pipeline para:

1. Coletar dados da TNU e do TRF2.
2. Classificar decisoes por tema (local ou Gemini).
3. Definir acao recursal.
4. Gerar relatorios CSV e minutas em LaTeX.

## Fluxo de execucao

```text
[CLI]
python -m app.cli.main --mode live --analysis-mode gemini --limit 10
        |
        v
[app/cli/main.py]
- carrega .env
- parseia args (app/core/config.py)
        |
        v
[app/core/pipeline.py]
1) coleta TNU --------------------> [app/services/collectors.py]
   - live: paginacao TNU + parse de tabelas HTML
   - saida: TnuTheme[]
2) coleta TRF2 -------------------> [app/services/collectors.py]
   - live: extrai blocos por numero de processo
   - saida: Trf2Decision[]
3) analisa decisoes -------------> [app/services/analysis.py]
   - local: similaridade textual
   - gemini: chama [app/services/gemini.py]
     com:
     - quota diaria [app/services/gemini_quota.py]
     - cache [app/services/gemini_cache.py]
     - fallback seguro (INVALIDA) em erro/quota
   - saida: AnalysisOutput[]
4) define acao ------------------> [app/services/actions.py]
   - SOBRESTAR / NEGAR_SEGUIMENTO / DETERMINAR_ADEQUACAO / SEM_ACAO
   - saida: DocumentDecision[]
5) grava CSVs -------------------> [app/services/csv.py] + [app/utils/fs.py]
6) gera minutas .tex -----------> [app/services/documents.py]
   - compilacao automatica para .pdf quando houver `tectonic`/`pdflatex`
        |
        v
[Saidas]
- data/csv/tnu_temas.csv
- data/csv/trf2_decisoes.csv
- outputs/reports/analises.csv
- outputs/reports/acoes_documentais.csv
- outputs/reports/comparados_compat.csv
- outputs/documents/*.tex
- outputs/reports/gemini_quota_state.json
- outputs/reports/gemini_cache.json

Observacao:
- quando `data/csv` nao estiver gravavel, a pipeline redireciona automaticamente os CSVs de dados para `outputs/data/csv`.
```

## Modos de analise

- `--analysis-mode local`
  - Nao usa API externa.
  - Classifica por semelhanca de texto.

- `--analysis-mode gemini`
  - Usa a Gemini via API.
  - Respeita limites operacionais configurados:
    - `--gemini-requests-per-minute` (default: 15)
    - `--gemini-requests-per-day` (default: 500)
    - `--gemini-delay-ms` (default: 1200)
    - `--gemini-cooldown-ms` (default: 15000)
    - `--gemini-429-threshold` (default: 2)
    - `--gemini-max-quota-errors` (default: 2)

- Browser automation para coleta live:
  - `--browser-automation true|false` (default: `true`)
  - se `true`, tenta Playwright como fallback quando parse HTML padrao falhar

- Modo de importacao de dataset local:
  - `--mode import`
  - `--import-root <pasta>` para usar `tnu/temas-tnu.csv` e `trf2/decisoes.csv`
  - ou `--tnu-csv-file <arquivo>` e `--trf2-csv-file <arquivo>`

- Compilacao de minutas:
  - `--compile-pdf true|false` (default: `true`)
  - `--latex-engine <engine>` (opcional, ex.: `tectonic` ou `pdflatex`)

## Cache e quota

- Cache de respostas validas:
  - Arquivo default: `outputs/reports/gemini_cache.json`
  - Quando existe resposta valida para a mesma decisao + base de temas, o sistema reutiliza.

- Estado de quota diaria:
  - Arquivo default: `outputs/reports/gemini_quota_state.json`
  - Guarda `date` e `requests`.
  - Reset manual:
    - `python -m app.cli.reset_quota`

## Comandos principais

- Rodar com defaults de Gemini:
  - `python -m app.cli.main --mode live --analysis-mode gemini --gemini-model gemini-flash-lite-latest --limit 20 --gemini-requests-per-minute 15 --gemini-requests-per-day 500`

- Rodar customizado:
  - `python -m app.cli.main --mode live --analysis-mode gemini --limit 10 --browser-automation true --compile-pdf true`

- Rodar somente local:
  - `python -m app.cli.main --mode live --analysis-mode local --limit 10`

- Rodar com importacao local:
  - `python -m app.cli.main --mode import --analysis-mode local --limit 100 --import-root incoming_tcc_pack_20260404/TCC`

- Resetar quota local:
  - `python -m app.cli.reset_quota`

## Checklist de diagnostico rapido

1. Verificar se `Pipeline concluida` apareceu no terminal.
2. Conferir `outputs/reports/analises.csv`.
3. Conferir `outputs/reports/acoes_documentais.csv`.
4. Conferir `outputs/reports/gemini_quota_state.json` para consumo diario.
5. Se houver muitos `HTTP 429`:
   - reduzir `--limit`
   - aumentar `--gemini-delay-ms`
   - rodar com `local` temporariamente

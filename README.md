# TCC Pipeline

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)](#)

Pipeline em Python para:
- coletar dados TNU e TRF2 (`sample`, `live` ou `import`),
- classificar decisões por tema,
- definir ação recursal,
- gerar relatórios CSV,
- gerar minutas em `.tex` e, opcionalmente, `.pdf`.

Arquitetura detalhada: [WORKFLOW.md](./WORKFLOW.md)
Guia de fluxo operacional: [WORKFLOW.md](./WORKFLOW.md)

## Requisitos
- Python 3.11+
- Dependências de `requirements.txt`
- Opcional (scraping JS pesado): `playwright` + Chromium
- Opcional (PDF): `tectonic` ou `pdflatex`

## Quickstart (2 minutos)
```bash
python -m pip install -r requirements.txt
python -m app.cli.main --mode sample --analysis-mode local --limit 10
```

## Modos de execução

Modo `sample` (sem dependência de rede):
```bash
python -m app.cli.main --mode sample --analysis-mode local --limit 10
```

Modo `live`:
```bash
python -m app.cli.main --mode live --analysis-mode local --limit 20 --browser-automation true
```

Modo `import` (compatível com pacote externo):
```bash
python -m app.cli.main --mode import --analysis-mode local --limit 100 --import-root incoming_tcc_pack_20260404/TCC
```

Com Gemini:
```bash
python -m app.cli.main --mode live --analysis-mode gemini --limit 20 --gemini-model gemini-flash-lite-latest
```

Com compilação de PDF:
```bash
python -m app.cli.main --mode import --analysis-mode local --limit 20 --import-root incoming_tcc_pack_20260404/TCC --compile-pdf true --latex-engine tools/tectonic/tectonic.exe
```

No Windows, defina `GEMINI_API_KEY=...` no arquivo `.env` da raiz.

## Scripts úteis
```bash
.\rodar-tcc.cmd
corepack pnpm rodar-tcc
corepack pnpm rodar-tcc:custom -- --mode sample --analysis-mode local --limit 10
corepack pnpm reset-quota
```

## Saídas
- `data/csv/tnu_temas.csv`
- `data/csv/trf2_decisoes.csv`
- `outputs/reports/analises.csv`
- `outputs/reports/acoes_documentais.csv`
- `outputs/reports/comparados_compat.csv`
- `outputs/documents/*.tex`
- `outputs/documents/*.pdf` (quando habilitado)

Se `data/csv` não estiver gravável, os CSVs de dados são redirecionados automaticamente para `outputs/data/csv`.

## Estrutura do projeto
```text
app/
  cli/         # entrada e comandos
  core/        # config e pipeline
  domain/      # modelos de dados
  services/    # coletores, análise, Gemini, documentos
  utils/       # filesystem, hash, normalização de texto
```

## Checklist de validação
```bash
python -m compileall app
corepack pnpm tsc
corepack pnpm lint
python -m app.cli.main --mode sample --analysis-mode local --limit 2
```

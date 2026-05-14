# Workflow do Projeto

## Visao geral

O projeto executa uma pipeline para:

1. Coletar dados da TNU e do TRF2.
2. Classificar decisoes por tema.
3. Definir acao recursal.
4. Gerar minutas em LaTeX.
5. Gerar uma camada semantica em RDF/Turtle com provenance em PROV-O.

## Arquitetura de dupla camada

O pipeline agora separa dois produtos complementares:

- camada de apresentacao: `.tex` e `.pdf`;
- camada semantica: `.ttl`.

Essa separacao permite manter o documento juridico legivel para humanos, sem abrir mao de rastreabilidade, auditabilidade e reprodutibilidade do processo de geracao.

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
   - saida: AnalysisOutput[]
4) define acao ------------------> [app/services/actions.py]
   - SOBRESTAR / NEGAR_SEGUIMENTO / DETERMINAR_ADEQUACAO / SEM_ACAO
   - saida: DocumentDecision[]
5) grava CSVs -------------------> [app/services/csv.py]
6) gera minutas .tex/.pdf ------> [app/services/documents.py]
7) gera grafos RDF/PROV-O ------> [app/services/semantic.py]
   - grafo consolidado por execucao
   - grafo individual por minuta
        |
        v
[Saidas]
- data/csv/tnu_temas.csv
- data/csv/trf2_decisoes.csv
- outputs/reports/analises.csv
- outputs/reports/acoes_documentais.csv
- outputs/reports/comparados_compat.csv
- outputs/documents/*.tex
- outputs/documents/*.pdf
- outputs/semantic/run-*.ttl
- outputs/semantic/*.ttl
```

## Modelagem semantica

O RDF gerado segue uma ontologia minima do dominio:

- `tcc:LegalDecision`
- `tcc:TnuTheme`
- `tcc:AnalysisResult`
- `tcc:LegalDraft`
- `tcc:PipelineRun`
- `tcc:ClassificationActivity`
- `tcc:DraftGenerationActivity`

Com PROV-O, a pipeline explicita:

- `prov:Entity` para decisoes, temas, analises e minutas;
- `prov:Activity` para classificacao e geracao;
- `prov:Agent` para o classificador local, Gemini e a propria pipeline.

## O que o grafo permite auditar

Os arquivos `.ttl` permitem recuperar:

- qual decisao foi usada na classificacao;
- qual tema TNU foi associado;
- qual justificativa foi registrada na analise;
- qual modo de analise estava ativo;
- qual modelo Gemini estava configurado;
- quais arquivos `.tex` e `.pdf` foram produzidos;
- quais atividades geraram cada resultado.

## Modos de analise

- `--analysis-mode local`
  - Nao usa API externa.
  - Classifica por semelhanca de texto.

- `--analysis-mode gemini`
  - Usa a Gemini via API.
  - Respeita:
    - `--gemini-requests-per-minute`
    - `--gemini-requests-per-day`
    - `--gemini-delay-ms`
    - `--gemini-cooldown-ms`
    - `--gemini-429-threshold`
    - `--gemini-max-quota-errors`

## Modos de coleta e geracao

- `--mode sample`
  - sem rede; ideal para verificacao rapida;

- `--mode live`
  - coleta em fontes reais;
  - pode usar `--browser-automation true` como fallback para paginas com JS pesado;

- `--mode import`
  - usa datasets locais via `--import-root` ou arquivos CSV explicitos.

- `--compile-pdf true|false`
  - controla a compilacao automatica de `.tex` para `.pdf`.

## Checklist de diagnostico

1. Confirmar a mensagem `Pipeline concluida`.
2. Conferir `outputs/reports/analises.csv`.
3. Conferir `outputs/reports/acoes_documentais.csv`.
4. Conferir `outputs/semantic/run-*.ttl`.
5. Conferir ao menos um `outputs/semantic/<decision>-<action>.ttl`.
6. Se houver erro Gemini, validar se a saida foi marcada como `INVALIDA` no fallback seguro.

# Template documental

Arquivos:
- `decisions_template.docx`: The decision templates were provided by legal domain experts.

Cenarios estruturais:
- `adequacao_dissonancia`: paragrafos 1-13
- `sobrestamento_pendente_julgamento`: paragrafos 15-20
- `sobrestamento_sem_transito`: paragrafos 21-30
- `nego_seguimento_pos_sobrestamento`: paragrafos 32-43
- `nego_seguimento_transitado`: paragrafos 45-55

Placeholders principais:
- `{{decision_process_number}}`
- `{{theme_number}}`
- `{{theme_process_number}}`
- `{{theme_affectation_date}}`
- `{{theme_judgment_date}}`
- `{{theme_transit_date}}`
- `{{theme_question_quote}}`
- `{{theme_thesis_quote}}`
- `{{theme_judgment_reference}}`
- `{{theme_reference_label}}`
- `{{decision_excerpt_quote}}`
- `{{theme_alignment_phrase}}`

Comportamento adicional:
- os documentos gerados passam a incluir automaticamente, no topo, a linha `Processo n°: <numero do processo da decisao>`, usando `Trf2Decision.numeroProcesso`.

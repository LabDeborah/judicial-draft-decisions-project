from __future__ import annotations

import csv
import json
import math
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.domain.types import CollectionMode, TnuTheme, Trf2Decision
from app.utils.text import normalize_for_matching, normalize_text

TNU_URL = (
    "https://www.cjf.jus.br/cjf/corregedoria-da-justica-federal/"
    "turma-nacional-de-uniformizacao/temas-representativos"
)
TRF2_JURISPRUDENCIA_URL = "https://jurisprudencia.trf2.jus.br/"
TRF2_JURISPRUDENCIA_RESULTS_URL = (
    "https://eproc.trf2.jus.br/eproc/externo_controlador.php?acao=jurisprudencia@jurisprudencia/listar_resultados"
)
TRF2_JURISPRUDENCIA_PAGINATION_URL = (
    "https://eproc.trf2.jus.br/eproc/externo_controlador.php?acao=jurisprudencia@jurisprudencia/ajax_paginar_resultado"
)
TRF2_TURMAS_RECURSAIS_ES_ORGAOS = {
    "1ª Turma Recursal do Espírito Santo",
    "2ª Turma Recursal do Espírito Santo",
}
TRF2_TURMAS_RECURSAIS_ES_ORGAOS_NORMALIZED = {
    normalize_for_matching(item) for item in TRF2_TURMAS_RECURSAIS_ES_ORGAOS
}
TRF2_TURMAS_RECURSAIS_ES_UF = "ES"
TRF2_TURMAS_RECURSAIS_START_DATE = "01/01/2025"
TRF2_TURMAS_RECURSAIS_END_DATE = "05/06/2026"
TRF2_TURMAS_RECURSAIS_TARGET_YEAR = "2026"
TRF2_MAX_RESULTS_PER_PAGE = 100
TRF2_MIN_DOCUMENTABLE_RICHNESS = 80
TRF2_DETAIL_REQUEST_DELAY_S = 0.35
TRF2_DETAIL_MIN_HTML_LEN = 2500
TRF2_MAX_SEARCH_QUERIES = 24
TRF2_DETAIL_CACHE_FILE = "outputs/reports/trf2_detail_cache.json"
SAMPLE_IMPORT_ROOT = Path("incoming_tcc_pack_20260404/TCC")
SAMPLE_TNU_ZIP = SAMPLE_IMPORT_ROOT / "tnu-20260327T210944Z-3-001.zip"
SAMPLE_TRF2_ZIP = SAMPLE_IMPORT_ROOT / "trf2-20260327T210759Z-3-001.zip"
TRF2_BAD_DETAIL_MARKERS = (
    "consulta processual - busca de processo",
    ":: eproc - consulta processual",
    "ir para conteúdo",
    "entrar no sistema",
    "cadastrar advogado",
    "cadastrar jus postulandi",
)
_TRF2_QUERY_STOPWORDS = {
    "para",
    "como",
    "tema",
    "base",
    "calculo",
    "sobre",
    "firmada",
    "questao",
    "direito",
    "ramo",
    "julgamento",
    "julgada",
    "julgado",
    "submetida",
    "disponivel",
    "nao",
    "comum",
    "devido",
    "integral",
    "federal",
    "federais",
    "publico",
    "publicos",
    "quando",
    "apos",
    "acima",
    "menor",
    "anos",
    "pela",
    "pelos",
    "pelas",
    "entre",
    "servidor",
    "servidores",
}


def collect_tnu_themes(
    mode: CollectionMode,
    limit: int,
    browser_automation: bool = True,
    import_csv_file: str | None = None,
) -> list[TnuTheme]:
    if mode == "sample":
        return _sample_themes()[:limit]
    if mode == "import":
        return _collect_tnu_themes_import(import_csv_file, limit)
    parsed = _collect_tnu_themes_live(limit, browser_automation=browser_automation)
    if parsed:
        return parsed
    print(
        "Aviso: coleta live da TNU indisponivel; usando dados sample como fallback.",
        file=sys.stderr,
    )
    return _sample_themes()[:limit]


def collect_trf2_decisions(
    mode: CollectionMode,
    limit: int,
    browser_automation: bool = True,
    import_csv_file: str | None = None,
    themes: list[TnuTheme] | None = None,
) -> list[Trf2Decision]:
    if mode == "sample":
        return _sample_decisions()[:limit]
    if mode == "import":
        return _collect_trf2_decisions_import(import_csv_file, limit)
    parsed = _collect_trf2_decisions_live(limit, themes=themes)
    if parsed:
        return parsed
    print(
        "Aviso: coleta live do TRF2 indisponivel; usando dados sample como fallback.",
        file=sys.stderr,
    )
    return _sample_decisions()[:limit]


def _fetch_html(url: str) -> str:
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
        except requests.RequestException:
            if attempt == 3:
                return ""
            continue
        if resp.ok:
            resp.encoding = resp.encoding or "utf-8"
            return resp.text
        if attempt == 3:
            return ""
    return ""


def _parse_tnu_themes_from_html(html: str, limit: int) -> list[TnuTheme]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[TnuTheme] = []
    tables = soup.select("table.auto-table.tablesorter.tg")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue
        header_cells = [_clean(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
        if len(header_cells) < 6 or _clean(header_cells[0]) != "Tema":
            continue

        tema_numero = header_cells[1] if len(header_cells) > 1 else ""
        if not re.match(r"^\d{1,4}$", tema_numero):
            continue

        situacao_tema = header_cells[3] if len(header_cells) > 3 else "DESCONHECIDA"
        ramo_direito = header_cells[5] if len(header_cells) > 5 else "NAO_INFORMADO"
        q_cells = rows[1].find_all("td") if len(rows) > 1 else []
        t_cells = rows[2].find_all("td") if len(rows) > 2 else []
        questao_submetida = _clean(q_cells[1].get_text(" ", strip=True)) if len(q_cells) > 1 else "NAO_INFORMADO"
        tese_firmada = _clean(t_cells[1].get_text(" ", strip=True)) if len(t_cells) > 1 else ""

        process_cells = rows[4].find_all("td") if len(rows) > 4 else []
        numero_processo = _cell_text(process_cells, 0)
        data_decisao_afetacao = _cell_text(process_cells, 1)
        relator = _cell_text(process_cells, 2)
        data_julgamento = _cell_text(process_cells, 3)
        data_publicacao = _cell_text(process_cells, 4)
        transito_julgado = _cell_text(process_cells, 5)
        pdf_path = _cell_link(process_cells, 1) or _cell_link(process_cells, 4) or ""

        results.append(
            TnuTheme(
                temaNumero=tema_numero,
                situacaoTema=situacao_tema,
                ramoDireito=ramo_direito,
                questaoSubmetidaJulgamento=questao_submetida,
                teseFirmada=tese_firmada,
                numeroProcesso=numero_processo,
                dataDecisaoAfetacao=data_decisao_afetacao,
                relator=relator,
                dataJulgamento=data_julgamento,
                dataPublicacaoAcordao=data_publicacao,
                transitoJulgado=transito_julgado,
                pdfPath=pdf_path,
            )
        )
        if len(results) >= limit:
            break

    return results


def _collect_tnu_themes_live(limit: int, *, browser_automation: bool) -> list[TnuTheme]:
    batch_size = 40
    start = 0
    results: list[TnuTheme] = []
    seen: set[str] = set()
    while len(results) < limit:
        page_url = f"{TNU_URL}?b_size:int={batch_size}&b_start:int={start}"
        html = _fetch_html(page_url)
        page_items = _parse_tnu_themes_from_html(html, limit)
        if not page_items and browser_automation:
            dynamic_html = _fetch_html_with_browser(page_url)
            if dynamic_html:
                page_items = _parse_tnu_themes_from_html(dynamic_html, limit)
        if not page_items:
            break
        added = 0
        for item in page_items:
            if item.temaNumero in seen:
                continue
            seen.add(item.temaNumero)
            results.append(item)
            added += 1
            if len(results) >= limit:
                break
        if added == 0:
            break
        start += batch_size
    return results[:limit]


def _collect_tnu_themes_import(csv_path: str | None, limit: int) -> list[TnuTheme]:
    if not csv_path:
        return _sample_themes()[:limit]
    rows = _read_csv_rows(csv_path)
    out: list[TnuTheme] = []
    for row in rows:
        out.append(
            TnuTheme(
                temaNumero=_get_field(row, "tema"),
                situacaoTema=_get_field(row, "situacao do tema"),
                ramoDireito=_get_field(row, "ramo do direito"),
                questaoSubmetidaJulgamento=_get_field(row, "questao submetida a julgamento"),
                teseFirmada=_get_field(row, "tese firmada"),
                numeroProcesso=_get_field(row, "processo"),
                dataDecisaoAfetacao=_get_field(row, "decisao de afetacao"),
                relator=_get_field(row, "relator (a)", "relator"),
                dataJulgamento=_get_field(row, "julgado em"),
                dataPublicacaoAcordao=_get_field(row, "acordao publicado em"),
                transitoJulgado=_get_field(row, "transito em julgado"),
                pdfPath=_resolve_relative_file(csv_path, _get_field(row, "inteiro teor decisao de afetacao")),
            )
        )
        if len(out) >= limit:
            break
    return out


def _collect_trf2_decisions_import(csv_path: str | None, limit: int) -> list[Trf2Decision]:
    if not csv_path:
        return _sample_decisions()[:limit]
    rows = _read_csv_rows(csv_path)
    out: list[Trf2Decision] = []
    for row in rows:
        decision_id = _get_field(row, "id")
        out.append(
            Trf2Decision(
                decisionId=decision_id or f"TRF2-IMPORT-{len(out) + 1}",
                classe=_get_field(row, "classe"),
                tipoJulgamento=_get_field(row, "tipo julgamento"),
                assuntos=_get_field(row, "assunto(s)", "assuntos"),
                competencia=_get_field(row, "competencia"),
                relatorOriginario=_get_field(row, "relator originario"),
                dataAutuacao=_get_field(row, "data autuacao"),
                dataJulgamento=_get_field(row, "data julgamento"),
                numeroProcesso=_get_field(row, "numero processo"),
                inteiroTeorPath=_resolve_relative_file(csv_path, _get_field(row, "pdf inteiro teor")),
            )
        )
        if len(out) >= limit:
            break
    return out


def _collect_trf2_decisions_live(limit: int, *, themes: list[TnuTheme] | None = None) -> list[Trf2Decision]:
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    search_queries = _build_trf2_search_queries(themes)
    page_size = min(TRF2_MAX_RESULTS_PER_PAGE, max(10, limit))
    max_pages_per_query = _estimate_trf2_pages_per_query(limit)
    detail_cache = _load_trf2_detail_cache()
    for _attempt in range(1, 4):
        try:
            with requests.Session() as session:
                landing = session.get(TRF2_JURISPRUDENCIA_URL, timeout=30, headers=headers, allow_redirects=True)
                if not landing.ok:
                    continue
                buckets: list[list[tuple[int, Trf2Decision]]] = []
                seen: set[str] = set()
                for query in search_queries:
                    payload = {
                        "selOrigem[]": "3",
                        "selTipoDocumento[]": "1",
                        "rdoCampo": "I",
                        "selTamanhoPagina": str(page_size),
                        "dtDecisaoInicio": TRF2_TURMAS_RECURSAIS_START_DATE,
                        "dtDecisaoFim": TRF2_TURMAS_RECURSAIS_END_DATE,
                        "dtPublicacaoInicio": TRF2_TURMAS_RECURSAIS_START_DATE,
                        "dtPublicacaoFim": TRF2_TURMAS_RECURSAIS_END_DATE,
                        "txtPesquisa": query,
                    }
                    try:
                        response = session.post(
                            TRF2_JURISPRUDENCIA_RESULTS_URL,
                            data=payload,
                            timeout=30,
                            headers=headers,
                        )
                    except requests.RequestException:
                        continue
                    if not response.ok:
                        continue
                    response.encoding = response.encoding or "iso-8859-1"
                    page_payloads = [(response.text, 1)]
                    total_pages = _extract_trf2_total_pages(response.text)
                    last_page = min(total_pages or 1, max_pages_per_query)
                    for page_number in range(2, last_page + 1):
                        paginated_html = _fetch_trf2_results_page(
                            session,
                            headers,
                            payload,
                            page_number=page_number,
                        )
                        if not paginated_html:
                            break
                        page_payloads.append((paginated_html, page_number))
                    bucket: list[tuple[int, Trf2Decision]] = []
                    query_seen: set[str] = set()
                    for page_html, _page_number in page_payloads:
                        parsed = _parse_trf2_decisions_from_results_html(
                            page_html,
                            max(page_size, limit),
                            session=session,
                            headers=headers,
                            detail_cache=detail_cache,
                        )
                        if not parsed:
                            continue
                        for decision in parsed:
                            dedupe_key = decision.numeroProcesso or decision.inteiroTeorPath or decision.decisionId
                            if dedupe_key in seen or dedupe_key in query_seen:
                                continue
                            score = _score_trf2_decision_against_themes(decision, themes)
                            query_seen.add(dedupe_key)
                            seen.add(dedupe_key)
                            bucket.append((score, decision))
                    if not bucket:
                        continue
                    bucket.sort(
                        key=lambda item: (
                            _score_trf2_decision_documentability(item[1], themes),
                            item[0],
                            _trf2_decision_text_richness(item[1]),
                            len(item[1].assuntos or ""),
                            item[1].dataJulgamento or "",
                        ),
                        reverse=True,
                    )
                    buckets.append(bucket)
                diversified = _select_diverse_trf2_decisions(buckets, limit)
                if diversified:
                    diversified = _prefer_documentable_trf2_decisions(diversified, limit, themes)
                    diversified.sort(
                        key=lambda decision: (
                            _score_trf2_decision_documentability(decision, themes),
                            _trf2_decision_text_richness(decision),
                            len(decision.assuntos or ""),
                            decision.dataJulgamento or "",
                        ),
                        reverse=True,
                    )
                    final_decisions: list[Trf2Decision] = []
                    for index, decision in enumerate(diversified, start=1):
                        decision.decisionId = f"TRF2-LIVE-{index}"
                        final_decisions.append(decision)
                    _save_trf2_detail_cache(detail_cache)
                    return final_decisions
        except requests.RequestException:
            continue
    _save_trf2_detail_cache(detail_cache)
    return []


def _estimate_trf2_pages_per_query(limit: int) -> int:
    base_pages = max(1, math.ceil(limit / TRF2_MAX_RESULTS_PER_PAGE))
    return min(20, base_pages + 6)


def _extract_trf2_total_pages(html: str) -> int:
    match = re.search(r'id="hdnTotalPaginas"[^>]*value="(\d+)"', html, flags=re.IGNORECASE)
    return int(match.group(1)) if match else 1


def _fetch_trf2_results_page(
    session: requests.Session,
    headers: dict[str, str],
    base_payload: dict[str, str],
    *,
    page_number: int,
) -> str:
    payload = dict(base_payload)
    payload["hdnPaginaAtual"] = str(page_number)
    try:
        response = session.post(
            TRF2_JURISPRUDENCIA_PAGINATION_URL,
            data=payload,
            timeout=30,
            headers=headers,
        )
    except requests.RequestException:
        return ""
    if not response.ok:
        return ""
    response.encoding = response.encoding or "iso-8859-1"
    return response.text


def _build_trf2_search_queries(themes: list[TnuTheme] | None) -> list[str]:
    if not themes:
        return [""]
    queries: list[str] = []
    seen: set[str] = set()
    for theme in themes:
        for query in _theme_to_search_queries(theme):
            if not query or query in seen:
                continue
            seen.add(query)
            queries.append(query)
            if len(queries) >= TRF2_MAX_SEARCH_QUERIES - 4:
                break
        if len(queries) >= TRF2_MAX_SEARCH_QUERIES - 4:
            break
    for query in _build_trf2_domain_queries(themes):
        if query in seen:
            continue
        seen.add(query)
        queries.append(query)
        if len(queries) >= TRF2_MAX_SEARCH_QUERIES:
            break
    if "" not in seen:
        queries.append("")
    return queries or [""]


def _theme_to_search_queries(theme: TnuTheme) -> list[str]:
    source = " ".join(
        part
        for part in [
            theme.questaoSubmetidaJulgamento,
            theme.teseFirmada,
            theme.ramoDireito,
        ]
        if part
    )
    tokens: list[str] = []
    for raw in re.split(r"[^a-z0-9]+", normalize_for_matching(source)):
        if len(raw) < 4 or raw in _TRF2_QUERY_STOPWORDS:
            continue
        if raw in tokens:
            continue
        tokens.append(raw)
        if len(tokens) >= 6:
            break
    queries: list[str] = []
    if len(tokens) >= 3:
        queries.append(" ".join(tokens[:3]))
    if len(tokens) >= 5:
        queries.append(" ".join(tokens[2:5]))
    if len(tokens) >= 2:
        queries.append(" ".join(tokens[:2]))
    ramo = normalize_for_matching(theme.ramoDireito)
    if ramo and len(tokens) >= 2:
        queries.append(f"{ramo} {' '.join(tokens[:2])}".strip())
    return [query.strip() for query in queries if query.strip()]


def _build_trf2_domain_queries(themes: list[TnuTheme]) -> list[str]:
    token_counts: dict[str, int] = {}
    for theme in themes:
        for token in _collector_tokens(
            f"{theme.ramoDireito} {theme.questaoSubmetidaJulgamento} {theme.teseFirmada}"
        ):
            token_counts[token] = token_counts.get(token, 0) + 1
    top_tokens = [
        token
        for token, _count in sorted(token_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    queries: list[str] = []
    if len(top_tokens) >= 2:
        queries.append(" ".join(top_tokens[:2]))
    if len(top_tokens) >= 4:
        queries.append(" ".join(top_tokens[2:4]))
    if len(top_tokens) >= 6:
        queries.append(" ".join(top_tokens[4:6]))
    for preferred in ("previdenciario", "administrativo", "assistencial", "aposentadoria", "pensao"):
        if preferred in token_counts:
            queries.append(preferred)
    if len(top_tokens) >= 3:
        queries.append(f"{top_tokens[0]} {top_tokens[-1]}")
    if len(top_tokens) >= 5:
        queries.append(f"{top_tokens[1]} {top_tokens[4]}")
    return queries


def _score_trf2_decision_against_themes(decision: Trf2Decision, themes: list[TnuTheme] | None) -> int:
    if not themes:
        return 1
    decision_tokens = _collector_tokens(f"{decision.classe} {decision.assuntos} {decision.competencia}")
    best_score = 0
    for theme in themes:
        theme_tokens = _collector_tokens(
            f"{theme.ramoDireito} {theme.questaoSubmetidaJulgamento} {theme.teseFirmada}"
        )
        score = len(decision_tokens.intersection(theme_tokens))
        if score > best_score:
            best_score = score
    return best_score


def _trf2_decision_text_richness(decision: Trf2Decision) -> int:
    score = 0
    if decision.assuntos and decision.assuntos != "NAO_INFORMADO":
        score += min(400, len(decision.assuntos))
    if decision.classe and decision.classe != "NAO_INFORMADO":
        score += 60
    if decision.relatorOriginario:
        score += 20
    if decision.dataAutuacao:
        score += 10
    if _is_bad_trf2_subject_text(decision.assuntos):
        score -= 500
    return score


def _score_trf2_decision_documentability(
    decision: Trf2Decision,
    themes: list[TnuTheme] | None,
) -> int:
    score = _trf2_decision_text_richness(decision)
    normalized_class = normalize_for_matching(decision.classe)
    if "criminal" in normalized_class:
        score -= 500
    if decision.assuntos == "NAO_INFORMADO":
        score -= 300
    if themes:
        score += _score_trf2_decision_against_themes(decision, themes) * 50
        if _decision_has_local_document_action(decision, themes):
            score += 1000
    return score


def _collector_tokens(text: str) -> set[str]:
    normalized = normalize_for_matching(text)
    return {
        token
        for token in re.split(r"[^a-z0-9]+", normalized)
        if len(token) > 2 and token not in _TRF2_QUERY_STOPWORDS
    }


def _select_diverse_trf2_decisions(
    buckets: list[list[tuple[int, Trf2Decision]]],
    limit: int,
) -> list[Trf2Decision]:
    if not buckets:
        return []
    ranked_buckets = [
        list(bucket)
        for bucket in sorted(
            buckets,
            key=lambda bucket: (
                bucket[0][0],
                len(bucket),
                len(bucket[0][1].assuntos or ""),
            ),
            reverse=True,
        )
    ]
    per_bucket_cap = max(1, math.ceil(limit / max(1, len(ranked_buckets))) + 1)
    picks_by_bucket = [0 for _ in ranked_buckets]
    selected: list[Trf2Decision] = []
    while len(selected) < limit:
        progressed = False
        for index, bucket in enumerate(ranked_buckets):
            if len(selected) >= limit:
                break
            if not bucket or picks_by_bucket[index] >= per_bucket_cap:
                continue
            _score, decision = bucket.pop(0)
            selected.append(decision)
            picks_by_bucket[index] += 1
            progressed = True
        if not progressed:
            break
    return selected[:limit]


def _prefer_documentable_trf2_decisions(
    decisions: list[Trf2Decision],
    limit: int,
    themes: list[TnuTheme] | None,
) -> list[Trf2Decision]:
    if not themes:
        return decisions[:limit]
    documentable = [
        decision
        for decision in decisions
        if _score_trf2_decision_documentability(decision, themes) >= TRF2_MIN_DOCUMENTABLE_RICHNESS
    ]
    if len(documentable) >= max(1, min(limit, 3)):
        return documentable[:limit]
    return decisions[:limit]


def _decision_has_local_document_action(decision: Trf2Decision, themes: list[TnuTheme]) -> bool:
    from app.services.actions import derive_document_action
    from app.services.analysis import analyze_decision_local

    local_analysis = analyze_decision_local(decision, themes)
    if local_analysis.temaTnu == "NENHUM_TEMA":
        return False
    theme = next((item for item in themes if item.temaNumero == local_analysis.temaTnu), None)
    return derive_document_action(local_analysis, theme).action != "SEM_ACAO"


def _matches_trf2_turmas_recursais_es_filters(
    *,
    uf: str,
    orgao: str,
    data_julgamento: str,
    data_publicacao: str,
) -> bool:
    if (uf or "").strip().upper() != TRF2_TURMAS_RECURSAIS_ES_UF:
        return False
    if normalize_for_matching(orgao) not in TRF2_TURMAS_RECURSAIS_ES_ORGAOS_NORMALIZED:
        return False
    if not data_julgamento.endswith(TRF2_TURMAS_RECURSAIS_TARGET_YEAR):
        return False
    if not data_publicacao.endswith(TRF2_TURMAS_RECURSAIS_TARGET_YEAR):
        return False
    return True


def _fetch_html_with_browser(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (compatible; TCC-Bot/0.1)")
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1200)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return ""


def _parse_trf2_decisions_from_results_html(
    html: str,
    limit: int,
    *,
    session: requests.Session,
    headers: dict[str, str],
    detail_cache: dict[str, dict[str, str]],
) -> list[Trf2Decision]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[Trf2Decision] = []
    seen: set[str] = set()
    for link in soup.select("a.numero-processo[href*='processo_seleciona_publica']"):
        card = link
        for _ in range(6):
            parent = card.parent
            if not isinstance(parent, Tag):
                break
            card = parent
        block_text = _clean(card.get_text(" ", strip=True))
        numero_processo = _pick(block_text, r"PROCESSO\s+(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})")
        if not numero_processo or numero_processo in seen:
            continue
        seen.add(numero_processo)
        classe = _pick(block_text, r"\b[A-Z]{2,4}\s*-\s*([^.]+?)(?=\s+UF\b|\s+ÓRGÃO JULGADOR\b|\s+ORGAO JULGADOR\b)") or "NAO_INFORMADO"
        uf = _pick(block_text, r"\bUF\s+([A-Z]{2})(?=\s+ÓRGÃO JULGADOR\b|\s+ORGAO JULGADOR\b)") or ""
        orgao = _pick(block_text, r"(?:ÓRGÃO JULGADOR|ORGAO JULGADOR)\s+(.+?)(?=\s+DATA DO JULGAMENTO\b)") or "NAO_INFORMADO"
        relator = _pick(block_text, r"RELATOR\s+(.+?)(?=\s+DECISÃO\b|\s+DECISAO\b)") or ""
        data_julgamento = _pick(block_text, r"DATA DO JULGAMENTO\s+(\d{2}/\d{2}/\d{4})") or ""
        data_publicacao = _pick(block_text, r"DATA DA PUBLICA(?:ÇÃO|CAO)\s+(\d{2}/\d{2}/\d{4})") or ""
        if not _matches_trf2_turmas_recursais_es_filters(
            uf=uf,
            orgao=orgao,
            data_julgamento=data_julgamento,
            data_publicacao=data_publicacao,
        ):
            continue
        ementa = _pick(block_text, r"EMENTA\s+(.+)$") or ""
        assuntos = _summarize_ementa_subject(ementa)
        href = link.get("href") or ""
        result_document_href = _extract_trf2_result_document_href(card, href)
        if result_document_href:
            cached = dict(detail_cache.get(href) or {})
            cached["inteiroTeorPath"] = result_document_href
            detail_cache[href] = cached
        detail = _fetch_trf2_process_detail(session, headers, href, detail_cache)
        results.append(
            Trf2Decision(
                decisionId=f"TRF2-LIVE-{len(results) + 1}",
                classe=detail.get("classe", classe),
                tipoJulgamento="COLEGIADO",
                assuntos=detail.get("assuntos", assuntos),
                competencia=detail.get("colegiado", orgao),
                relatorOriginario=detail.get("relator", relator),
                dataAutuacao=detail.get("dataAutuacao", ""),
                dataJulgamento=data_julgamento,
                numeroProcesso=numero_processo,
                inteiroTeorPath=detail.get("inteiroTeorPath", result_document_href or href),
            )
        )
        if len(results) >= limit:
            break
    return results


def _summarize_ementa_subject(ementa: str) -> str:
    clean = _clean(ementa)
    if not clean:
        return "NAO_INFORMADO"
    match = re.search(r"(.+?)(?=\s+[IVX]+\s*-?\s+CASO EM EXAME\b)", clean, flags=re.IGNORECASE)
    if match:
        clean = match.group(1).strip()
    return clean[:420] or "NAO_INFORMADO"


def _fetch_trf2_process_detail(
    session: requests.Session,
    headers: dict[str, str],
    process_url: str,
    detail_cache: dict[str, dict[str, str]],
) -> dict[str, str]:
    if not process_url:
        return {}
    cached = detail_cache.get(process_url)
    if cached:
        return dict(cached)
    response: requests.Response | None = None
    for attempt in range(1, 4):
        time.sleep(TRF2_DETAIL_REQUEST_DELAY_S)
        try:
            response = session.get(process_url, timeout=30, headers=headers)
        except requests.RequestException:
            response = None
        if response is not None and response.ok and len(response.text) >= TRF2_DETAIL_MIN_HTML_LEN:
            break
        if response is not None and response.status_code == 429 and attempt < 3:
            time.sleep(0.6 * attempt)
            continue
        if attempt < 3:
            time.sleep(0.6 * attempt)
    if response is None or not response.ok or len(response.text) < TRF2_DETAIL_MIN_HTML_LEN:
        return {}
    response.encoding = response.encoding or "iso-8859-1"
    soup = BeautifulSoup(response.text, "html.parser")
    detail_text = _clean(soup.get_text(" ", strip=True))
    if _is_bad_trf2_subject_text(detail_text):
        return {}

    data_autuacao = _extract_text_by_id(soup, "txtAutuacao")
    colegiado = _extract_text_by_id(soup, "txtOrgaoJulgador")
    relator = _extract_text_by_id(soup, "txtMagistrado")
    classe = _extract_text_by_id(soup, "txtClasse")
    assuntos = _extract_trf2_detail_subjects(soup)
    inteiro_teor_path = _extract_trf2_detail_pdf_href(soup, process_url)

    if not data_autuacao:
        data_autuacao = _pick_date(detail_text, r"(autuacao.{0,40}?(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}:\d{2})?))")
    if not colegiado:
        colegiado = _extract_competencia(detail_text)
    if not relator:
        relator = _extract_relator(detail_text)
    if not classe or classe == "NAO_INFORMADO":
        classe = _extract_class(detail_text)
    if not assuntos:
        assuntos = _extract_assuntos(detail_text)

    detail: dict[str, str] = {}
    if data_autuacao:
        detail["dataAutuacao"] = data_autuacao
    if colegiado:
        detail["colegiado"] = colegiado
    if relator:
        detail["relator"] = relator
    if classe:
        detail["classe"] = classe
    if assuntos:
        detail["assuntos"] = assuntos
    if inteiro_teor_path:
        detail["inteiroTeorPath"] = inteiro_teor_path
    if detail and _trf2_detail_is_cacheworthy(detail):
        detail_cache[process_url] = dict(detail)
    return detail


def _trf2_detail_is_cacheworthy(detail: dict[str, str]) -> bool:
    assuntos = detail.get("assuntos", "")
    classe = detail.get("classe", "")
    if assuntos and assuntos != "NAO_INFORMADO" and not _is_bad_trf2_subject_text(assuntos):
        return True
    return bool(classe and classe != "NAO_INFORMADO")


def _load_trf2_detail_cache() -> dict[str, dict[str, str]]:
    path = Path(TRF2_DETAIL_CACHE_FILE)
    cache: dict[str, dict[str, str]] = {}
    if not path.exists():
        cache = {}
    else:
        try:
            parsed = json.loads(_read_json_text_with_fallbacks(path))
            cache = parsed if isinstance(parsed, dict) else {}
        except Exception:
            cache = {}
    _seed_trf2_detail_cache_from_runs(cache)
    return cache


def _save_trf2_detail_cache(cache: dict[str, dict[str, str]]) -> None:
    path = Path(TRF2_DETAIL_CACHE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_trf2_detail_cache_from_runs(cache: dict[str, dict[str, str]]) -> None:
    run_root = Path("outputs/runs")
    if not run_root.exists():
        return
    for csv_path in run_root.glob("run-*/data/trf2_decisoes.csv"):
        try:
            rows = _read_csv_rows(str(csv_path))
        except OSError:
            continue
        for row in rows:
            process_url = (row.get("inteiroTeorPath") or "").strip()
            if not process_url or process_url in cache:
                continue
            detail = {
                "classe": (row.get("classe") or "").strip(),
                "assuntos": (row.get("assuntos") or "").strip(),
                "colegiado": (row.get("competencia") or "").strip(),
                "relator": (row.get("relatorOriginario") or "").strip(),
                "dataAutuacao": (row.get("dataAutuacao") or "").strip(),
            }
            if _trf2_detail_is_cacheworthy(detail):
                cache[process_url] = detail


def _is_bad_trf2_subject_text(text: str) -> bool:
    normalized = normalize_for_matching(text)
    return any(marker in normalized for marker in TRF2_BAD_DETAIL_MARKERS)


def _extract_text_by_id(soup: BeautifulSoup, element_id: str) -> str:
    node = soup.find(id=element_id)
    if not isinstance(node, Tag):
        return ""
    return _clean(node.get_text(" ", strip=True))


def _extract_trf2_detail_subjects(soup: BeautifulSoup) -> str:
    subject_table = soup.select_one("fieldset#fldAssuntos table.infraTable, table.infraTable[summary='Assuntos']")
    if not isinstance(subject_table, Tag):
        return ""
    rows = subject_table.find_all("tr")
    descriptions: list[str] = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        descricao = _clean(cells[1].get_text(" ", strip=True))
        principal = _clean(cells[2].get_text(" ", strip=True)).upper()
        if descricao and principal == "SIM":
            return descricao[:420]
        if descricao:
            descriptions.append(descricao)
    if descriptions:
        return " | ".join(descriptions)[:420]
    return ""


def _extract_trf2_detail_pdf_href(soup: BeautifulSoup, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = (anchor.get("href") or "").strip()
        label = _clean(anchor.get_text(" ", strip=True))
        normalized_label = normalize_for_matching(label)
        normalized_href = normalize_for_matching(href)
        if not href:
            continue
        if "pdf" not in normalized_href and "acao=acessar_documento_publico" not in href:
            continue
        score = 0
        if "pdf" in normalized_href:
            score += 200
        if normalized_label.startswith("acor"):
            score += 120
        if "inteiro teor" in normalized_label:
            score += 80
        if "relvoto" in normalized_label:
            score += 60
        if "voto" in normalized_label:
            score += 30
        candidates.append((score, urljoin(base_url, href)))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_trf2_result_document_href(card: Tag, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    for anchor in card.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        if "acao=acessar_documento_publico" in href:
            candidates.append((_score_trf2_document_link(label, href), urljoin(base_url, href)))
            continue
        onclick = (anchor.get("onclick") or "").strip()
        extracted = _extract_trf2_public_document_url_from_text(onclick)
        if extracted:
            candidates.append((_score_trf2_document_link(label, extracted), urljoin(base_url, extracted)))
    raw_html = str(card)
    for extracted in re.findall(r"(?:href|onclick)=(?:\"|').*?(controlador\.php\?acao=acessar_documento_publico[^\"'> ]+)", raw_html, flags=re.IGNORECASE):
        candidates.append((50, urljoin(base_url, extracted)))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_trf2_public_document_url_from_text(text: str) -> str:
    if not text:
        return ""
    match = re.search(
        r"(controlador\.php\?acao=acessar_documento_publico[^'\" )]+)",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _score_trf2_document_link(label: str, href: str) -> int:
    normalized_label = normalize_for_matching(label)
    normalized_href = normalize_for_matching(href)
    score = 0
    if "acessar_documento_publico" in href:
        score += 40
    if normalized_label.startswith("acor"):
        score += 100
    if "inteiro teor" in normalized_label:
        score += 80
    if "relvoto" in normalized_label:
        score += 60
    if "voto" in normalized_label:
        score += 30
    if "acor" in normalized_href:
        score += 20
    return score


def _parse_trf2_decisions_from_html(html: str, limit: int) -> list[Trf2Decision]:
    soup = BeautifulSoup(html, "html.parser")
    full_text = _clean(soup.get_text(" ", strip=True))
    blocks = _extract_trf2_blocks(full_text, limit)
    results: list[Trf2Decision] = []
    for idx, block in enumerate(blocks, start=1):
        text = block["text"]
        numero_processo = block["numeroProcesso"]
        results.append(
            Trf2Decision(
                decisionId=f"TRF2-LIVE-{idx}",
                classe=_extract_class(text),
                tipoJulgamento=_extract_tipo_julgamento(text),
                assuntos=_extract_assuntos(text),
                competencia=_extract_competencia(text),
                relatorOriginario=_extract_relator(text),
                dataAutuacao=_pick_date(text, r"(autuacao.{0,40}?(\d{2}/\d{2}/\d{4}))"),
                dataJulgamento=_pick_date(text, r"(julgament[oa].{0,40}?(\d{2}/\d{2}/\d{4}))"),
                numeroProcesso=numero_processo,
                inteiroTeorPath=_find_pdf_near_process(soup, numero_processo) or "",
            )
        )
    return results


def _extract_trf2_blocks(full_text: str, limit: int) -> list[dict[str, str]]:
    block_re = re.compile(
        r"Processo\s+(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})([\s\S]{0,2200}?)(?=Processo\s+\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|$)"
    )
    seen: set[str] = set()
    blocks: list[dict[str, str]] = []
    for match in block_re.finditer(full_text):
        numero = match.group(1)
        if numero in seen:
            continue
        seen.add(numero)
        text = _clean_trf2_noise(f"Processo {numero} {match.group(2) or ''}")
        blocks.append({"numeroProcesso": numero, "text": text})
        if len(blocks) >= limit:
            break
    if blocks:
        return blocks

    process_re = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
    unique = []
    for m in process_re.finditer(full_text):
        val = m.group(0)
        if val not in unique:
            unique.append(val)
        if len(unique) >= limit:
            break
    text = _clean_trf2_noise(full_text)
    return [{"numeroProcesso": n, "text": text} for n in unique]


def _clean_trf2_noise(text: str) -> str:
    cleaned = text
    junk = [
        r"Ver todas Requerida no Recurso.*?Pesquisar",
        r"codigo verificador .*?assinatura:",
        r"Informacoes adicionais da assinatura:.*?(?=Ementa|Processo)",
        r"Data e Hora: \d{2}/\d{2}/\d{4}.*?(?=Ementa|Processo)",
    ]
    for pattern in junk:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return _clean(cleaned)


def _extract_class(text: str) -> str:
    return _pick(text, r"(Classe\s+)(.+?)(?=\s+Assunto(?:s)?\b|\s+Compet[êe]ncia\b|\s+Relator\b)") or "NAO_INFORMADO"


def _extract_tipo_julgamento(text: str) -> str:
    return _pick(
        text,
        r"(Tipo de Julgamento\s+)(.+?)(?=\s+Assunto(?:s)?\b|\s+Compet[êe]ncia\b|\s+Relator\b)",
    ) or ""


def _extract_assuntos(text: str) -> str:
    raw = _pick(
        text,
        r"(Assunto(?:s)?\s+)(.+?)(?=\s+Compet[êe]ncia\b|\s+Relator(?: Origin[áa]rio)?\b|\s+Data\b|\s+Ementa\b)",
    ) or text
    trimmed = re.sub(
        r"\b(AGRAVANTE|AGRAVADO|ADVOGADO\(A\)|DESPACHO/DECISAO|DESPACHO|DECISAO|VOTO)\b[\s\S]*",
        " ",
        raw,
        flags=re.IGNORECASE,
    )
    no_prefix = re.sub(r"^Processo\s+\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\s+Classe\s+.+?\s+Assunto(?:s)?\s+", "", trimmed, flags=re.IGNORECASE)
    compact = _clean(no_prefix)[:420]
    return compact or "NAO_INFORMADO"


def _extract_competencia(text: str) -> str:
    return _pick(text, r"(Compet[êe]ncia\s+)(.+?)(?=\s+Relator\b|\s+Data\b|\s+Ementa\b)") or "NAO_INFORMADO"


def _extract_relator(text: str) -> str:
    raw = _pick(text, r"(Relator(?: Origin[áa]rio)?\s+)(.+?)(?=\s+Data\b|\s+Ementa\b|\s+Inteiro Teor\b)") or ""
    return re.sub(r"^Origin[áa]rio\s+", "", raw, flags=re.IGNORECASE).strip()


def _pick(text: str, regex: str) -> str | None:
    m = re.search(regex, text, flags=re.IGNORECASE)
    if not m:
        return None
    return (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)).strip()


def _pick_date(text: str, regex: str) -> str:
    m = re.search(regex, text, flags=re.IGNORECASE)
    if not m or not m.lastindex or m.lastindex < 2:
        return ""
    return m.group(2).strip()


def _find_pdf_near_process(soup: BeautifulSoup, numero_processo: str) -> str | None:
    for link in soup.select("a[href$='.pdf']"):
        href = link.get("href")
        if not href:
            continue
        text = link.get_text(" ", strip=True)
        if numero_processo in text or numero_processo in href:
            return href
    return None


def _clean(value: str) -> str:
    return normalize_text(value)


def _cell_text(cells: list[Tag], idx: int) -> str:
    if idx >= len(cells):
        return ""
    return _clean(cells[idx].get_text(" ", strip=True))


def _cell_link(cells: list[Tag], idx: int) -> str | None:
    if idx >= len(cells):
        return None
    anchor = cells[idx].find("a")
    href = anchor.get("href") if anchor else None
    return urljoin(TNU_URL, href) if href else None


def _sample_themes() -> list[TnuTheme]:
    imported = _load_sample_themes_from_package()
    if imported:
        return imported
    return [
        TnuTheme(
            temaNumero="309",
            situacaoTema="JULGADO",
            ramoDireito="ADMINISTRATIVO",
            questaoSubmetidaJulgamento="Auxilio-alimentacao integra base de calculo da licenca-premio convertida em pecunia?",
            teseFirmada="O auxilio-alimentacao integra a base de calculo da licenca-premio nao usufruida.",
            numeroProcesso="PEDILEF 5001816-07.2020.4.04.7008/PR",
            dataDecisaoAfetacao="2022-08-18",
            relator="Relator Exemplo A",
            dataJulgamento="2023-10-10",
            dataPublicacaoAcordao="2023-11-01",
            transitoJulgado="2024-02-14",
            pdfPath="data/pdf/tnu/tema-309.pdf",
        ),
        TnuTheme(
            temaNumero="344",
            situacaoTema="JULGADO_SEM_TRANSITO",
            ramoDireito="PREVIDENCIARIO",
            questaoSubmetidaJulgamento="Salario-maternidade e devido em adocao de menor acima de doze anos?",
            teseFirmada="E devido salario-maternidade por 120 dias ao adotante de menor de dezoito anos.",
            numeroProcesso="PEDILEF 1006649-81.2020.4.01.3820/MG",
            dataDecisaoAfetacao="2023-10-19",
            relator="Relator Exemplo B",
            dataJulgamento="2025-03-12",
            dataPublicacaoAcordao="2025-03-20",
            transitoJulgado="",
            pdfPath="data/pdf/tnu/tema-344.pdf",
        ),
        TnuTheme(
            temaNumero="369",
            situacaoTema="AFETADO_NAO_JULGADO",
            ramoDireito="ASSISTENCIAL",
            questaoSubmetidaJulgamento="Exclusao de faixa de salario-minimo no calculo de renda per capita para BPC.",
            teseFirmada="",
            numeroProcesso="PEDILEF 0001882-94.2021.4.05.8500/SE",
            dataDecisaoAfetacao="2024-10-16",
            relator="Relator Exemplo C",
            dataJulgamento="",
            dataPublicacaoAcordao="",
            transitoJulgado="",
            pdfPath="data/pdf/tnu/tema-369.pdf",
        ),
    ]


def _sample_decisions() -> list[Trf2Decision]:
    imported = _load_sample_decisions_from_package()
    if imported:
        return imported
    return [
        Trf2Decision(
            decisionId="TRF2-0001",
            classe="PEDIDO DE UNIFORMIZACAO",
            tipoJulgamento="COLEGIADO",
            assuntos="Salario-maternidade em adocao",
            competencia="JEF",
            relatorOriginario="Relator 1",
            dataAutuacao="2025-01-10",
            dataJulgamento="2025-03-30",
            numeroProcesso="5000001-00.2025.4.02.5001",
            inteiroTeorPath="data/pdf/trf2/TRF2-0001.pdf",
        ),
        Trf2Decision(
            decisionId="TRF2-0002",
            classe="PEDIDO DE UNIFORMIZACAO",
            tipoJulgamento="COLEGIADO",
            assuntos="Auxilio-alimentacao em licenca-premio",
            competencia="JEF",
            relatorOriginario="Relator 2",
            dataAutuacao="2025-01-12",
            dataJulgamento="2025-03-30",
            numeroProcesso="5000002-00.2025.4.02.5001",
            inteiroTeorPath="data/pdf/trf2/TRF2-0002.pdf",
        ),
        Trf2Decision(
            decisionId="TRF2-0003",
            classe="PEDIDO DE UNIFORMIZACAO",
            tipoJulgamento="COLEGIADO",
            assuntos="Beneficio assistencial e renda familiar per capita",
            competencia="JEF",
            relatorOriginario="Relator 3",
            dataAutuacao="2025-01-14",
            dataJulgamento="2025-03-30",
            numeroProcesso="5000003-00.2025.4.02.5001",
            inteiroTeorPath="data/pdf/trf2/TRF2-0003.pdf",
        ),
    ]


def _read_csv_rows(path: str) -> list[dict[str, str]]:
    if path.startswith("zip::"):
        return _read_csv_rows_from_zip_spec(path)
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                return [dict(row) for row in reader if row]
        except UnicodeDecodeError:
            continue
    return []


def _normalize_header(value: str) -> str:
    normalized = normalize_for_matching(value)
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _get_field(row: dict[str, str], *candidates: str) -> str:
    indexed = {_normalize_header(key): (val or "").strip() for key, val in row.items() if key}
    for candidate in candidates:
        found = indexed.get(_normalize_header(candidate))
        if found:
            return found
    return ""


def _resolve_relative_file(csv_path: str, raw_path: str) -> str:
    clean = (raw_path or "").strip()
    if not clean:
        return ""
    if clean.startswith(("http://", "https://")):
        return clean
    if csv_path.startswith("zip::"):
        parts = csv_path.split("::", 2)
        if len(parts) == 3:
            zip_path = parts[1]
            entry = parts[2]
            entry_dir = Path(entry).parent
            normalized_entry = str((entry_dir / clean).as_posix()).replace("\\", "/")
            return f"zip::{zip_path}::{normalized_entry}"
    base_dir = Path(csv_path).parent
    joined = (base_dir / clean).resolve()
    return str(joined) if joined.exists() else clean


def _load_sample_themes_from_package() -> list[TnuTheme]:
    if not SAMPLE_TNU_ZIP.exists():
        return []
    return _collect_tnu_themes_import(
        f"zip::{SAMPLE_TNU_ZIP.as_posix()}::tnu/temas-tnu.csv",
        10_000,
    )


def _load_sample_decisions_from_package() -> list[Trf2Decision]:
    if not SAMPLE_TRF2_ZIP.exists():
        return []
    return _collect_trf2_decisions_import(
        f"zip::{SAMPLE_TRF2_ZIP.as_posix()}::trf2/decisoes.csv",
        10_000,
    )


def _read_csv_rows_from_zip_spec(spec: str) -> list[dict[str, str]]:
    parts = spec.split("::", 2)
    if len(parts) != 3:
        return []
    zip_path = parts[1]
    entry = parts[2]
    try:
        with zipfile.ZipFile(zip_path) as archive:
            with archive.open(entry, "r") as handle:
                raw = handle.read()
    except Exception:
        return []

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            reader = csv.DictReader(text.splitlines())
            return [dict(row) for row in reader if row]
        except UnicodeDecodeError:
            continue
    return []


def _read_json_text_with_fallbacks(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")

from __future__ import annotations

import csv
import re
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
TRF2_URL = "https://juris.trf2.jus.br/consulta.php?q="


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
    return parsed if parsed else _sample_themes()[:limit]


def collect_trf2_decisions(
    mode: CollectionMode,
    limit: int,
    browser_automation: bool = True,
    import_csv_file: str | None = None,
) -> list[Trf2Decision]:
    if mode == "sample":
        return _sample_decisions()[:limit]
    if mode == "import":
        return _collect_trf2_decisions_import(import_csv_file, limit)
    html = _fetch_html(TRF2_URL)
    parsed = _parse_trf2_decisions_from_html(html, limit)
    if not parsed and browser_automation:
        dynamic_html = _fetch_html_with_browser(TRF2_URL)
        if dynamic_html:
            parsed = _parse_trf2_decisions_from_html(dynamic_html, limit)
    return parsed if parsed else _sample_decisions()[:limit]


def _fetch_html(url: str) -> str:
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    for attempt in range(1, 4):
        resp = requests.get(url, timeout=30, headers=headers)
        if resp.ok:
            resp.encoding = resp.encoding or "utf-8"
            return resp.text
        if attempt == 3:
            raise RuntimeError(f"Falha ao acessar {url}: HTTP {resp.status_code}")
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
    base_dir = Path(csv_path).parent
    joined = (base_dir / clean).resolve()
    return str(joined) if joined.exists() else clean


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

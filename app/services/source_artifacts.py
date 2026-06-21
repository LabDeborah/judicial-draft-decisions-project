from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.domain.types import TnuTheme, Trf2Decision
from app.services.documents import _compile_tex_to_pdf
from app.utils.fs import ensure_dir, write_text
from app.utils.text import normalize_text

TNU_VIRTUS_SEARCH_URL = "https://www.cjf.jus.br/phpdoc/virtus/pesqinteiroteor.php"
TNU_VIRTUS_BASE_URL = "https://www.cjf.jus.br/phpdoc/virtus/"
LOCAL_CHROME_USER_DATA = Path.home() / "AppData/Local/Google/Chrome/User Data"
TRF2_PROFILE_CLONE_ROOT = Path("outputs/playwright-profile-runtime")
TRF2_DOCUMENT_URL_CACHE_FILE = Path("outputs/reports/trf2_document_url_cache.json")
TRF2_DETAIL_CACHE_FILE = Path("outputs/reports/trf2_detail_cache.json")


def materialize_source_artifacts(
    *,
    data_dir: str,
    themes: list[TnuTheme],
    decisions: list[Trf2Decision],
    latex_engine: str | None,
    trf2_chrome_profile: str | None = None,
) -> None:
    themes_dir = Path(data_dir) / "themes"
    decisions_dir = Path(data_dir) / "decisions"
    ensure_dir(str(themes_dir))
    ensure_dir(str(decisions_dir))

    document_url_cache = _load_trf2_document_url_cache()
    total_themes = len(themes)
    total_decisions = len(decisions)
    for index, theme in enumerate(themes, start=1):
        if total_themes:
            _log_artifacts(
                "artifacts",
                f"theme PDF {index}/{total_themes} tema={theme.temaNumero or 'NAO_INFORMADO'}",
            )
        try:
            local_pdf = _materialize_theme_pdf(theme, themes_dir, latex_engine)
        except Exception as exc:  # noqa: BLE001
            _log_artifacts(
                "artifacts.error",
                (
                    f"theme materialization failed tema={theme.temaNumero or 'NAO_INFORMADO'} "
                    f"error={exc!r}; using fallback PDF"
                ),
            )
            local_pdf = _render_theme_fallback_pdf(theme, themes_dir, latex_engine)
        if local_pdf:
            theme.pdfPath = local_pdf

    for index, decision in enumerate(decisions, start=1):
        if total_decisions:
            _log_artifacts(
                "artifacts",
                (
                    f"decision PDF {index}/{total_decisions} "
                    f"decision={decision.decisionId or 'NAO_INFORMADO'}"
                ),
            )
        try:
            local_pdf = _materialize_decision_pdf(
                decision,
                decisions_dir,
                latex_engine,
                trf2_chrome_profile,
                document_url_cache,
            )
        except Exception as exc:  # noqa: BLE001
            _log_artifacts(
                "artifacts.error",
                (
                    f"decision materialization failed decision={decision.decisionId or 'NAO_INFORMADO'} "
                    f"error={exc!r}; using fallback PDF"
                ),
            )
            local_pdf = _render_decision_fallback_pdf(decision, decisions_dir, latex_engine)
        if local_pdf:
            decision.inteiroTeorPath = local_pdf
    _save_trf2_document_url_cache(document_url_cache)


def _materialize_theme_pdf(theme: TnuTheme, output_dir: Path, latex_engine: str | None) -> str | None:
    filename = f"tema-{_safe_slug(theme.temaNumero or theme.numeroProcesso or 'sem-id')}.pdf"
    target = output_dir / filename
    direct_source = theme.pdfPath or ""
    downloaded = _download_or_copy_pdf(direct_source, target)
    if not downloaded:
        downloaded = _download_tnu_theme_pdf(theme, target)
    if downloaded:
        return downloaded
    return _render_theme_fallback_pdf(theme, output_dir, latex_engine)


def _render_theme_fallback_pdf(theme: TnuTheme, output_dir: Path, latex_engine: str | None) -> str | None:
    filename = f"tema-{_safe_slug(theme.temaNumero or theme.numeroProcesso or 'sem-id')}.pdf"
    target = output_dir / filename
    context = {
        "titulo": f"Tema {theme.temaNumero}",
        "linha_1": f"Processo: {theme.numeroProcesso or 'NAO_INFORMADO'}",
        "linha_2": f"Situacao: {theme.situacaoTema or 'NAO_INFORMADO'}",
        "linha_3": f"Ramo: {theme.ramoDireito or 'NAO_INFORMADO'}",
        "linha_4": f"Questao: {theme.questaoSubmetidaJulgamento or 'NAO_INFORMADO'}",
        "linha_5": f"Tese: {theme.teseFirmada or 'NAO_INFORMADO'}",
        "linha_6": f"Fonte: {theme.pdfPath or 'NAO_INFORMADO'}",
    }
    return _render_metadata_pdf(target, context, latex_engine)


def _materialize_decision_pdf(
    decision: Trf2Decision,
    output_dir: Path,
    latex_engine: str | None,
    trf2_chrome_profile: str | None,
    document_url_cache: dict[str, str],
) -> str | None:
    filename = f"{_safe_slug(decision.decisionId or decision.numeroProcesso or 'sem-id')}.pdf"
    target = output_dir / filename
    direct_source = decision.inteiroTeorPath or ""
    downloaded = _download_or_copy_pdf(direct_source, target)
    if not downloaded:
        downloaded = _download_trf2_decision_pdf(
            decision,
            target,
            latex_engine,
            trf2_chrome_profile=trf2_chrome_profile,
            document_url_cache=document_url_cache,
        )
    if downloaded:
        return downloaded
    return _render_decision_fallback_pdf(decision, output_dir, latex_engine)


def _render_decision_fallback_pdf(
    decision: Trf2Decision,
    output_dir: Path,
    latex_engine: str | None,
) -> str | None:
    filename = f"{_safe_slug(decision.decisionId or decision.numeroProcesso or 'sem-id')}.pdf"
    target = output_dir / filename
    context = {
        "titulo": f"Decisao {decision.decisionId}",
        "linha_1": f"Processo: {decision.numeroProcesso or 'NAO_INFORMADO'}",
        "linha_2": f"Classe: {decision.classe or 'NAO_INFORMADO'}",
        "linha_3": f"Assuntos: {decision.assuntos or 'NAO_INFORMADO'}",
        "linha_4": f"Competencia: {decision.competencia or 'NAO_INFORMADO'}",
        "linha_5": f"Relator: {decision.relatorOriginario or 'NAO_INFORMADO'}",
        "linha_6": f"Fonte: {decision.inteiroTeorPath or 'NAO_INFORMADO'}",
    }
    return _render_metadata_pdf(target, context, latex_engine)


def _download_or_copy_pdf(source: str, target: Path) -> str | None:
    if not source:
        return None
    if source.startswith("zip::"):
        return _copy_pdf_from_zip_spec(source, target)
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        try:
            response = requests.get(
                source,
                timeout=45,
                headers={"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"},
            )
        except requests.RequestException:
            return None
        content_type = (response.headers.get("content-type") or "").lower()
        if not response.ok or ("pdf" not in content_type and not source.lower().endswith(".pdf")):
            return None
        target.write_bytes(response.content)
        return str(target)
    local_path = Path(source)
    if local_path.exists() and local_path.suffix.lower() == ".pdf":
        shutil.copyfile(local_path, target)
        return str(target)
    return None


def _copy_pdf_from_zip_spec(source: str, target: Path) -> str | None:
    parts = source.split("::", 2)
    if len(parts) != 3:
        return None
    zip_path, entry = parts[1], parts[2]
    if not entry.lower().endswith(".pdf"):
        return None
    try:
        with zipfile.ZipFile(zip_path) as archive:
            target.write_bytes(archive.read(entry))
    except Exception:
        return None
    return str(target)


def _download_tnu_theme_pdf(theme: TnuTheme, target: Path) -> str | None:
    process_digits = re.sub(r"\D+", "", theme.numeroProcesso or "")
    if not process_digits:
        return None
    session = requests.Session()
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    try:
        search_response = session.post(
            TNU_VIRTUS_SEARCH_URL,
            data={"tipo": "num_pro", "pesq": process_digits, "nm_arq": "int_teor"},
            timeout=45,
            headers=headers,
        )
    except requests.RequestException:
        return None
    if not search_response.ok:
        return None
    soup = BeautifulSoup(search_response.text, "html.parser")
    anchor = soup.find("a", href=lambda value: value and "mostradocumentoInd.php" in value)
    if not isinstance(anchor, Tag):
        return None
    first_url = urljoin(TNU_VIRTUS_BASE_URL, anchor.get("href", ""))
    try:
        redirect_1 = session.get(first_url, timeout=45, headers=headers)
        redirect_2 = session.get(urljoin(TNU_VIRTUS_BASE_URL, _extract_js_redirect(redirect_1.text)), timeout=45, headers=headers)
    except requests.RequestException:
        return None
    final_relative = _extract_js_redirect(redirect_2.text)
    if not final_relative:
        return None
    final_url = urljoin(TNU_VIRTUS_BASE_URL, final_relative)
    return _download_or_copy_pdf(final_url, target)


def _download_trf2_decision_pdf(
    decision: Trf2Decision,
    target: Path,
    latex_engine: str | None,
    *,
    trf2_chrome_profile: str | None,
    document_url_cache: dict[str, str],
) -> str | None:
    document_url = _resolve_trf2_public_document_url(
        decision.inteiroTeorPath or "",
        configured_profile=trf2_chrome_profile,
        document_url_cache=document_url_cache,
    )
    if not document_url:
        return None
    if document_url.lower().endswith(".pdf"):
        return _download_or_copy_pdf(document_url, target)
    session = requests.Session()
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    try:
        response = session.get(document_url, timeout=45, headers=headers)
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    content_type = (response.headers.get("content-type") or "").lower()
    if "pdf" in content_type:
        target.write_bytes(response.content)
        return str(target)
    if "html" not in content_type:
        return None
    printed_pdf = _download_trf2_public_print_pdf(
        session=session,
        document_url=document_url,
        document_html=response.text,
        target=target,
    )
    if printed_pdf:
        return printed_pdf
    local_profile_pdf = _render_trf2_document_page_pdf_with_local_profile(
        document_url,
        target,
        configured_profile=trf2_chrome_profile,
    )
    if local_profile_pdf:
        return local_profile_pdf
    browser_pdf = _render_trf2_document_page_pdf(document_url, target)
    if browser_pdf:
        return browser_pdf
    soup = BeautifulSoup(response.text, "html.parser")
    doc_root = soup.find(id="divInfraAreaDados") or soup.find(id="divdochtml") or soup.find("body")
    if not isinstance(doc_root, Tag):
        return None
    lines = [_normalize_line(node.get_text(" ", strip=True)) for node in doc_root.find_all(["p", "div", "tr", "td"])]
    lines = [line for line in lines if line]
    if not lines:
        lines = [_normalize_line(doc_root.get_text(" ", strip=True))]
    return _render_official_document_pdf(target, decision, lines[:120], latex_engine)


def _resolve_trf2_public_document_url(
    source: str,
    *,
    configured_profile: str | None,
    document_url_cache: dict[str, str],
) -> str:
    if not source:
        return ""
    cached = document_url_cache.get(source, "")
    if cached:
        return cached
    if "acao=acessar_documento_publico" in source:
        document_url_cache[source] = source
        return source
    if "acao=processo_seleciona_publica" not in source:
        return source
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    try:
        response = requests.get(source, timeout=45, headers=headers)
    except requests.RequestException:
        return _resolve_trf2_public_document_url_with_local_profile(source, configured_profile, document_url_cache)
    if not response.ok:
        return _resolve_trf2_public_document_url_with_local_profile(source, configured_profile, document_url_cache)
    soup = BeautifulSoup(response.text, "html.parser")
    resolved = _extract_best_public_document_url_from_soup(soup, source)
    if resolved:
        document_url_cache[source] = resolved
        return resolved
    return _resolve_trf2_public_document_url_with_local_profile(source, configured_profile, document_url_cache)


def _extract_js_redirect(html: str) -> str:
    match = re.search(r"location\.href\s*=\s*'([^']+)'", html, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _load_trf2_document_url_cache() -> dict[str, str]:
    cache: dict[str, str] = {}
    if TRF2_DOCUMENT_URL_CACHE_FILE.exists():
        try:
            parsed = json.loads(_read_json_text_with_fallbacks(TRF2_DOCUMENT_URL_CACHE_FILE))
            if isinstance(parsed, dict):
                cache = {str(key): str(value) for key, value in parsed.items() if key and value}
        except Exception:
            cache = {}
    if TRF2_DETAIL_CACHE_FILE.exists():
        try:
            parsed = json.loads(_read_json_text_with_fallbacks(TRF2_DETAIL_CACHE_FILE))
            if isinstance(parsed, dict):
                for process_url, detail in parsed.items():
                    if not isinstance(detail, dict):
                        continue
                    document_url = str(detail.get("inteiroTeorPath") or "").strip()
                    if process_url and "acao=acessar_documento_publico" in document_url:
                        cache.setdefault(str(process_url), document_url)
        except Exception:
            pass
    return cache


def _save_trf2_document_url_cache(cache: dict[str, str]) -> None:
    TRF2_DOCUMENT_URL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ordered = {key: cache[key] for key in sorted(cache)}
    TRF2_DOCUMENT_URL_CACHE_FILE.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json_text_with_fallbacks(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_best_public_document_url_from_soup(soup: BeautifulSoup, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if "acao=acessar_documento_publico" not in href:
            continue
        label = _normalize_line(anchor.get_text(" ", strip=True)).upper()
        score = 0
        if label.startswith("ACOR"):
            score += 100
        if "RELVOTO" in label:
            score += 60
        if "VOTO" in label:
            score += 30
        candidates.append((score, urljoin(base_url, href)))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _download_trf2_public_print_pdf(
    *,
    session: requests.Session,
    document_url: str,
    document_html: str,
    target: Path,
) -> str | None:
    soup = BeautifulSoup(document_html, "html.parser")
    form = soup.find("form", action=lambda value: value and "minuta_imprimir" in value)
    if not isinstance(form, Tag):
        return None
    payload: dict[str, str] = {}
    for field in form.find_all("input"):
        if not isinstance(field, Tag):
            continue
        name = (field.get("name") or "").strip()
        if not name:
            continue
        payload[name] = (field.get("value") or "").strip()
    if not payload.get("txtdochtml"):
        doc_root = soup.find(id="divInfraAreaDados") or soup.find(id="divdochtml") or soup.find("body")
        payload["txtdochtml"] = str(doc_root or "")
    action = (form.get("action") or "").strip()
    if not action:
        return None
    print_url = urljoin(document_url, action)
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    try:
        response = session.post(print_url, data=payload, timeout=60, headers=headers, allow_redirects=False)
    except requests.RequestException:
        return None
    if _store_pdf_response(response, target):
        return str(target)
    current_url = print_url
    current_response = response
    for _ in range(3):
        location = (current_response.headers.get("location") or "").strip()
        if not location:
            break
        next_url = urljoin(current_url, location)
        if "sessao foi encerrada" in next_url.lower():
            return None
        try:
            current_response = session.get(next_url, timeout=60, headers=headers, allow_redirects=False)
        except requests.RequestException:
            return None
        current_url = next_url
        if _store_pdf_response(current_response, target):
            return str(target)
    return None


def _store_pdf_response(response: requests.Response, target: Path) -> bool:
    content_type = (response.headers.get("content-type") or "").lower()
    if "pdf" not in content_type:
        return False
    target.write_bytes(response.content)
    return True


def _render_trf2_document_page_pdf(document_url: str, target: Path) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (compatible; TCC-Bot/0.1)")
            page.goto(document_url, wait_until="networkidle", timeout=60000)
            page.emulate_media(media="print")
            page.add_style_tag(
                content="""
                .infraButton,
                .btn,
                .glyphicon,
                .fa,
                .material-icons,
                form[action*="minuta_imprimir"] {
                  display: none !important;
                }
                body {
                  background: white !important;
                }
                #divdochtml, #divInfraAreaDados {
                  margin: 0 auto !important;
                  width: auto !important;
                }
                """
            )
            page.pdf(
                path=str(target),
                format="A4",
                margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
                print_background=True,
            )
            browser.close()
    except Exception:
        return None
    return str(target) if target.exists() else None


def _resolve_trf2_public_document_url_with_local_profile(
    source: str,
    configured_profile: str | None,
    document_url_cache: dict[str, str],
) -> str:
    if not LOCAL_CHROME_USER_DATA.exists():
        return ""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    for profile_name in _candidate_local_chrome_profiles(configured_profile):
        cloned_user_data = _clone_local_chrome_profile(profile_name)
        if not cloned_user_data:
            scripted = _resolve_trf2_public_document_url_via_profile_script(profile_name, source)
            if scripted:
                document_url_cache[source] = scripted
                return scripted
            continue
        try:
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(cloned_user_data),
                    channel="chrome",
                    headless=False,
                    accept_downloads=True,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1440, "height": 1200},
                    locale="pt-BR",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/137.0.0.0 Safari/537.36"
                    ),
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(source, wait_until="commit", timeout=60000)
                page.wait_for_timeout(6000)
                title = page.title()
                if "429" in title or "Too Many Requests" in title:
                    context.close()
                    continue
                html = page.content()
                context.close()
        except Exception:
            scripted = _resolve_trf2_public_document_url_via_profile_script(profile_name, source)
            if scripted:
                document_url_cache[source] = scripted
                return scripted
            continue
        soup = BeautifulSoup(html, "html.parser")
        resolved = _extract_best_public_document_url_from_soup(soup, source)
        if resolved:
            document_url_cache[source] = resolved
            return resolved
        scripted = _resolve_trf2_public_document_url_via_profile_script(profile_name, source)
        if scripted:
            document_url_cache[source] = scripted
            return scripted
    return ""


def _render_trf2_document_page_pdf_with_local_profile(
    document_url: str,
    target: Path,
    *,
    configured_profile: str | None,
) -> str | None:
    if not LOCAL_CHROME_USER_DATA.exists():
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    for profile_name in _candidate_local_chrome_profiles(configured_profile):
        cloned_user_data = _clone_local_chrome_profile(profile_name)
        if not cloned_user_data:
            scripted_pdf = _render_trf2_document_page_pdf_via_profile_script(profile_name, document_url, target)
            if scripted_pdf:
                return scripted_pdf
            continue
        try:
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(cloned_user_data),
                    channel="chrome",
                    headless=False,
                    accept_downloads=True,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1440, "height": 1200},
                    locale="pt-BR",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/137.0.0.0 Safari/537.36"
                    ),
                )
                page = context.pages[0] if context.pages else context.new_page()
                for attempt in range(1, 4):
                    page.goto(document_url, wait_until="commit", timeout=60000)
                    page.wait_for_timeout(6000)
                    title = page.title()
                    if "429" in title or "Too Many Requests" in title:
                        page.wait_for_timeout(8000 * attempt)
                        continue
                    page.emulate_media(media="print")
                    page.pdf(
                        path=str(target),
                        format="A4",
                        margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
                        print_background=True,
                    )
                    break
                context.close()
        except Exception:
            scripted_pdf = _render_trf2_document_page_pdf_via_profile_script(profile_name, document_url, target)
            if scripted_pdf:
                return scripted_pdf
            continue
        if target.exists():
            return str(target)
        scripted_pdf = _render_trf2_document_page_pdf_via_profile_script(profile_name, document_url, target)
        if scripted_pdf:
            return scripted_pdf
    return None


def _candidate_local_chrome_profiles(configured_profile: str | None) -> list[str]:
    configured = (configured_profile or os.getenv("TRF2_CHROME_PROFILE", "")).strip()
    if configured:
        return [configured]
    candidates = ["Profile 1", "Default"]
    out: list[str] = []
    for candidate in candidates:
        if candidate in out:
            continue
        if (LOCAL_CHROME_USER_DATA / candidate).exists():
            out.append(candidate)
    return out


def _clone_local_chrome_profile(profile_name: str) -> Path | None:
    source_profile = LOCAL_CHROME_USER_DATA / profile_name
    if not source_profile.exists():
        return None
    target_root = TRF2_PROFILE_CLONE_ROOT / _safe_slug(profile_name)
    if target_root.exists():
        shutil.rmtree(target_root, ignore_errors=True)
    target_root.mkdir(parents=True, exist_ok=True)
    local_state = LOCAL_CHROME_USER_DATA / "Local State"
    if local_state.exists():
        try:
            shutil.copy2(local_state, target_root / "Local State")
        except OSError:
            pass
    ignore = shutil.ignore_patterns(
        "Cache",
        "Code Cache",
        "GPUCache",
        "Service Worker",
        "ShaderCache",
        "GrShaderCache",
        "GraphiteDawnCache",
        "DawnGraphiteCache",
        "DawnWebGPUCache",
        "Crashpad",
        "BrowserMetrics*",
        "Visited Links",
        "WebStorage",
        "blob_storage",
        "LOCK",
        "*.lock",
        "Cookies",
        "Cookies-journal",
        "Session*",
        "Tabs_*",
    )
    try:
        shutil.copytree(source_profile, target_root / profile_name, ignore=ignore, dirs_exist_ok=True)
    except OSError:
        return None
    return target_root


def _render_trf2_document_page_pdf_via_profile_script(
    profile_name: str,
    document_url: str,
    target: Path,
) -> str | None:
    script_path = Path("tools/inspect_trf2_chrome_profile.py")
    if not script_path.exists():
        return None
    try:
        subprocess.run(
            [sys.executable, str(script_path), document_url, profile_name],
            cwd=str(Path.cwd()),
            capture_output=True,
            timeout=420,
            check=False,
        )
    except Exception:
        return None
    rendered = Path("outputs/playwright-inspect") / f"page-print-{profile_name.replace(' ', '_').lower()}.pdf"
    if not rendered.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rendered, target)
    return str(target)


def _resolve_trf2_public_document_url_via_profile_script(
    profile_name: str,
    process_url: str,
) -> str:
    script_path = Path("tools/inspect_trf2_process_profile.py")
    if not script_path.exists():
        return ""
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path), process_url, profile_name],
            cwd=str(Path.cwd()),
            capture_output=True,
            timeout=420,
            check=False,
        )
    except Exception:
        return ""
    stdout_text = _decode_subprocess_output(completed.stdout)
    for line in stdout_text.splitlines():
        if line.startswith("document_url:"):
            return line.split(":", 1)[1].strip()
    return ""


def _render_metadata_pdf(target_pdf: Path, context: dict[str, str], latex_engine: str | None) -> str | None:
    tex_path = target_pdf.with_suffix(".tex")
    latex = (
        "\\documentclass[12pt]{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[brazil]{babel}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        "\\setlength{\\parindent}{0pt}\n"
        "\\begin{document}\n"
        f"\\section*{{{_escape_latex(context['titulo'])}}}\n"
        f"{_escape_latex(context['linha_1'])}\\\\\n"
        f"{_escape_latex(context['linha_2'])}\\\\\n"
        f"{_escape_latex(context['linha_3'])}\\\\\n"
        f"{_escape_latex(context['linha_4'])}\\\\\n"
        f"{_escape_latex(context['linha_5'])}\\\\\n"
        f"{_escape_latex(context['linha_6'])}\n"
        "\\end{document}\n"
    )
    write_text(str(tex_path), latex)
    if _compile_tex_to_pdf(tex_path, latex_engine):
        return str(target_pdf)
    return None


def _render_official_document_pdf(
    target_pdf: Path,
    decision: Trf2Decision,
    lines: list[str],
    latex_engine: str | None,
) -> str | None:
    tex_path = target_pdf.with_suffix(".tex")
    body = "\n".join(f"{_escape_latex(line)}\\\\\n" for line in lines if line)
    latex = (
        "\\documentclass[12pt]{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[brazil]{babel}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        "\\setlength{\\parindent}{0pt}\n"
        "\\begin{document}\n"
        f"\\section*{{Documento oficial - { _escape_latex(decision.decisionId) }}}\n"
        f"Processo: {_escape_latex(decision.numeroProcesso or 'NAO_INFORMADO')}\\\\\n"
        f"Fonte oficial: {_escape_latex(decision.inteiroTeorPath or 'NAO_INFORMADO')}\\\\\n\n"
        f"{body}\n"
        "\\end{document}\n"
    )
    write_text(str(tex_path), latex)
    if _compile_tex_to_pdf(tex_path, latex_engine):
        return str(target_pdf)
    return None


def _safe_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")[:80] or "arquivo"


def _normalize_line(value: str) -> str:
    return normalize_text(value)


def _escape_latex(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("~", "\\textasciitilde{}")
        .replace("^", "\\textasciicircum{}")
    )


def _log_artifacts(stage: str, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{stage}] {message}", file=sys.stderr)


def _decode_subprocess_output(raw: bytes | str) -> str:
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

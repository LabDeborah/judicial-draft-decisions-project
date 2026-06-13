from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


SEARCH_URL = "https://eproc-consulta.jfes.jus.br/eproc/externo_controlador.php?acao=processo_consulta_publica"


def _copy_profile(src_root: Path, profile_name: str, dst_root: Path) -> None:
    if dst_root.exists():
        shutil.rmtree(dst_root, ignore_errors=True)
    dst_root.mkdir(parents=True, exist_ok=True)
    local_state = src_root / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, dst_root / "Local State")
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
    shutil.copytree(src_root / profile_name, dst_root / profile_name, ignore=ignore, dirs_exist_ok=True)


def _best_document_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if "acao=acessar_documento_publico" not in href:
            continue
        label = anchor.get_text(" ", strip=True).upper()
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


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python tools/search_trf2_process_profile.py <process_digits> <profile_name>")
        return 1
    process_digits = sys.argv[1]
    profile_name = sys.argv[2]
    chrome_user_data = Path.home() / "AppData/Local/Google/Chrome/User Data"
    temp_user_data = Path("outputs/playwright-profile-search-run") / profile_name
    _copy_profile(chrome_user_data, profile_name, temp_user_data)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(temp_user_data),
            channel="chrome",
            headless=False,
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
        page.goto(SEARCH_URL, wait_until="commit", timeout=60000)
        page.wait_for_timeout(6000)
        print("search_title:", page.title())
        first_numeric = page.locator("input[type='text']").nth(1)
        first_numeric.click()
        first_numeric.type(process_digits, delay=50)
        print("filled_value:", first_numeric.input_value())
        page.locator("form").evaluate("(form) => form.requestSubmit()")
        page.wait_for_timeout(10000)
        print("after_submit_title:", page.title())
        print("after_submit_url:", page.url)
        print("after_submit_value:", first_numeric.input_value())
        html = page.content()
        print("errors:", page.locator(".infraExcecao, .alert, .warning, .texto").all_inner_texts())
        print("document_url:", _best_document_url(html, page.url))
        print("snippet:", html[:1500].replace("\n", " ").replace("\r", " "))
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


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
        print("usage: python tools/inspect_trf2_process_profile.py <process_url> <profile_name>")
        return 1
    process_url = sys.argv[1]
    profile_name = sys.argv[2]
    chrome_user_data = Path.home() / "AppData/Local/Google/Chrome/User Data"
    temp_user_data = Path("outputs/playwright-profile-process") / profile_name
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
        for attempt in range(1, 4):
            page.goto(process_url, wait_until="commit", timeout=60000)
            page.wait_for_timeout(6000)
            title = page.title()
            print("attempt:", attempt, "title:", title, "url:", page.url)
            if "429" in title or "Too Many Requests" in title:
                time.sleep(8 * attempt)
                continue
            html = page.content()
            document_url = _best_document_url(html, process_url)
            if document_url:
                print("document_url:", document_url)
                context.close()
                return 0
            soup = BeautifulSoup(html, "html.parser")
            anchors = soup.find_all("a", href=True)
            print("anchors:", len(anchors))
            for index, anchor in enumerate(anchors[:12], start=1):
                print("link", index, anchor.get_text(" ", strip=True), anchor.get("href", ""))
            print("snippet:", html[:1200].replace("\n", " ").replace("\r", " "))
        context.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

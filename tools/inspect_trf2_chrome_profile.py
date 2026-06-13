from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_URL = (
    "https://eproc-consulta.jfes.jus.br/eproc/controlador.php?"
    "acao=acessar_documento_publico&doc=501778688745446793190552401567&"
    "evento=501778688745446793190552408998&key=c945760b35a58e4a5f166a8f3b0533cbde00b58a43f6136a2e3f093164f33028&"
    "hash=1f3fa315cd4b7bdb7c5eeeebc4145198"
)


def _copy_profile(src_root: Path, profile_name: str, dst_root: Path) -> Path:
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)
    local_state = src_root / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, dst_root / "Local State")
    src_profile = src_root / profile_name
    dst_profile = dst_root / profile_name
    ignore = shutil.ignore_patterns(
        "Cache",
        "Code Cache",
        "GPUCache",
        "Service Worker",
        "ShaderCache",
        "GrShaderCache",
        "GraphiteDawnCache",
        "Crashpad",
        "BrowserMetrics*",
        "Visited Links",
        "WebStorage",
        "blob_storage",
    )
    shutil.copytree(src_profile, dst_profile, ignore=ignore, dirs_exist_ok=True)
    return dst_profile


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    profile_name = sys.argv[2] if len(sys.argv) > 2 else "Default"
    chrome_user_data = Path.home() / "AppData/Local/Google/Chrome/User Data"
    temp_user_data = Path("outputs/playwright-profile") / profile_name
    downloads_dir = Path("outputs/playwright-inspect")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    copied_profile = _copy_profile(chrome_user_data, profile_name, temp_user_data)
    print("copied_profile:", copied_profile)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(temp_user_data),
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
            page.goto(url, wait_until="commit", timeout=60000)
            page.wait_for_timeout(6000)
            title = page.title()
            print("attempt:", attempt, "page_url:", page.url)
            print("title:", title)
            if "429" in title or "Too Many Requests" in title:
                time.sleep(8 * attempt)
                continue
            pdf_target = downloads_dir / f"page-print-{profile_name.replace(' ', '_').lower()}.pdf"
            try:
                page.emulate_media(media="print")
                page.pdf(
                    path=str(pdf_target),
                    format="A4",
                    margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
                    print_background=True,
                )
                print("page_pdf_preclick:", pdf_target)
            except Exception as exc:  # noqa: BLE001
                print("page_pdf_preclick_error:", repr(exc))
            try:
                form_action = page.locator("form[action*='minuta_imprimir']").first.get_attribute("action")
                print("form_action:", form_action)
            except Exception as exc:  # noqa: BLE001
                print("form_error:", repr(exc))
                break
            try:
                print_button = page.locator("input[name='btnImprimir']").first
                print("button_onclick:", print_button.get_attribute("onclick"))
                print("button_value:", print_button.get_attribute("value"))
            except Exception as exc:  # noqa: BLE001
                print("button_error:", repr(exc))
            try:
                existing_pages = len(context.pages)
                with page.expect_download(timeout=20000) as download_info:
                    print_button.click()
                download = download_info.value
                target = downloads_dir / download.suggested_filename
                download.save_as(str(target))
                print("downloaded:", target)
                context.close()
                return 0
            except PlaywrightTimeoutError:
                print("download_timeout")
            except Exception as exc:  # noqa: BLE001
                print("download_error:", repr(exc))
            page.wait_for_timeout(3000)
            print("post_click_url:", page.url)
            print("context_pages:", len(context.pages), "previous_pages:", existing_pages)
            for index, extra_page in enumerate(context.pages, start=1):
                print("page", index, "url:", extra_page.url, "title:", extra_page.title())
            try:
                page.emulate_media(media="print")
                page.pdf(
                    path=str(pdf_target),
                    format="A4",
                    margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
                    print_background=True,
                )
                print("page_pdf:", pdf_target)
            except Exception as exc:  # noqa: BLE001
                print("page_pdf_error:", repr(exc))
            print("snippet:", page.content()[:1000].replace("\n", " ").replace("\r", " "))
            break
        context.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

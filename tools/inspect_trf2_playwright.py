from __future__ import annotations

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


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    out_dir = Path("outputs/playwright-inspect")
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        for headless in (True, False):
            for attempt in range(1, 4):
                print("headless:", headless, "attempt:", attempt)
                browser = pw.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    accept_downloads=True,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/137.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 1200},
                    locale="pt-BR",
                )
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)
                    title = page.title()
                    print("page_url:", page.url)
                    print("title:", title)
                    if "429" in title or "Too Many Requests" in title:
                        print("rate_limited: yes")
                        browser.close()
                        time.sleep(5 * attempt)
                        continue
                    form_action = page.locator("form[action*='minuta_imprimir']").first.get_attribute("action")
                    print("form_action:", form_action)
                    try:
                        with page.expect_download(timeout=15000) as download_info:
                            page.locator("input[name='btnImprimir']").first.click()
                        download = download_info.value
                        suggested = download.suggested_filename
                        target = out_dir / suggested
                        download.save_as(str(target))
                        print("downloaded:", target)
                    except PlaywrightTimeoutError:
                        print("downloaded: none")
                    except Exception as exc:  # noqa: BLE001
                        print("download_error:", repr(exc))
                    print("final_page_url:", page.url)
                    print("content_snippet:", page.content()[:1000].replace("\n", " ").replace("\r", " "))
                    browser.close()
                    return 0
                except Exception as exc:  # noqa: BLE001
                    print("page_error:", repr(exc))
                    browser.close()
                    time.sleep(3 * attempt)
                    continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

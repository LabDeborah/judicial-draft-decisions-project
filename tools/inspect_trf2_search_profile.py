from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

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


def main() -> int:
    profile_name = sys.argv[1] if len(sys.argv) > 1 else "Profile 1"
    chrome_user_data = Path.home() / "AppData/Local/Google/Chrome/User Data"
    temp_user_data = Path("outputs/playwright-profile-search") / profile_name
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
            page.goto(SEARCH_URL, wait_until="commit", timeout=60000)
            page.wait_for_timeout(6000)
            title = page.title()
            print("attempt:", attempt, "title:", title, "url:", page.url)
            if "429" in title or "Too Many Requests" in title:
                time.sleep(8 * attempt)
                continue
            forms = page.locator("form")
            print("forms:", forms.count())
            for index in range(forms.count()):
                form = forms.nth(index)
                print("form", index + 1, "action:", form.get_attribute("action"))
            inputs = page.locator("input, select, textarea")
            count = min(inputs.count(), 40)
            print("fields:", count)
            for index in range(count):
                field = inputs.nth(index)
                print(
                    "field",
                    index + 1,
                    "name:",
                    field.get_attribute("name"),
                    "type:",
                    field.get_attribute("type"),
                    "value:",
                    field.get_attribute("value"),
                    "placeholder:",
                    field.get_attribute("placeholder"),
                    "aria:",
                    field.get_attribute("aria-label"),
                )
                if 4 <= index <= 8:
                    try:
                        locator = field.locator("xpath=ancestor::*[self::td or self::div][1]")
                        print("field_context:", locator.inner_text(timeout=2000))
                    except Exception:
                        pass
            buttons = page.locator("button, input[type='submit'], input[type='button']")
            button_count = min(buttons.count(), 20)
            print("buttons:", button_count)
            for index in range(button_count):
                button = buttons.nth(index)
                print(
                    "button",
                    index + 1,
                    "text:",
                    button.inner_text() if button.evaluate("el => el.tagName") == "BUTTON" else "",
                    "name:",
                    button.get_attribute("name"),
                    "type:",
                    button.get_attribute("type"),
                    "value:",
                    button.get_attribute("value"),
                    "onclick:",
                    button.get_attribute("onclick"),
                )
            print("snippet:", page.content()[:1500].replace("\n", " ").replace("\r", " "))
            context.close()
            return 0
        context.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

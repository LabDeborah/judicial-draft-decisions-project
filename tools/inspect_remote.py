from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python tools/inspect_remote.py <url>")
        return 1

    url = sys.argv[1]
    response = requests.get(
        url,
        timeout=45,
        headers={"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"},
        allow_redirects=True,
    )
    print("status:", response.status_code)
    print("final_url:", response.url)
    print("content_type:", response.headers.get("content-type", ""))
    print("length:", len(response.text))

    soup = BeautifulSoup(response.text, "html.parser")
    print("title:", (soup.title.get_text(" ", strip=True) if soup.title else ""))
    snippet = response.text[:2000].replace("\n", " ").replace("\r", " ")
    print("snippet:", snippet)

    for index, form in enumerate(soup.find_all("form"), start=1):
        print(f"FORM {index}: action={form.get('action', '')} method={form.get('method', '')}")
        for field in form.find_all(["input", "select", "textarea"]):
            name = field.get("name", "")
            value = field.get("value", "")
            field_type = field.get("type", field.name)
            print(f"  field: name={name} type={field_type} value={value}")

    for index, anchor in enumerate(soup.find_all("a", href=True)[:100], start=1):
        href = anchor.get("href", "")
        label = anchor.get_text(" ", strip=True)
        print(f"LINK {index}: label={label} href={href}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

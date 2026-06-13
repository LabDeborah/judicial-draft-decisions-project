from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup


def main() -> int:
    process_digits = sys.argv[1] if len(sys.argv) > 1 else "200951510662123"
    url = "https://www.cjf.jus.br/phpdoc/virtus/pesqinteiroteor.php"
    payload = {
        "tipo": "num_pro",
        "pesq": process_digits,
        "nm_arq": "int_teor",
    }
    response = requests.post(
        url,
        data=payload,
        timeout=45,
        headers={"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"},
        allow_redirects=True,
    )
    print("status:", response.status_code)
    print("final_url:", response.url)
    print("content_type:", response.headers.get("content-type", ""))
    print("length:", len(response.text))
    snippet = response.text[:4000].replace("\n", " ").replace("\r", " ")
    print("snippet:", snippet)

    soup = BeautifulSoup(response.text, "html.parser")
    for index, anchor in enumerate(soup.find_all("a", href=True), start=1):
        href = anchor.get("href", "")
        label = anchor.get_text(" ", strip=True)
        print(f"LINK {index}: label={label} href={href}")
    for index, img in enumerate(soup.find_all("img"), start=1):
        print(f"IMG {index}: src={img.get('src', '')} alt={img.get('alt', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

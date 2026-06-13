from __future__ import annotations

import sys

import requests
import urllib3
from bs4 import BeautifulSoup


DEFAULT_URL = (
    "https://eproc-consulta.jfes.jus.br/eproc/controlador.php?"
    "acao=acessar_documento_publico&doc=501778688745446793190552401567&"
    "evento=501778688745446793190552408998&key=fb6d28563b55708b4c730cf036eebf3055b56e93a42979b1d837ce382ebb8fb0&"
    "hash=2041074924c73b69d642478ec9583c02"
)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    session = requests.Session()
    headers = {"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"}
    response = session.get(url, timeout=45, headers=headers)
    print("doc_status:", response.status_code)
    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form", action=lambda value: value and "minuta_imprimir" in value)
    if not form:
        print("print_form: not found")
        return 1
    payload = {}
    for field in form.find_all("input"):
        name = field.get("name", "")
        value = field.get("value", "")
        if name:
            payload[name] = value
    if "txtdochtml" in payload and not payload["txtdochtml"]:
        doc_div = soup.find(id="divInfraAreaDados") or soup.find(id="divdochtml") or soup.find("body")
        payload["txtdochtml"] = str(doc_div or "")
    print("payload_keys:", sorted(payload))
    action = form.get("action", "")
    print_url = requests.compat.urljoin(url, action)
    print("print_url:", print_url)
    print_response = session.post(print_url, data=payload, timeout=60, headers=headers, allow_redirects=False)
    print("print_status:", print_response.status_code)
    print("print_type:", print_response.headers.get("content-type", ""))
    print("location:", print_response.headers.get("location", ""))
    print("print_len:", len(print_response.content))
    if print_response.is_redirect and print_response.headers.get("location"):
        location = requests.compat.urljoin(print_url, print_response.headers["location"])
        print("manual_follow:", location)
        manager = urllib3.PoolManager()
        redirected = manager.request("GET", location, headers=headers, redirect=False)
        print("redirect_status:", redirected.status)
        print("redirect_type:", redirected.headers.get("content-type", ""))
        print("redirect_location:", redirected.headers.get("location", ""))
        print("redirect_len:", len(redirected.data))
        if redirected.headers.get("location"):
            third_url = requests.compat.urljoin(location, redirected.headers["location"])
            print("third_url:", third_url)
    elif "text" in (print_response.headers.get("content-type", "") or "").lower():
        print(print_response.text[:500].replace("\n", " ").replace("\r", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup


def main() -> int:
    urls = (
        sys.argv[1:]
        or [
            "https://eproc.jfes.jus.br/eproc/externo_controlador.php?acao=processo_seleciona_publica&acao_origem=processo_consulta_publica&acao_retorno=processo_consulta_publica&num_processo=50012975120244025002",
            "https://eproc.jfes.jus.br/eproc/externo_controlador.php?acao=processo_seleciona_publica&acao_origem=processo_consulta_publica&acao_retorno=processo_consulta_publica&num_processo=50363985520244025001",
        ]
    )
    for url in urls:
        response = requests.get(
            url,
            timeout=30,
            headers={"user-agent": "Mozilla/5.0 (compatible; TCC-Bot/0.1)"},
        )
        print("URL:", url)
        print("status:", response.status_code)
        print("final_url:", response.url)
        print("len:", len(response.text))
        text = response.text[:2000].replace("\n", " ")
        print("head:", text)
        soup = BeautifulSoup(response.text, "html.parser")
        for element_id in ["txtClasse", "txtAutuacao", "txtOrgaoJulgador", "txtMagistrado", "fldAssuntos"]:
            node = soup.find(id=element_id)
            print(element_id, bool(node), (node.get_text(" ", strip=True)[:300] if node else ""))
        print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

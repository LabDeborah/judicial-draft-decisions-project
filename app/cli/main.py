from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv

from app.core.config import parse_args
from app.core.pipeline import run_pipeline


def _load_dotenv_with_fallbacks() -> None:
    env_file = Path(".env")
    if not env_file.exists():
        return
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            load_dotenv(dotenv_path=env_file, encoding=encoding)
            return
        except UnicodeDecodeError:
            continue
    load_dotenv(dotenv_path=env_file, encoding="utf-8")


def main() -> None:
    _load_dotenv_with_fallbacks()
    config = parse_args(sys.argv[1:])
    summary = run_pipeline(config)

    print("Pipeline concluida.")
    print(f"Modo: {config.mode}")
    if config.mode == "import":
        print(f"Import root: {config.import_root or 'nao informado'}")
        print(f"TNU CSV: {config.import_tnu_csv_file or 'nao informado'}")
        print(f"TRF2 CSV: {config.import_trf2_csv_file or 'nao informado'}")
    print(f"Modo de analise: {config.analysis_mode}")
    print(f"Limite de analise: {config.analysis_limit or 'auto'}")
    print(f"Browser automation: {config.browser_automation}")
    print(f"Perfil Chrome TRF2: {config.trf2_chrome_profile or 'auto'}")
    print(f"Compilar PDF: {config.compile_pdf}")
    print(f"Engine LaTeX: {config.latex_engine or 'auto'}")
    print(f"Modelo Gemini: {config.gemini_model}")
    print(f"Delay Gemini (ms): {config.gemini_delay_ms}")
    print(f"Cooldown Gemini 429 (ms): {config.gemini_cooldown_ms}")
    print(f"Limiar 429 consecutivo: {config.gemini_429_threshold}")
    print(f"Max erros de quota Gemini: {config.gemini_max_quota_errors}")
    print(f"Arquivo de cache Gemini: {config.gemini_cache_file}")
    print(f"Limite Gemini req/min: {config.gemini_requests_per_minute}")
    print(f"Limite Gemini req/dia: {config.gemini_requests_per_day}")
    print(f"Arquivo de estado de quota: {config.gemini_quota_state_file}")
    print(f"Diretorio da execucao: {summary.run_dir}")
    print(f"Temas coletados: {summary.themes}")
    print(f"Decisoes coletadas: {summary.decisions}")
    print(f"Analises produzidas: {summary.analyses}")
    print(f"Minutas geradas (.tex): {summary.generated_drafts}")
    print(f"Minutas compiladas (.pdf): {summary.generated_pdfs}")
    print(f"Grafos semanticos por minuta: {summary.semantic_documents}")
    print(f"Grafo semantico da execucao: {summary.semantic_execution_graph}")
    print(f"Diretorio CSV de dados: {summary.data_csv_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Falha na execucao: {error}", file=sys.stderr)
        raise SystemExit(1)

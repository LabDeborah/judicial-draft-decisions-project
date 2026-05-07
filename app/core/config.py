from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Sequence

from app.domain.types import AnalysisMode, CollectionMode


@dataclass(slots=True)
class CliConfig:
    mode: CollectionMode
    analysis_mode: AnalysisMode
    limit: int
    import_root: str | None
    import_tnu_csv_file: str | None
    import_trf2_csv_file: str | None
    browser_automation: bool
    compile_pdf: bool
    latex_engine: str | None
    gemini_model: str
    gemini_delay_ms: int
    gemini_cooldown_ms: int
    gemini_429_threshold: int
    gemini_max_quota_errors: int
    gemini_cache_file: str
    gemini_requests_per_minute: int
    gemini_requests_per_day: int
    gemini_quota_state_file: str


def parse_args(argv: Sequence[str]) -> CliConfig:
    mode_raw = _read_arg_value(argv, "--mode") or "sample"
    if mode_raw == "live":
        mode: CollectionMode = "live"
    elif mode_raw == "import":
        mode = "import"
    else:
        mode = "sample"
    analysis_raw = _read_arg_value(argv, "--analysis-mode") or "local"
    analysis_mode: AnalysisMode = "gemini" if analysis_raw == "gemini" else "local"

    limit = _to_int(_read_arg_value(argv, "--limit") or "20", "--limit")
    import_root = (_read_arg_value(argv, "--import-root") or "").strip() or None
    import_tnu_csv_file = (_read_arg_value(argv, "--tnu-csv-file") or "").strip() or None
    import_trf2_csv_file = (_read_arg_value(argv, "--trf2-csv-file") or "").strip() or None
    browser_automation = _to_bool(
        _read_arg_value(argv, "--browser-automation") or "true",
        "--browser-automation",
    )
    compile_pdf = _to_bool(_read_arg_value(argv, "--compile-pdf") or "true", "--compile-pdf")
    latex_engine = (_read_arg_value(argv, "--latex-engine") or "").strip() or None
    gemini_model = _read_arg_value(argv, "--gemini-model") or "gemini-flash-lite-latest"
    gemini_delay_ms = _to_int(_read_arg_value(argv, "--gemini-delay-ms") or "1200", "--gemini-delay-ms")
    gemini_cooldown_ms = _to_int(
        _read_arg_value(argv, "--gemini-cooldown-ms") or "15000", "--gemini-cooldown-ms"
    )
    gemini_429_threshold = _to_int(
        _read_arg_value(argv, "--gemini-429-threshold") or "2", "--gemini-429-threshold"
    )
    gemini_max_quota_errors = _to_int(
        _read_arg_value(argv, "--gemini-max-quota-errors") or "2", "--gemini-max-quota-errors"
    )
    gemini_cache_file = _read_arg_value(argv, "--gemini-cache-file") or "outputs/reports/gemini_cache.json"
    gemini_requests_per_minute = _to_int(
        _read_arg_value(argv, "--gemini-requests-per-minute") or "15", "--gemini-requests-per-minute"
    )
    gemini_requests_per_day = _to_int(
        _read_arg_value(argv, "--gemini-requests-per-day") or "500", "--gemini-requests-per-day"
    )
    gemini_quota_state_file = (
        _read_arg_value(argv, "--gemini-quota-state-file") or "outputs/reports/gemini_quota_state.json"
    )

    if limit <= 0:
        raise ValueError("Parametro --limit invalido. Use um inteiro positivo.")
    if gemini_delay_ms < 0:
        raise ValueError("Parametro --gemini-delay-ms invalido. Use inteiro >= 0.")
    if gemini_cooldown_ms < 0:
        raise ValueError("Parametro --gemini-cooldown-ms invalido. Use inteiro >= 0.")
    if gemini_429_threshold <= 0:
        raise ValueError("Parametro --gemini-429-threshold invalido. Use inteiro > 0.")
    if gemini_max_quota_errors <= 0:
        raise ValueError("Parametro --gemini-max-quota-errors invalido. Use inteiro > 0.")
    if gemini_requests_per_minute <= 0:
        raise ValueError("Parametro --gemini-requests-per-minute invalido. Use inteiro > 0.")
    if gemini_requests_per_day <= 0:
        raise ValueError("Parametro --gemini-requests-per-day invalido. Use inteiro > 0.")
    if mode == "import":
        if import_root:
            import_tnu_csv_file = import_tnu_csv_file or os.path.join(import_root, "tnu", "temas-tnu.csv")
            import_trf2_csv_file = import_trf2_csv_file or os.path.join(import_root, "trf2", "decisoes.csv")
            if not os.path.exists(import_tnu_csv_file) or not os.path.exists(import_trf2_csv_file):
                nested_root = os.path.join(import_root, "TCC")
                nested_tnu = os.path.join(nested_root, "tnu", "temas-tnu.csv")
                nested_trf2 = os.path.join(nested_root, "trf2", "decisoes.csv")
                if os.path.exists(nested_tnu) and os.path.exists(nested_trf2):
                    import_tnu_csv_file = nested_tnu
                    import_trf2_csv_file = nested_trf2
            if not os.path.exists(import_tnu_csv_file) or not os.path.exists(import_trf2_csv_file):
                tnu_zip = _pick_first(glob.glob(os.path.join(import_root, "tnu-*.zip")))
                trf2_zip = _pick_first(glob.glob(os.path.join(import_root, "trf2-*.zip")))
                if tnu_zip and trf2_zip:
                    import_tnu_csv_file = f"zip::{tnu_zip}::tnu/temas-tnu.csv"
                    import_trf2_csv_file = f"zip::{trf2_zip}::trf2/decisoes.csv"
        if not import_tnu_csv_file or not import_trf2_csv_file:
            raise ValueError(
                "Modo import requer --import-root ou ambos --tnu-csv-file e --trf2-csv-file."
            )
        if not _import_source_exists(import_tnu_csv_file):
            raise ValueError(f"Arquivo nao encontrado: {import_tnu_csv_file}")
        if not _import_source_exists(import_trf2_csv_file):
            raise ValueError(f"Arquivo nao encontrado: {import_trf2_csv_file}")

    return CliConfig(
        mode=mode,
        analysis_mode=analysis_mode,
        limit=limit,
        import_root=import_root,
        import_tnu_csv_file=import_tnu_csv_file,
        import_trf2_csv_file=import_trf2_csv_file,
        browser_automation=browser_automation,
        compile_pdf=compile_pdf,
        latex_engine=latex_engine,
        gemini_model=gemini_model,
        gemini_delay_ms=gemini_delay_ms,
        gemini_cooldown_ms=gemini_cooldown_ms,
        gemini_429_threshold=gemini_429_threshold,
        gemini_max_quota_errors=gemini_max_quota_errors,
        gemini_cache_file=gemini_cache_file,
        gemini_requests_per_minute=gemini_requests_per_minute,
        gemini_requests_per_day=gemini_requests_per_day,
        gemini_quota_state_file=gemini_quota_state_file,
    )


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Variavel de ambiente ausente: {name}")
    return value


def _read_arg_value(argv: Sequence[str], key: str) -> str | None:
    try:
        idx = list(argv).index(key)
    except ValueError:
        return None
    return argv[idx + 1] if idx + 1 < len(argv) else None


def _to_int(value: str, arg_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Parametro {arg_name} invalido.") from exc


def _to_bool(value: str, arg_name: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "sim", "on"):
        return True
    if lowered in ("0", "false", "no", "nao", "off"):
        return False
    raise ValueError(f"Parametro {arg_name} invalido. Use true/false.")


def _import_source_exists(source: str) -> bool:
    if source.startswith("zip::"):
        parts = source.split("::", 2)
        if len(parts) != 3:
            return False
        return os.path.exists(parts[1])
    return os.path.exists(source)


def _pick_first(items: list[str]) -> str | None:
    return sorted(items)[0] if items else None

from __future__ import annotations

import csv
from io import StringIO

from app.utils.text import normalize_text
from app.utils.fs import write_text


def write_csv(output_path: str, records: list[dict]) -> None:
    headers = _collect_headers(records)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in records:
        writer.writerow({header: _to_cell(row.get(header)) for header in headers})
    write_text(output_path, buffer.getvalue())


def _collect_headers(records: list[dict]) -> list[str]:
    keys: list[str] = []
    for rec in records:
        for key in rec.keys():
            if key not in keys:
                keys.append(key)
    return keys


def _to_cell(value) -> str:
    if value is None:
        return ""
    return normalize_text(str(value))

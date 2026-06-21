from __future__ import annotations

import uuid

UUID_NAMESPACE = uuid.UUID("0aa58434-7aaf-4f26-a312-3fd5446b6d63")


def stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, "::".join(part.strip() for part in parts if part and part.strip())))


def process_uuid(process_number: str, fallback: str = "") -> str:
    source = process_number.strip() if process_number else fallback.strip()
    return stable_uuid("process", source)


def generated_decision_uuid(process_number: str, action: str, fallback: str = "") -> str:
    source = process_number.strip() if process_number else fallback.strip()
    return stable_uuid("generated-decision", source, action)

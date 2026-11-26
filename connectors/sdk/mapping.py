"""Declarative YAML field-mapping engine (plan §10, Phase 3, T3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FieldMap:
    canonical: str
    source: str
    transform: str | None = None


@dataclass(frozen=True)
class RecordMapping:
    record_type: str
    id_field: str
    fields: tuple[FieldMap, ...]


def _to_date(value: Any) -> Any:
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _to_datetime(value: Any) -> Any:
    if value is None or isinstance(value, datetime):
        return value
    return _to_date(value) if isinstance(value, date) else None or _parse_datetime(value)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _apply(value: Any, transform: str | None) -> Any:
    if value is None:
        return None
    if transform == "iso_date":
        return _to_date(value)
    if transform == "iso_datetime":
        return _to_datetime(value)
    if transform in {"lower", "upper"}:
        return str(value).lower() if transform == "lower" else str(value).upper()
    if transform == "strip":
        return str(value).strip()
    if transform == "int":
        return int(value) if str(value).strip() != "" else None
    if transform == "float":
        return float(value) if str(value).strip() != "" else None
    return value


class MappingEngine:
    """Maps raw system-of-record fields onto canonical fields via YAML."""

    def __init__(self, mappings: dict[str, RecordMapping]):
        self._mappings = mappings

    @classmethod
    def load(cls, path: Path) -> MappingEngine:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        mappings: dict[str, RecordMapping] = {}
        for item in raw.get("mappings", []):
            fields = tuple(
                FieldMap(
                    canonical=field["canonical"],
                    source=field["source"],
                    transform=field.get("transform"),
                )
                for field in item.get("fields", [])
            )
            mappings[item["record_type"]] = RecordMapping(
                record_type=item["record_type"],
                id_field=item["id_field"],
                fields=fields,
            )
        return cls(mappings)

    def mapping_for(self, record_type: str) -> RecordMapping:
        mapping = self._mappings.get(record_type)
        if mapping is None:
            raise ValueError(f"No mapping for record type: {record_type}")
        return mapping

    def apply(self, record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        mapping = self.mapping_for(record_type)
        return {field.canonical: _apply(payload.get(field.source), field.transform) for field in mapping.fields}

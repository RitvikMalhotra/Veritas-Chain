"""Parses FIR text files into header fields and the narrative the extractors read."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

NARRATIVE_MARKER = "NARRATIVE"

_HEADER_FIELDS = {
    "FIR No": "fir_id",
    "Police Station": "police_station",
    "Date and Time of Report": "reported_at",
    "Date and Time of Occurrence": "occurred_at",
    "Acts and Sections": "sections",
    "Investigating Officer": "officer",
}


@dataclass(frozen=True)
class FirDocument:
    fir_id: str
    police_station: str
    reported_at: datetime
    occurred_at: datetime
    sections: str
    officer: str  # header metadata only; officers are not extracted as network entities
    narrative: str  # extraction runs on this text; all offsets are relative to it


def parse_fir(text: str) -> FirDocument:
    lines = text.splitlines()
    if NARRATIVE_MARKER not in lines:
        raise ValueError("FIR has no NARRATIVE section")
    marker = lines.index(NARRATIVE_MARKER)
    fields: dict[str, str] = {}
    for line in lines[:marker]:
        key, sep, value = line.partition(": ")
        if sep and key in _HEADER_FIELDS:
            fields[_HEADER_FIELDS[key]] = value.strip()
    missing = sorted(set(_HEADER_FIELDS.values()) - fields.keys())
    if missing:
        raise ValueError(f"FIR header is missing: {missing}")
    return FirDocument(
        fir_id=fields["fir_id"],
        police_station=fields["police_station"],
        reported_at=datetime.fromisoformat(fields["reported_at"]),
        occurred_at=datetime.fromisoformat(fields["occurred_at"]),
        sections=fields["sections"],
        officer=fields["officer"],
        narrative="\n".join(lines[marker + 1:]).rstrip(),  # rstrip only, so start offsets are unchanged
    )


def load_firs(folder: Path) -> list[FirDocument]:
    return [parse_fir(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("FIR-*.txt"))]

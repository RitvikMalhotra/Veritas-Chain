"""Regex extraction for phone numbers and vehicle plates (deliberately not NER)."""

from __future__ import annotations

import re

from veritas import normalize
from veritas.models import EntityMention, MentionMethod, NodeType

# Why regex here: phone numbers and plates follow fixed national formats, so a pattern plus a validity check is
# near-deterministic and explainable. Generic NER models label them inconsistently (CARDINAL, ORG, or nothing).

# Indian mobile: optional +91 / 0091 / 0 prefix, then 10 digits starting 6-9, optionally split 5+5.
# A bare "91" prefix (919876543210) is deliberately not matched: in free text it is indistinguishable from a 12-digit account number.
_PHONE = re.compile(r"(?<![\w+])(?:(?:\+91|0091)[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")

# Standard plate: state code, RTO number, 0-3 series letters, 4-digit number; parts may be split by space or hyphen.
_PLATE = re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?(?:[A-Z]{1,3}[\s-]?)?\d{4}\b")

# Bharat-series plate, e.g. 22 BH 1234 AA.
_PLATE_BH = re.compile(r"\b\d{2}[\s-]?BH[\s-]?\d{4}[\s-]?[A-Z]{1,2}\b")


def _mentions(document_id: str, text: str, pattern: re.Pattern, node_type: NodeType, validate) -> list[EntityMention]:
    found = []
    for match in pattern.finditer(text):
        try:
            validate(match.group())  # a pattern hit that fails the Phase 0 normalizer is not emitted
        except ValueError:
            continue
        found.append(EntityMention(document_id=document_id, node_type=node_type, text=match.group(),
                                   start_char=match.start(), end_char=match.end(), method=MentionMethod.REGEX))
    return found


def find_phones(document_id: str, text: str) -> list[EntityMention]:
    return _mentions(document_id, text, _PHONE, NodeType.PHONE, normalize.phone_key)


def find_plates(document_id: str, text: str) -> list[EntityMention]:
    return (_mentions(document_id, text, _PLATE, NodeType.VEHICLE, normalize.plate_key)
            + _mentions(document_id, text, _PLATE_BH, NodeType.VEHICLE, normalize.plate_key))

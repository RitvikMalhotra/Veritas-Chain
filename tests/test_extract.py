"""Phase 2 tests: FIR parsing, regex extractors, merge rules and the scoring code."""

import importlib.util
import json
from pathlib import Path

import pytest

from veritas.extract.documents import load_firs, parse_fir
from veritas.extract.evaluate import score_document
from veritas.extract.patterns import find_phones, find_plates
from veritas.extract.pipeline import DEFAULT_MODEL, NerCandidate, canonical_key, merge
from veritas.models import EntityMention, NodeType

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = """[SYNTHETIC RECORD - generated test data, not a real case]
FIR No: FIR-TST-2025-0001
Police Station: Kurla Police Station, Mumbai
Date and Time of Report: 2025-01-27T01:12:00+05:30
Date and Time of Occurrence: 2025-01-26T23:12:00+05:30
Acts and Sections: BNS 2023 s.303(2)
Investigating Officer: SI Test Officer

NARRATIVE
Ravi Kumar (mobile no. 98765 43210) saw MH-12-AB-1234 near the market.
"""


# ---------- FIR parsing ----------


def test_parse_fir_header_and_narrative():
    doc = parse_fir(SAMPLE)
    assert doc.fir_id == "FIR-TST-2025-0001"
    assert doc.occurred_at.utcoffset().total_seconds() == 5.5 * 3600
    assert doc.officer == "SI Test Officer"
    assert doc.narrative.startswith("Ravi Kumar") and doc.narrative.endswith("market.")


def test_parse_fir_rejects_missing_parts():
    with pytest.raises(ValueError, match="NARRATIVE"):
        parse_fir(SAMPLE.replace("NARRATIVE", "BODY"))
    with pytest.raises(ValueError, match="missing"):
        parse_fir(SAMPLE.replace("FIR No: FIR-TST-2025-0001\n", ""))


def test_parsed_narratives_line_up_with_ground_truth_offsets():
    truth = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))
    docs = {d.fir_id: d for d in load_firs(ROOT / "data" / "firs")}
    for fir_id, ann in truth["fir_annotations"]["reports"].items():
        for m in ann["mentions"]:
            assert docs[fir_id].narrative[m["start"]:m["end"]] == m["text"]


# ---------- Regex extractors ----------


@pytest.mark.parametrize("surface", ["9876543210", "98765 43210", "+91-9876543210", "09876543210",
                                     "+91 98765 43210", "0091-98765-43210"])
def test_phone_formats_found_with_exact_span(surface):
    text = f"contacted on {surface}, then left"
    [m] = find_phones("D", text)
    assert m.text == surface and text[m.start_char:m.end_char] == surface


@pytest.mark.parametrize("text", ["paid ₹3,50,000 in cash", "240 grams recovered", "account 123456789012 frozen",
                                  "number 5876543210 is invalid", "call +1 415 555 0100", "at about 23:12 hours",
                                  "ref 98765432101234"])
def test_phone_non_matches(text):
    assert find_phones("D", text) == []


def test_bare_91_prefix_not_matched_by_design():
    assert find_phones("D", "called 919876543210 twice") == []


@pytest.mark.parametrize("surface", ["MH-12-AB-1234", "MH 12 AB 1234", "MH12AB1234", "DL 5 SU 8739", "MH 12 V 9289",
                                     "DL-3-CAB-1234", "22 BH 1234 AA"])
def test_plate_formats_found(surface):
    [m] = find_plates("D", f"a car bearing registration number {surface} was seen")
    assert m.text == surface


@pytest.mark.parametrize("text", ["under NDPS Act 1985", "IT Act 2000 s.66D", "KYC had expired", "reached MH 12 yesterday",
                                  "BNS 2023 s.303(2)"])
def test_plate_non_matches(text):
    assert find_plates("D", text) == []


def test_regex_finds_every_planted_phone_and_plate_exactly():
    # Consistency check only: the regexes and the generator's surface formats were written together.
    truth = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))
    for doc in load_firs(ROOT / "data" / "firs"):
        gold = {(m["start"], m["end"], m["node_type"]) for m in truth["fir_annotations"]["reports"][doc.fir_id]["mentions"]
                if m["node_type"] in ("Phone", "Vehicle")}
        found = {(m.start_char, m.end_char, str(m.node_type))
                 for m in find_phones(doc.fir_id, doc.narrative) + find_plates(doc.fir_id, doc.narrative)}
        assert found == gold, doc.fir_id


# ---------- Merge rules ----------


def test_merge_prefers_regex_over_overlapping_ner_and_drops_unmapped_labels():
    text = "Ravi Kumar called 98765 43210 on Monday"
    regex = find_phones("D", text)
    candidates = [NerCandidate("Ravi Kumar", "PERSON", 0, 10), NerCandidate("98765", "CARDINAL", 18, 23),
                  NerCandidate("43210", "ORG", 24, 29), NerCandidate("Monday", "DATE", 33, 39)]
    records = merge("D", regex, candidates)
    assert [(r["text"], r["node_type"], r["method"]) for r in records] == [
        ("Ravi Kumar", "Person", "spacy_ner"), ("98765 43210", "Phone", "regex")]
    assert records[0]["confidence"] == 0.92 and records[1]["confidence"] == 0.95  # per-label Person value
    assert records[1]["canonical_key"] == "+919876543210"


def test_merge_output_matches_mention_contract():
    records = merge("D", [], [NerCandidate("Kurla", "GPE", 5, 10)])
    fields = {k: v for k, v in records[0].items() if k not in ("raw_label", "canonical_key")}
    assert EntityMention(**fields).node_type == NodeType.LOCATION


def test_canonical_key_none_when_nothing_to_key():
    assert canonical_key(NodeType.PERSON, "Smt.") is None
    assert canonical_key(NodeType.PERSON, "Shri Rahul Sharma") == "rahul_sharma"


# ---------- Scoring ----------


def _pred(text, start, node_type, label="X"):
    return {"text": text, "start_char": start, "end_char": start + len(text), "node_type": node_type, "raw_label": label}


def test_score_document_counts_each_error_kind():
    gold = [{"text": "Rahul Sharma", "start": 5, "end": 17, "node_type": "Person"},
            {"text": "Balan Warehouse", "start": 30, "end": 45, "node_type": "Location"},
            {"text": "Pune", "start": 50, "end": 54, "node_type": "Location"},
            {"text": "Laksh Konda", "start": 60, "end": 71, "node_type": "Person"}]
    predicted = [_pred("Shri Rahul Sharma", 0, "Person", "PERSON"),     # boundary error, same key
                 _pred("Balan Warehouse", 30, "Organization", "ORG"),   # wrong type
                 _pred("Pune", 50, "Location", "GPE"),                  # exact
                 _pred("KYC", 80, "Organization", "ORG")]               # false positive; Laksh Konda missed
    result = score_document(gold, predicted)
    person, location, org = (result["counts"][t] for t in ("Person", "Location", "Organization"))
    assert (person["strict_tp"], person["lenient_tp"], person["same_key_tp"]) == (0, 1, 1)
    assert (location["strict_tp"], location["lenient_tp"]) == (1, 1)
    assert (org["predicted"], org["lenient_tp"]) == (2, 0)
    errors = result["errors"]
    assert [e["text"] for e in errors["wrong_type"]] == ["Balan Warehouse"]
    assert [e["text"] for e in errors["false_positive"]] == ["KYC"]
    assert sorted(e["text"] for e in errors["false_negative"]) == ["Balan Warehouse", "Laksh Konda"]
    assert [e["predicted"] for e in errors["boundary"]] == ["Shri Rahul Sharma"]


# ---------- spaCy end to end (skipped if the model isn't installed) ----------


@pytest.mark.skipif(importlib.util.find_spec(DEFAULT_MODEL) is None, reason=f"{DEFAULT_MODEL} not installed")
def test_extractor_output_is_valid_and_span_exact():
    from veritas.extract.pipeline import Extractor

    extractor = Extractor()
    for doc in load_firs(ROOT / "data" / "firs")[:3]:
        records = extractor.extract(doc)
        assert records
        for r in records:
            assert doc.narrative[r["start_char"]:r["end_char"]] == r["text"]
            EntityMention(**{k: v for k, v in r.items() if k not in ("raw_label", "canonical_key")})

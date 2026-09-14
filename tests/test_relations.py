"""Relation extraction tests: sentence splitting, references, each rule family, confidence and co-occurrence."""

import json
from pathlib import Path

from veritas.extract.relation_eval import challenge_cases
from veritas.extract.relations import Mention, interpret_document, split_sentences
from veritas.models import EDGE_ADAPTER

ROOT = Path(__file__).resolve().parents[1]
EVENT = "Event:doc"


def run(text, entities):
    records, pos = [], 0
    for surface, node_type in entities:  # entities listed in order of appearance
        start = text.index(surface, pos)
        records.append({"text": surface, "node_type": node_type, "start": start, "end": start + len(surface)})
        pos = start + len(surface)
    return interpret_document("DOC", text, records, EVENT)


def pattern(result):
    return {(r.edge_type.value, r.source_id, r.target_id) for r in result.relations if r.method.value == "text_pattern"}


# ---------- Sentences ----------


def test_abbreviations_and_entity_periods_do_not_split_sentences():
    text = "Smt. Meena Iyer (mobile no. 98765 43210) works at Sai Traders Pvt Ltd. During questioning she left."
    mentions = [Mention(0, "Person", "Meena Iyer", 5, 15, 0.9), Mention(1, "Organization", "Sai Traders Pvt Ltd.", 50, 70, 0.3)]
    spans = split_sentences(text, mentions)
    assert [text[a:b] for a, b in spans] == [text[:70], "During questioning she left."]


# ---------- Phones and calls ----------


def test_uses_phone_cues():
    result = run("Ravi Kumar (mobile no. 98765 43210) met Amit Joshi, who uses mobile number 91234 56789. "
                 "Neha Rao can be contacted on mobile number 99887 76655.",
                 [("Ravi Kumar", "Person"), ("98765 43210", "Phone"), ("Amit Joshi", "Person"), ("91234 56789", "Phone"),
                  ("Neha Rao", "Person"), ("99887 76655", "Phone")])
    assert pattern(result) >= {("USES_PHONE", "Person:ravi_kumar", "Phone:+919876543210"),
                               ("USES_PHONE", "Person:amit_joshi", "Phone:+919123456789"),
                               ("USES_PHONE", "Person:neha_rao", "Phone:+919988776655")}


def test_caller_number_is_not_given_to_the_complainant():
    result = run("The complainant Ravi Kumar (mobile no. 98765 43210), who lives near Sai Market, Pune, reported that a "
                 "caller using mobile number 91234 56789 threatened the complainant.",
                 [("Ravi Kumar", "Person"), ("98765 43210", "Phone"), ("Sai Market", "Location"), ("Pune", "Location"),
                  ("91234 56789", "Phone")])
    assert pattern(result) == {("USES_PHONE", "Person:ravi_kumar", "Phone:+919876543210"),
                               ("CALLED", "Phone:+919123456789", "Phone:+919876543210")}


def test_decision_3_no_person_to_person_call_when_a_number_is_given():
    with_number = run("The complainant Ravi Kumar (mobile no. 98765 43210) reported that Ajay Rao called the complainant "
                      "from mobile number 91234 56789.",
                      [("Ravi Kumar", "Person"), ("98765 43210", "Phone"), ("Ajay Rao", "Person"), ("91234 56789", "Phone")])
    assert ("CALLED", "Phone:+919123456789", "Phone:+919876543210") in pattern(with_number)
    assert ("USES_PHONE", "Person:ajay_rao", "Phone:+919123456789") in pattern(with_number)
    assert not any(t == "CALLED" and s.startswith("Person:") for t, s, _ in pattern(with_number))
    without_number = run("Sanjay Verma called Arjun Mehta twice.", [("Sanjay Verma", "Person"), ("Arjun Mehta", "Person")])
    assert pattern(without_number) == {("CALLED", "Person:sanjay_verma", "Person:arjun_mehta")}


# ---------- Organisations, places, vehicles ----------


def test_works_at_keeps_the_employer_an_organization():
    # Regression: an optional city once turned "works at X" into a Location and dropped MEMBER_OF.
    result = run("Neha Rao, who works at Sai Traders, was questioned.", [("Neha Rao", "Person"), ("Sai Traders", "Organization")])
    assert pattern(result) == {("MEMBER_OF", "Person:neha_rao", "Organization:sai_traders")}
    assert [e.node_type.value for e in result.entities] == ["Person", "Organization"]


def test_business_in_a_place_phrase_becomes_a_location_with_city():
    result = run("Amit Joshi had met Ravi Kumar and Neha Rao at Sai Dhaba, Pune on Monday.",
                 [("Amit Joshi", "Person"), ("Ravi Kumar", "Person"), ("Neha Rao", "Person"), ("Sai Dhaba", "Organization"),
                  ("Pune", "Location")])
    place = "Location:sai_dhaba:pune"
    assert pattern(result) == {("MET_AT", p, place) for p in ("Person:amit_joshi", "Person:ravi_kumar", "Person:neha_rao")}
    city = next(e for e in result.entities if e.name == "Pune")
    assert city.is_city_of_place


def test_vehicle_reference_and_presence():
    result = run("A white Tata Ace bearing registration number MH-12-AB-1234 was found parked at the spot. "
                 "As per records, the vehicle is registered to Ravi Kumar, a director of Sai Traders.",
                 [("MH-12-AB-1234", "Vehicle"), ("Ravi Kumar", "Person"), ("Sai Traders", "Organization")])
    assert pattern(result) == {("PRESENT_AT_EVENT", "Vehicle:MH12AB1234", EVENT),
                               ("OWNS_VEHICLE", "Person:ravi_kumar", "Vehicle:MH12AB1234"),
                               ("MEMBER_OF", "Person:ravi_kumar", "Organization:sai_traders")}


def test_presence_lists_and_appositives():
    result = run("Ravi Kumar, Amit Joshi and Neha Rao were detained. Karan Das, a director of Sai Traders, was also present.",
                 [("Ravi Kumar", "Person"), ("Amit Joshi", "Person"), ("Neha Rao", "Person"), ("Karan Das", "Person"),
                  ("Sai Traders", "Organization")])
    present = {s for t, s, d in pattern(result) if t == "PRESENT_AT_EVENT" and d == EVENT}
    assert present == {"Person:ravi_kumar", "Person:amit_joshi", "Person:neha_rao", "Person:karan_das"}


def test_cash_transfer_only_without_a_bank_channel():
    cash = run("Ravi Kumar paid ₹5,000 in cash to Amit Joshi.", [("Ravi Kumar", "Person"), ("Amit Joshi", "Person")])
    assert pattern(cash) == {("TRANSFERRED_MONEY_TO", "Person:ravi_kumar", "Person:amit_joshi")}
    upi = run("Ravi Kumar paid ₹5,000 in cash to Amit Joshi after a UPI attempt failed.",
              [("Ravi Kumar", "Person"), ("Amit Joshi", "Person")])
    assert pattern(upi) == set()


def test_type_mismatch_is_dropped():
    # spaCy tagging the employer as a Person must not produce Person->Person MEMBER_OF.
    result = run("Neha Rao, who works at Sai Traders, was questioned.", [("Neha Rao", "Person"), ("Sai Traders", "Person")])
    assert pattern(result) == set()


# ---------- Confidence and co-occurrence ----------


def test_confidence_is_capped_by_weakest_mention():
    result = run("Neha Rao, an employee of Sai Traders, was questioned.", [("Neha Rao", "Person"), ("Sai Traders", "Organization")])
    [member] = [r for r in result.relations if r.edge_type.value == "MEMBER_OF"]
    assert member.confidence == 0.29  # min(text_pattern 0.7, Person 0.92, Organization 0.29)


def test_cooccurrence_only_for_unlinked_people():
    result = run("Ravi Kumar paid ₹5,000 in cash to Amit Joshi while Neha Rao watched.",
                 [("Ravi Kumar", "Person"), ("Amit Joshi", "Person"), ("Neha Rao", "Person")])
    weak = {(r.source_id, r.target_id, r.confidence) for r in result.relations if r.method.value == "text_cooccurrence"}
    assert weak == {("Person:ravi_kumar", "Person:neha_rao", 0.4), ("Person:amit_joshi", "Person:neha_rao", 0.4)}


def test_every_relation_is_a_valid_schema_edge():
    result = run("The complainant Ravi Kumar (mobile no. 98765 43210) paid ₹20,000 in cash to Amit Joshi. "
                 "Amit Joshi came on a black Honda Activa bearing registration number DL 5 SU 8739.",
                 [("Ravi Kumar", "Person"), ("98765 43210", "Phone"), ("Amit Joshi", "Person"), ("Amit Joshi", "Person"),
                  ("DL 5 SU 8739", "Vehicle")])
    for r in result.relations:
        fields = {"type": r.edge_type, "source_id": r.source_id, "target_id": r.target_id,
                  "timestamp": "2025-01-01T00:00:00+05:30", "source_document_id": "DOC", "extraction_method": r.method,
                  "confidence": r.confidence}
        if r.edge_type.value == "ASSOCIATED_WITH":
            fields["context"] = "test"
        EDGE_ADAPTER.validate_python(fields)
    assert ("PRESENT_AT_EVENT", "Vehicle:DL5SU8739", EVENT) in pattern(result)


def test_challenge_fixture_is_well_formed():
    cases = challenge_cases(ROOT / "tests" / "fixtures" / "relation_challenge.json")
    assert len(cases) == 22 and len({c["id"] for c in cases}) == 22
    for case in cases:
        for record in case["records"]:
            assert case["text"][record["start"]:record["end"]] == record["text"]
        for edge_type, source, target in case["expected"]:
            assert source.split(":")[0] in ("Person", "Phone", "Vehicle")
            assert target == "EVENT" or ":" in target

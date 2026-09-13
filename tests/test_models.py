"""Schema tests: each test pins one rule from schema.md."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from veritas.config import get_confidence_settings
from veritas.models import (
    EDGE_ADAPTER,
    NODE_ADAPTER,
    AssociatedWith,
    BankAccount,
    Called,
    EntityMention,
    Location,
    MetAt,
    Organization,
    Person,
    Phone,
    TransferredMoneyTo,
    Vehicle,
)

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2025, 3, 14, 21, 5, tzinfo=IST)
DOC = ["CDR-000001"]


# ---------- Entity resolution keys ----------


@pytest.mark.parametrize("raw", ["+91 98765 43210", "09876543210", "919876543210", "0091-98765-43210", "9876543210"])
def test_phone_formats_resolve_to_one_node(raw):
    assert Phone(number=raw, source_document_ids=DOC).id == "Phone:+919876543210"


@pytest.mark.parametrize("raw", ["12345", "+91 5876543210", "+1 415 555 0100"])
def test_invalid_phone_rejected(raw):
    with pytest.raises(ValidationError):
        Phone(number=raw, source_document_ids=DOC)


def test_person_titles_case_and_punctuation_ignored():
    a = Person(name="Shri Rajesh  Kumar", source_document_ids=DOC)
    b = Person(name="rajesh kumar.", source_document_ids=DOC)
    assert a.id == b.id == "Person:rajesh_kumar"
    assert a.name == "Shri Rajesh  Kumar"  # display form is kept as given


def test_person_name_variants_do_not_merge():
    # Known limitation: exact match only, so initials and spelling variants stay separate.
    assert Person(name="R. Kumar", source_document_ids=DOC).id != Person(name="Rajesh Kumar", source_document_ids=DOC).id


def test_person_with_only_a_title_rejected():
    with pytest.raises(ValidationError):
        Person(name="Mr.", source_document_ids=DOC)


def test_location_city_prevents_cross_city_merge():
    pune = Location(name="Station Road", city="Pune", source_document_ids=DOC)
    nagpur = Location(name="Station Road", city="Nagpur", source_document_ids=DOC)
    assert pune.id != nagpur.id


def test_org_suffix_variants_merge():
    a = Organization(name="Sai Logistics Private Limited", source_document_ids=DOC)
    b = Organization(name="Sai Logistics Pvt. Ltd.", source_document_ids=DOC)
    assert a.id == b.id


@pytest.mark.parametrize("raw", ["MH-12-AB-1234", "mh 12 ab 1234", "MH12AB1234"])
def test_plate_formats_resolve_to_one_node(raw):
    assert Vehicle(registration_number=raw, source_document_ids=DOC).id == "Vehicle:MH12AB1234"


def test_bh_series_plate_accepted():
    assert Vehicle(registration_number="22 BH 1234 AA", source_document_ids=DOC).registration_number == "22BH1234AA"


def test_bank_account_key_includes_ifsc():
    a = BankAccount(ifsc="SBIN0001234", account_number="123456789012", source_document_ids=DOC)
    b = BankAccount(ifsc="HDFC0000456", account_number="123456789012", source_document_ids=DOC)
    assert a.id != b.id


def test_nodes_require_provenance():
    with pytest.raises(ValidationError):
        Person(name="Rajesh Kumar", source_document_ids=[])


# ---------- Edge rules ----------


def _call(**overrides):
    fields = dict(
        source_id="Phone:+919876543210",
        target_id="Phone:+919123456780",
        timestamp=T0,
        source_document_id="CDR-000001",
        extraction_method="structured",
        duration_seconds=74,
    )
    return Called(**(fields | overrides))


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        _call(timestamp=datetime(2025, 3, 14, 21, 5))


def test_disallowed_endpoint_types_rejected():
    with pytest.raises(ValidationError, match="cannot connect"):
        _call(source_id="Person:rajesh_kumar", target_id="Vehicle:MH12AB1234")


def test_structured_person_to_person_call_rejected():
    # Decision 3: structured data always routes through Phone/BankAccount nodes.
    with pytest.raises(ValidationError, match="instrument nodes"):
        _call(source_id="Person:rajesh_kumar", target_id="Person:imran_qureshi")
    assert _call(source_id="Person:rajesh_kumar", target_id="Person:imran_qureshi",
                 extraction_method="text_pattern").confidence == 0.7


def test_structured_person_to_person_transfer_rejected():
    with pytest.raises(ValidationError, match="instrument nodes"):
        TransferredMoneyTo(source_id="Person:a", target_id="Person:b", timestamp=T0,
                           source_document_id="TXN-000001", extraction_method="structured")


def test_self_loop_rejected():
    with pytest.raises(ValidationError, match="self-loop"):
        _call(target_id="Phone:+919876543210")


def test_unknown_node_type_prefix_rejected():
    with pytest.raises(ValidationError):
        _call(target_id="Spaceship:x")


def test_confidence_defaults_by_method():
    assert _call().confidence == 1.0
    text_edge = MetAt(
        source_id="Person:rajesh_kumar",
        target_id="Location:hotel_sai_palace:mumbai",
        timestamp=T0,
        source_document_id="FIR-0007",
        extraction_method="text_pattern",
    )
    assert text_edge.confidence == 0.7


def test_confidence_default_configurable_via_env(monkeypatch):
    monkeypatch.setenv("VERITAS_CONF_TEXT_COOCCURRENCE", "0.25")
    get_confidence_settings.cache_clear()
    try:
        edge = AssociatedWith(
            source_id="Person:rajesh_kumar",
            target_id="Organization:sai_logistics_pvt_ltd",
            timestamp=T0,
            source_document_id="FIR-0007",
            extraction_method="text_cooccurrence",
            context="same sentence",
        )
        assert edge.confidence == 0.25
    finally:
        get_confidence_settings.cache_clear()


def test_explicit_confidence_overrides_default():
    assert _call(confidence=0.8).confidence == 0.8


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _call(confidence=1.5)


def test_associated_with_requires_context():
    with pytest.raises(ValidationError):
        AssociatedWith(
            source_id="Person:a",
            target_id="Person:b",
            timestamp=T0,
            source_document_id="FIR-0001",
            extraction_method="text_cooccurrence",
        )


def test_edge_id_is_deterministic_and_timezone_independent():
    same_instant_utc = T0.astimezone(timezone.utc)
    assert _call().id == _call(timestamp=same_instant_utc).id
    assert _call().id != _call(source_document_id="CDR-000002").id


def test_structured_money_transfer_between_accounts():
    edge = TransferredMoneyTo(
        source_id="BankAccount:SBIN0001234:123456789012",
        target_id="BankAccount:HDFC0000456:987654321098",
        timestamp=T0,
        source_document_id="TXN-000042",
        extraction_method="structured",
        amount_inr="49500.00",
        mode="IMPS",
    )
    assert str(edge.amount_inr) == "49500.00"


# ---------- Serialization ----------


def test_node_round_trip_through_json_recomputes_id():
    node = Phone(number="09876543210", source_document_ids=DOC)
    parsed = NODE_ADAPTER.validate_json(node.model_dump_json())
    assert parsed == node and parsed.id == node.id


def test_supplied_id_is_ignored_not_trusted():
    parsed = NODE_ADAPTER.validate_python(
        {"type": "Person", "name": "Rajesh Kumar", "source_document_ids": DOC, "id": "Person:someone_else"}
    )
    assert parsed.id == "Person:rajesh_kumar"


def test_edge_round_trip_through_json():
    edge = _call()
    parsed = EDGE_ADAPTER.validate_json(edge.model_dump_json())
    assert isinstance(parsed, Called) and parsed.id == edge.id


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Person(name="Rajesh Kumar", source_document_ids=DOC, nickname="Pappu")


# ---------- Mentions ----------


def test_mention_defaults_and_span_check():
    m = EntityMention(document_id="FIR-0001", node_type="Phone", text="98765 43210",
                      start_char=10, end_char=21, method="regex")
    assert m.confidence == 0.95
    with pytest.raises(ValidationError, match="span length"):
        EntityMention(document_id="FIR-0001", node_type="Phone", text="98765 43210",
                      start_char=10, end_char=15, method="regex")


def test_ner_mention_confidence_is_per_label(monkeypatch):
    def mention(node_type, text):
        return EntityMention(document_id="FIR-0001", node_type=node_type, text=text, start_char=0,
                             end_char=len(text), method="spacy_ner")

    assert (mention("Person", "Ravi Kumar").confidence, mention("Location", "Pune").confidence,
            mention("Organization", "Sai Traders").confidence) == (0.92, 0.97, 0.29)
    monkeypatch.setenv("VERITAS_CONF_MENTION_SPACY_NER_ORGANIZATION", "0.5")
    get_confidence_settings.cache_clear()
    try:
        assert mention("Organization", "Sai Traders").confidence == 0.5
    finally:
        get_confidence_settings.cache_clear()


def test_mention_method_restricted_to_its_node_types():
    with pytest.raises(ValidationError, match="not allowed"):
        EntityMention(document_id="FIR-0001", node_type="Phone", text="98765 43210",
                      start_char=0, end_char=11, method="spacy_ner")

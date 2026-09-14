"""Loads structured CSVs and interpreted FIR text into a GraphBuilder."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from veritas import normalize
from veritas.extract.documents import load_firs
from veritas.extract.relations import interpret_document
from veritas.graph.builder import GraphBuilder
from veritas.models import (
    EDGE_ADAPTER, AssociatedWith, BankAccount, Called, EdgeType, Event, HoldsAccount, Location, MemberOf, NodeType,
    Organization, OwnsVehicle, Person, Phone, TransferredMoneyTo, UsesPhone, Vehicle, make_node_id,
)

# Event-like edges are stamped with when the incident happened; state-like edges with when the report was filed.
EVENT_LIKE = {EdgeType.CALLED, EdgeType.TRANSFERRED_MONEY_TO, EdgeType.MET_AT, EdgeType.PRESENT_AT_EVENT}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _holder(builder: GraphBuilder, name: str, holder_type: str, doc: str) -> str:
    cls = Person if holder_type == "person" else Organization
    return builder.add_node(cls(name=name, source_document_ids=[doc]))


def load_structured(builder: GraphBuilder, data: Path) -> None:
    s = data / "structured"
    for r in _rows(s / "subscribers.csv"):
        doc = r["record_id"]
        person = builder.add_node(Person(name=r["subscriber_name"], source_document_ids=[doc]))
        phone = builder.add_node(Phone(number=r["msisdn"], source_document_ids=[doc]))
        builder.add_edge(UsesPhone(source_id=person, target_id=phone, timestamp=r["activation_date"],
                                   source_document_id=doc, extraction_method="structured"))
    for r in _rows(s / "cdr.csv"):
        doc = r["record_id"]
        caller = builder.add_node(Phone(number=r["calling_number"], source_document_ids=[doc]))
        callee = builder.add_node(Phone(number=r["called_number"], source_document_ids=[doc]))
        builder.add_edge(Called(source_id=caller, target_id=callee, timestamp=r["start_time"], source_document_id=doc,
                                extraction_method="structured", duration_seconds=int(r["duration_seconds"]),
                                call_type=r["call_type"]))
    for r in _rows(s / "bank_accounts.csv"):
        doc = r["record_id"]
        account = builder.add_node(BankAccount(ifsc=r["ifsc"], account_number=r["account_number"],
                                               bank_name=r["bank_name"], source_document_ids=[doc]))
        holder = _holder(builder, r["holder_name"], r["holder_type"], doc)
        builder.add_edge(HoldsAccount(source_id=holder, target_id=account, timestamp=r["opened_on"],
                                      source_document_id=doc, extraction_method="structured"))
    for r in _rows(s / "transactions.csv"):
        doc = r["txn_id"]
        payer = builder.add_node(BankAccount(ifsc=r["from_ifsc"], account_number=r["from_account"], source_document_ids=[doc]))
        payee = builder.add_node(BankAccount(ifsc=r["to_ifsc"], account_number=r["to_account"], source_document_ids=[doc]))
        builder.add_edge(TransferredMoneyTo(source_id=payer, target_id=payee, timestamp=r["timestamp"], source_document_id=doc,
                                            extraction_method="structured", amount_inr=r["amount_inr"], mode=r["mode"]))
    for r in _rows(s / "vehicle_registry.csv"):
        doc = r["record_id"]
        vehicle = builder.add_node(Vehicle(registration_number=r["registration_number"], make_model=r["make_model"],
                                           color=r["color"], source_document_ids=[doc]))
        owner = _holder(builder, r["owner_name"], r["owner_type"], doc)
        builder.add_edge(OwnsVehicle(source_id=owner, target_id=vehicle, timestamp=r["registered_on"],
                                     source_document_id=doc, extraction_method="structured"))
    for r in _rows(s / "company_registry.csv"):
        doc = r["record_id"]
        org = builder.add_node(Organization(name=r["company_name"], org_type=r["company_type"], source_document_ids=[doc]))
        director = builder.add_node(Person(name=r["director_name"], source_document_ids=[doc]))
        builder.add_edge(MemberOf(source_id=director, target_id=org, timestamp=r["appointed_on"], source_document_id=doc,
                                  extraction_method="structured", role=r["role"]))
    for r in _rows(s / "incident_register.csv"):
        doc = r["record_id"]
        event = builder.add_node(Event(event_ref=r["event_ref"], event_type=r["event_type"], occurred_at=r["occurred_at"],
                                       source_document_ids=[doc]))
        place = builder.add_node(Location(name=r["location_name"], city=r["city"], source_document_ids=[doc]))
        builder.add_edge(AssociatedWith(source_id=event, target_id=place, timestamp=r["occurred_at"], source_document_id=doc,
                                        extraction_method="structured", context="event location"))


def _entity_node(entity, doc_id: str):
    docs = [doc_id]
    if entity.node_type == NodeType.PERSON:
        return Person(name=entity.name, source_document_ids=docs)
    if entity.node_type == NodeType.ORGANIZATION:
        return Organization(name=entity.name, source_document_ids=docs)
    if entity.node_type == NodeType.LOCATION:
        return Location(name=entity.name, city=entity.city, source_document_ids=docs)
    if entity.node_type == NodeType.PHONE:
        return Phone(number=entity.name, source_document_ids=docs)
    return Vehicle(registration_number=entity.name, source_document_ids=docs)


def load_text(builder: GraphBuilder, data: Path, entities_path: Path) -> list[dict[str, Any]]:
    """Adds FIR entities and relations. Returns an evidence record (rule, sentence) for every text edge."""
    extracted = json.loads(entities_path.read_text(encoding="utf-8"))
    records = {d["document_id"]: d["entities"] for d in extracted["documents"]}
    evidence = []
    for doc in load_firs(data / "firs"):
        event_id = make_node_id(NodeType.EVENT, normalize.text_key(doc.fir_id))
        # The incident register normally created this Event already; otherwise fall back to the FIR header.
        builder.add_node(Event(event_ref=doc.fir_id, event_type="reported incident", occurred_at=doc.occurred_at,
                               source_document_ids=[doc.fir_id]))
        interpretation = interpret_document(doc.fir_id, doc.narrative, records.get(doc.fir_id, []), event_id)
        for entity in interpretation.entities:
            if entity.node_id is None:
                builder.stats["text_mentions_without_key"] += 1
            elif entity.is_city_of_place:
                builder.stats["text_mentions_used_as_city"] += 1
            else:
                builder.add_node(_entity_node(entity, doc.fir_id))
        for rel in interpretation.relations:
            fields = {
                "type": rel.edge_type, "source_id": rel.source_id, "target_id": rel.target_id,
                "timestamp": doc.occurred_at if rel.edge_type in EVENT_LIKE else doc.reported_at,
                "source_document_id": doc.fir_id, "extraction_method": rel.method, "confidence": rel.confidence,
            }
            if rel.edge_type == EdgeType.ASSOCIATED_WITH:
                fields["context"] = "mentioned in the same sentence"
            edge = EDGE_ADAPTER.validate_python(fields)
            if builder.add_edge(edge):
                evidence.append({"edge_id": edge.id, "type": rel.edge_type.value, "source": rel.source_id,
                                 "target": rel.target_id, "document_id": doc.fir_id, "rule": rel.rule,
                                 "confidence": rel.confidence, "sentence": rel.sentence})
    return evidence

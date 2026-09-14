"""Graph construction tests: builder rules, structured and text loading, GraphML round trip."""

import csv
import json
from datetime import datetime
from pathlib import Path

import pytest

from veritas.extract.documents import load_firs
from veritas.graph.builder import GraphBuilder
from veritas.graph.io import load_graphml, save_graphml
from veritas.graph.loaders import EVENT_LIKE, load_structured, load_text
from veritas.models import Called, EdgeType, Person, Phone

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ENTITIES = ROOT / "output" / "phase2" / "entities.en_core_web_md.json"


def _rows(name):
    with (DATA / "structured" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def built():
    builder = GraphBuilder()
    load_structured(builder, DATA)
    evidence = load_text(builder, DATA, ENTITIES)
    return builder, builder.finalize(), evidence


def _edges(graph, edge_type, method):
    return [(s, d, a) for s, d, a in graph.edges(data=True) if a["type"] == edge_type and a["extraction_method"] == method]


# ---------- Builder rules ----------


def test_merge_unions_provenance_and_keeps_first_display_name():
    b = GraphBuilder()
    b.add_node(Person(name="Shri Rahul Sharma", source_document_ids=["FIR-1"]))
    b.add_node(Person(name="Rahul Sharma", source_document_ids=["SUB-1", "FIR-1"]))
    node = b.nodes["Person:rahul_sharma"]
    assert node.name == "Shri Rahul Sharma" and node.source_document_ids == ("FIR-1", "SUB-1")
    assert b.name_variants["Person:rahul_sharma"] == {"Shri Rahul Sharma", "Rahul Sharma"}


def test_edges_need_existing_nodes_and_duplicates_are_skipped():
    b = GraphBuilder()
    a = b.add_node(Phone(number="9876543210", source_document_ids=["SUB-1"]))
    edge = Called(source_id=a, target_id="Phone:+919123456789", timestamp="2025-01-01T10:00:00+05:30",
                  source_document_id="CDR-1", extraction_method="structured")
    with pytest.raises(KeyError, match="missing node"):
        b.add_edge(edge)
    b.add_node(Phone(number="9123456789", source_document_ids=["SUB-2"]))
    assert b.add_edge(edge) is True and b.add_edge(edge) is False
    assert b.stats["duplicate_edges_skipped"] == 1


# ---------- Structured data ----------


def test_every_structured_record_becomes_exactly_one_edge(built):
    _, graph, _ = built
    expected = {
        ("CALLED", "cdr.csv"), ("TRANSFERRED_MONEY_TO", "transactions.csv"), ("USES_PHONE", "subscribers.csv"),
        ("HOLDS_ACCOUNT", "bank_accounts.csv"), ("OWNS_VEHICLE", "vehicle_registry.csv"),
        ("MEMBER_OF", "company_registry.csv"), ("ASSOCIATED_WITH", "incident_register.csv"),
    }
    for edge_type, file in expected:
        assert len(_edges(graph, edge_type, "structured")) == len(_rows(file)), edge_type


def test_endpoints_exist_and_match_their_id_prefix(built):
    _, graph, _ = built
    for node_id, attrs in graph.nodes(data=True):
        assert node_id.split(":", 1)[0] == attrs["type"]
    for s, d, _ in graph.edges(data=True):
        assert graph.has_node(s) and graph.has_node(d)


def test_no_structured_person_to_person_edges(built):
    _, graph, _ = built
    assert not [1 for s, d, a in graph.edges(data=True)
                if a["extraction_method"] == "structured" and s.startswith("Person:") and d.startswith("Person:")]


def test_planted_collision_is_merged_by_exact_matching(built):
    _, graph, _ = built
    truth = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))
    collision = truth["planted_collisions"][0]
    phones = {d for s, d, a in _edges(graph, "USES_PHONE", "structured") if s == collision["expected_node_id"]}
    assert phones == {f"Phone:{n}" for p in collision["true_persons"] for n in p["phones"]}


# ---------- Text data ----------


def test_text_edges_carry_fir_provenance_and_the_right_timestamp(built):
    _, graph, evidence = built
    firs = {d.fir_id: d for d in load_firs(DATA / "firs")}
    text_edges = [(s, d, a) for s, d, a in graph.edges(data=True) if a["extraction_method"] != "structured"]
    assert text_edges and len(text_edges) == len(evidence)
    for _, _, a in text_edges:
        doc = firs[a["source_document_id"]]
        expected = doc.occurred_at if EdgeType(a["type"]) in EVENT_LIKE else doc.reported_at
        assert datetime.fromisoformat(a["timestamp"]) == expected
        assert 0 < a["confidence"] <= 0.7  # never above the text_pattern default


def test_text_nodes_record_the_fir_they_came_from(built):
    builder, graph, _ = built
    assert builder.stats["text_mentions_used_as_city"] > 0
    fir_nodes = [n for n, a in graph.nodes(data=True) if any(d.startswith("FIR-") for d in json.loads(a["source_document_ids"]))]
    assert any(n.startswith("Person:") for n in fir_nodes) and any(n.startswith("Location:") for n in fir_nodes)


# ---------- Serialization and determinism ----------


def test_graphml_round_trip(built, tmp_path):
    _, graph, _ = built
    path = tmp_path / "graph.graphml"
    save_graphml(graph, path)
    loaded = load_graphml(path)
    assert (loaded.number_of_nodes(), loaded.number_of_edges()) == (graph.number_of_nodes(), graph.number_of_edges())
    node = "Person:rahul_sharma"
    assert loaded.nodes[node]["source_document_ids"] == json.loads(graph.nodes[node]["source_document_ids"])
    s, d, key, attrs = next(iter(graph.edges(keys=True, data=True)))
    assert loaded.edges[s, d, key]["timestamp"] == attrs["timestamp"]


def test_rebuild_is_identical(built):
    _, graph, _ = built
    again = GraphBuilder()
    load_structured(again, DATA)
    load_text(again, DATA, ENTITIES)
    rebuilt = again.finalize()
    assert set(rebuilt.edges(keys=True)) == set(graph.edges(keys=True))
    assert dict(rebuilt.nodes(data=True)) == dict(graph.nodes(data=True))

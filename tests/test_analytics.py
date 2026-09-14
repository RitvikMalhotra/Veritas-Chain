"""Phase 4 tests: actor projection, rankings, Louvain determinism, spike and cycle rules, evaluation helpers."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from veritas.analytics.anomalies import detect_call_spikes, detect_money_cycles
from veritas.analytics.centrality import centrality_rankings, louvain
from veritas.analytics.evaluate import evaluate_communities
from veritas.analytics.projection import actor_graph
from veritas.config import AnalyticsSettings
from veritas.graph.builder import GraphBuilder
from veritas.graph.loaders import load_structured
from veritas.models import (
    AssociatedWith, BankAccount, Called, Event, HoldsAccount, Organization, Person, Phone, PresentAtEvent,
    TransferredMoneyTo, UsesPhone,
)

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2025, 1, 1, tzinfo=IST)
ROOT = Path(__file__).resolve().parents[1]


def _person(b, name, doc="SUB-1"):
    return b.add_node(Person(name=name, source_document_ids=[doc]))


def _phone(b, person, number, doc="SUB-1"):
    phone = b.add_node(Phone(number=number, source_document_ids=[doc]))
    b.add_edge(UsesPhone(source_id=person, target_id=phone, timestamp=T0, source_document_id=doc, extraction_method="structured"))
    return phone


def _call(b, src, dst, at, doc):
    b.add_edge(Called(source_id=src, target_id=dst, timestamp=at, source_document_id=doc, extraction_method="structured"))


# ---------- Projection ----------


def test_calls_between_phones_become_person_ties():
    b = GraphBuilder()
    ravi, amit = _person(b, "Ravi Kumar"), _person(b, "Amit Joshi")
    p, q = _phone(b, ravi, "9876543210"), _phone(b, amit, "9123456789")
    _call(b, p, q, T0, "CDR-1")
    _call(b, p, q, T0 + timedelta(hours=1), "CDR-2")
    actors = actor_graph(b.finalize())
    assert actors[ravi][amit]["weight"] == 2.0 and not actors.has_edge(amit, ravi)


def test_shared_phone_splits_weight_and_money_reaches_companies():
    b = GraphBuilder()
    ravi, amit, neha = _person(b, "Ravi Kumar"), _person(b, "Amit Joshi"), _person(b, "Neha Rao")
    shared = _phone(b, ravi, "9876543210")
    b.add_edge(UsesPhone(source_id=amit, target_id=shared, timestamp=T0, source_document_id="SUB-2", extraction_method="structured"))
    q = _phone(b, neha, "9123456789")
    _call(b, shared, q, T0, "CDR-1")
    org = b.add_node(Organization(name="Sai Traders", source_document_ids=["KYC-1"]))
    a1 = b.add_node(BankAccount(ifsc="ZARV0000001", account_number="123456789012", source_document_ids=["KYC-1"]))
    a2 = b.add_node(BankAccount(ifsc="ZARV0000001", account_number="223456789012", source_document_ids=["KYC-2"]))
    b.add_edge(HoldsAccount(source_id=neha, target_id=a1, timestamp=T0, source_document_id="KYC-1", extraction_method="structured"))
    b.add_edge(HoldsAccount(source_id=org, target_id=a2, timestamp=T0, source_document_id="KYC-2", extraction_method="structured"))
    b.add_edge(TransferredMoneyTo(source_id=a1, target_id=a2, timestamp=T0, source_document_id="TXN-1",
                                  extraction_method="structured", amount_inr="1000"))
    actors = actor_graph(b.finalize())
    assert actors[ravi][neha]["weight"] == 0.5 and actors[amit][neha]["weight"] == 0.5
    assert actors[neha][org]["TRANSFERRED_MONEY_TO"] == 1.0


def test_variants_drop_text_evidence():
    b = GraphBuilder()
    ravi, amit, neha = (_person(b, n, "FIR-1") for n in ("Ravi Kumar", "Amit Joshi", "Neha Rao"))
    event = b.add_node(Event(event_ref="FIR-1", event_type="raid", occurred_at=T0, source_document_ids=["INC-1"]))
    for p in (ravi, amit):
        b.add_edge(PresentAtEvent(source_id=p, target_id=event, timestamp=T0, source_document_id="FIR-1",
                                  extraction_method="text_pattern", confidence=0.7))
    b.add_edge(AssociatedWith(source_id=amit, target_id=neha, timestamp=T0, source_document_id="FIR-1",
                              extraction_method="text_cooccurrence", confidence=0.4, context="same sentence"))
    graph = b.finalize()
    everything = actor_graph(graph, "all_evidence")
    assert everything[ravi][amit]["co_present"] == 0.7 and everything[neha][amit]["weight"] == 0.4
    assert not actor_graph(graph, "no_cooccurrence").has_edge(amit, neha)
    assert actor_graph(graph, "structured_only").number_of_edges() == 0


# ---------- Rankings and communities ----------


@pytest.fixture(scope="module")
def structured_actors():
    b = GraphBuilder()
    load_structured(b, ROOT / "data")
    return actor_graph(b.finalize(), "structured_only")


def test_rankings_cover_people_only_and_are_stable(structured_actors):
    rankings = centrality_rankings(structured_actors)
    people = sorted(n for n, a in structured_actors.nodes(data=True) if a["type"] == "Person")
    for metric, ranking in rankings.items():
        assert sorted(r["node"] for r in ranking) == people, metric
        assert [r["rank"] for r in ranking] == list(range(1, len(people) + 1))
    assert centrality_rankings(structured_actors) == rankings


def test_louvain_is_repeatable_with_a_seed_and_partitions_all_actors(structured_actors):
    first = louvain(structured_actors, seed=3, resolution=1.0)
    assert louvain(structured_actors, seed=3, resolution=1.0) == first
    assert sorted(n for c in first for n in c) == sorted(structured_actors.nodes)


def test_community_scoring_reports_purity_not_just_recall():
    truth = {
        "persons": [{"true_id": f"T{i}", "expected_node_id": f"Person:p{i}", "role": r, "cluster": c}
                    for i, (r, c) in enumerate([("leader", "A"), ("member", "A"), ("noise", None), ("noise", None)])]
        + [{"true_id": "T9", "expected_node_id": "Person:x", "role": "member", "cluster": "A"}],
        "planted_collisions": [{"expected_node_id": "Person:x"}],
        "clusters": [{"cluster_id": "A", "leader": "T0", "lieutenants": [], "members": ["T1"]}],
        "bridges": [],
    }
    result = evaluate_communities([["Person:p0", "Person:p1", "Person:p2", "Person:p3"]], truth)
    assert result["per_cluster"]["A"]["recall"] == 1.0 and result["per_cluster"]["A"]["purity"] == 0.5


# ---------- Money cycles ----------


def _money_graph(hops):
    b = GraphBuilder()
    accounts = {}
    for i, name in enumerate("ABCD"):
        accounts[name] = b.add_node(BankAccount(ifsc="ZARV0000001", account_number=f"10000000{i}000", source_document_ids=["KYC"]))
    for n, (src, dst, day, amount) in enumerate(hops):
        b.add_edge(TransferredMoneyTo(source_id=accounts[src], target_id=accounts[dst], timestamp=T0 + timedelta(days=day),
                                      source_document_id=f"TXN-{n}", extraction_method="structured", amount_inr=str(amount)))
    return b.finalize()


def test_time_ordered_shrinking_loop_is_flagged():
    result = detect_money_cycles(_money_graph([("A", "B", 1, 100000), ("B", "C", 2, 97000), ("C", "A", 3, 94000)]), AnalyticsSettings())
    assert len(result["topology_cycles"]) == 1 and len(result["flagged"]) == 1
    assert result["flagged"][0]["transactions"] == ["TXN-0", "TXN-1", "TXN-2"]


@pytest.mark.parametrize("hops, why", [
    # Each case breaks exactly one rule, so every check is tested on its own (amounts shrink ~3% unless noted).
    ([("A", "B", 3, 100000), ("B", "C", 2, 97000), ("C", "A", 1, 94000)], "dates run backwards around the loop"),
    ([("A", "B", 1, 100000), ("B", "C", 2, 120000), ("C", "A", 3, 119000)], "money grows along the loop"),
    ([("A", "B", 1, 100000), ("B", "C", 20, 97000), ("C", "A", 21, 94000)], "hop gap longer than 7 days"),
])
def test_loops_failing_the_rule_are_found_by_topology_but_not_flagged(hops, why):
    result = detect_money_cycles(_money_graph(hops), AnalyticsSettings())
    assert len(result["topology_cycles"]) == 1 and result["flagged"] == [], why


def test_repayment_two_cycles_are_ignored():
    result = detect_money_cycles(_money_graph([("A", "B", 1, 5000), ("B", "A", 10, 5000)]), AnalyticsSettings())
    assert result["topology_cycles"] == [] and result["flagged"] == []


# ---------- Call spikes ----------


def _spike_graph(calls_in_window):
    b = GraphBuilder()
    ravi = _person(b, "Ravi Kumar", "FIR-1")
    amit = _person(b, "Amit Joshi")
    p, q = _phone(b, ravi, "9876543210"), _phone(b, amit, "9123456789")
    b.add_node(Event(event_ref="FIR-1", event_type="raid", occurred_at=T0 + timedelta(days=30), source_document_ids=["INC-1"]))
    b.add_node(Event(event_ref="FIR-2", event_type="theft", occurred_at=T0 + timedelta(days=45), source_document_ids=["INC-2"]))
    n = 0
    for day in range(60):  # one call a day at the normal rate
        _call(b, p, q, T0 + timedelta(days=day, hours=12), f"CDR-{n}")
        n += 1
    for i in range(calls_in_window):
        _call(b, q, p, T0 + timedelta(days=29, minutes=10 * i), f"CDR-{n}")
        n += 1
    return b.finalize()


def test_spike_on_named_persons_phones_is_flagged():
    results = {r["event_ref"]: r for r in detect_call_spikes(_spike_graph(20), AnalyticsSettings())}
    assert results["FIR-1"]["flagged"] and results["FIR-1"]["observed_calls"] >= 20
    assert not results["FIR-2"]["flagged"] and "no phones" in results["FIR-2"]["reason"]  # nobody named in FIR-2


def test_normal_volume_is_not_flagged():
    results = {r["event_ref"]: r for r in detect_call_spikes(_spike_graph(0), AnalyticsSettings())}
    assert not results["FIR-1"]["flagged"]

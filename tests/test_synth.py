"""Generator self-checks: the data really has the structure ground_truth.json claims it has."""

import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import networkx as nx
import pytest

from veritas.models import (
    EDGE_ADAPTER, BankAccount, Called, Event, HoldsAccount, MemberOf, NodeType, Organization, OwnsVehicle, Person,
    Phone, TransferredMoneyTo, UsesPhone, Vehicle, node_type_of,
)
from veritas.synth.generate import generate
from veritas.synth.reports import SYNTHETIC_BANNER, parse_narrative

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=[42, 7])
def data(request, tmp_path_factory):
    out = tmp_path_factory.mktemp(f"seed{request.param}")
    generate(request.param, out)
    return out


def _rows(out: Path, name: str) -> list[dict]:
    with (out / "structured" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _truth(out: Path) -> dict:
    return json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))


def _digest(folder: Path) -> dict[str, str]:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "README.md"}


# ---------- Reproducibility ----------


def test_output_is_identical_across_processes_and_hash_seeds(tmp_path):
    for label, hash_seed in (("a", "1"), ("b", "999")):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        subprocess.run([sys.executable, "-m", "veritas.synth", "--seed", "42", "--out", str(tmp_path / label)],
                       cwd=ROOT, env=env, check=True, capture_output=True)
    assert _digest(tmp_path / "a") == _digest(tmp_path / "b")


def test_committed_data_matches_seed_42(tmp_path):
    if not (ROOT / "data" / "ground_truth.json").exists():
        pytest.skip("data/ not generated yet")
    generate(42, tmp_path)
    assert _digest(ROOT / "data") == _digest(tmp_path), "data/ is stale: rerun python -m veritas.synth"


# ---------- Brief requirements ----------


def test_cluster_counts_and_sizes(data):
    clusters = _truth(data)["clusters"]
    assert 3 <= len(clusters) <= 4
    assert all(5 <= c["size"] <= 10 for c in clusters)


def test_one_or_two_bridges_between_distinct_clusters(data):
    bridges = _truth(data)["bridges"]
    assert 1 <= len(bridges) <= 2
    assert all(len(set(b["connects"])) == 2 for b in bridges)


def test_fir_count_and_banner(data):
    files = sorted((data / "firs").glob("FIR-*.txt"))
    assert 20 <= len(files) <= 30
    assert all(f.read_text(encoding="utf-8").splitlines()[0] == SYNTHETIC_BANNER for f in files)


# ---------- Schema conformance: every structured row loads into the Phase 0 models ----------


def test_structured_rows_conform_to_schema(data):
    subs = _rows(data, "subscribers.csv")
    for r in subs:
        person = Person(name=r["subscriber_name"], source_document_ids=[r["record_id"]])
        phone = Phone(number=r["msisdn"], source_document_ids=[r["record_id"]])
        UsesPhone(source_id=person.id, target_id=phone.id, timestamp=r["activation_date"],
                  source_document_id=r["record_id"], extraction_method="structured")
    for r in _rows(data, "cdr.csv"):
        Called(source_id=Phone(number=r["calling_number"], source_document_ids=["x"]).id,
               target_id=Phone(number=r["called_number"], source_document_ids=["x"]).id,
               timestamp=r["start_time"], source_document_id=r["record_id"], extraction_method="structured",
               duration_seconds=int(r["duration_seconds"]), call_type=r["call_type"])
    for r in _rows(data, "bank_accounts.csv"):
        acct = BankAccount(ifsc=r["ifsc"], account_number=r["account_number"], source_document_ids=[r["record_id"]])
        holder_cls = Person if r["holder_type"] == "person" else Organization
        holder = holder_cls(name=r["holder_name"], source_document_ids=[r["record_id"]])
        HoldsAccount(source_id=holder.id, target_id=acct.id, timestamp=r["opened_on"],
                     source_document_id=r["record_id"], extraction_method="structured")
    for r in _rows(data, "transactions.csv"):
        TransferredMoneyTo(
            source_id=BankAccount(ifsc=r["from_ifsc"], account_number=r["from_account"], source_document_ids=["x"]).id,
            target_id=BankAccount(ifsc=r["to_ifsc"], account_number=r["to_account"], source_document_ids=["x"]).id,
            timestamp=r["timestamp"], source_document_id=r["txn_id"], extraction_method="structured",
            amount_inr=r["amount_inr"], mode=r["mode"])
    for r in _rows(data, "vehicle_registry.csv"):
        vehicle = Vehicle(registration_number=r["registration_number"], source_document_ids=[r["record_id"]])
        OwnsVehicle(source_id=Person(name=r["owner_name"], source_document_ids=["x"]).id, target_id=vehicle.id,
                    timestamp=r["registered_on"], source_document_id=r["record_id"], extraction_method="structured")
    for r in _rows(data, "company_registry.csv"):
        org = Organization(name=r["company_name"], source_document_ids=[r["record_id"]])
        MemberOf(source_id=Person(name=r["director_name"], source_document_ids=["x"]).id, target_id=org.id,
                 timestamp=r["appointed_on"], source_document_id=r["record_id"], extraction_method="structured")
    for r in _rows(data, "incident_register.csv"):
        Event(event_ref=r["event_ref"], event_type=r["event_type"], occurred_at=r["occurred_at"],
              source_document_ids=[r["record_id"]])


def test_referential_integrity(data):
    truth = _truth(data)
    known_numbers = {"91" + r["msisdn"] for r in _rows(data, "subscribers.csv")}
    known_numbers |= {n.lstrip("+") for n in truth["unregistered_numbers"]}
    for r in _rows(data, "cdr.csv"):
        assert r["calling_number"] in known_numbers and r["called_number"] in known_numbers
    accounts = {(r["ifsc"], r["account_number"]) for r in _rows(data, "bank_accounts.csv")}
    for r in _rows(data, "transactions.csv"):
        assert (r["from_ifsc"], r["from_account"]) in accounts and (r["to_ifsc"], r["to_account"]) in accounts
    fir_ids = {f.stem for f in (data / "firs").glob("FIR-*.txt")}
    assert fir_ids == {r["event_ref"] for r in _rows(data, "incident_register.csv")}


def test_isolated_people_never_call(data):
    truth = _truth(data)
    isolated = {n.lstrip("+") for p in truth["persons"] if "isolated" in p["tags"] for n in p["phones"]}
    assert isolated
    assert not any(r["calling_number"] in isolated or r["called_number"] in isolated for r in _rows(data, "cdr.csv"))


# ---------- Planted name collision (decision 2) ----------


def test_exactly_one_planted_name_collision(data):
    truth = _truth(data)
    by_key = defaultdict(list)
    for p in truth["persons"]:
        by_key[p["expected_node_id"]].append(p["true_id"])
    shared = {k: v for k, v in by_key.items() if len(v) > 1}
    planted = truth["planted_collisions"]
    assert len(planted) == 1 and list(shared) == [planted[0]["expected_node_id"]]
    assert sorted(shared[planted[0]["expected_node_id"]]) == sorted(p["true_id"] for p in planted[0]["true_persons"])
    roles = {p["role"] for p in planted[0]["true_persons"]}
    assert roles == {"member", "noise"}  # one criminal-cluster member, one unrelated person


def test_collision_people_both_appear_in_reports(data):
    truth = _truth(data)
    ids = {p["true_id"] for p in truth["planted_collisions"][0]["true_persons"]}
    mentioned = {m["true_id"] for r in truth["fir_annotations"]["reports"].values() for m in r["mentions"]}
    assert ids <= mentioned


# ---------- FIR annotations ----------


def test_mention_spans_match_narrative_text(data):
    reports = _truth(data)["fir_annotations"]["reports"]
    for fir_id, ann in reports.items():
        narrative = parse_narrative((data / "firs" / f"{fir_id}.txt").read_text(encoding="utf-8"))
        assert ann["mentions"], fir_id
        for m in ann["mentions"]:
            assert narrative[m["start"]:m["end"]] == m["text"], (fir_id, m)


def test_relations_follow_schema_and_decision_3(data):
    reports = _truth(data)["fir_annotations"]["reports"]
    for fir_id, ann in reports.items():
        mention_ids = {m["expected_node_id"] for m in ann["mentions"]}
        assert all(m["node_type"] != "BankAccount" for m in ann["mentions"])  # accounts never appear in report text
        phone_users = {r["source"] for r in ann["relations"] if r["type"] == "USES_PHONE"}
        for rel in ann["relations"]:
            fields = {"type": rel["type"], "source_id": rel["source"], "target_id": rel["target"],
                      "timestamp": "2025-01-01T00:00:00+05:30", "source_document_id": fir_id,
                      "extraction_method": "text_pattern"}
            if rel["type"] == "ASSOCIATED_WITH":
                fields["context"] = "annotation"
            EDGE_ADAPTER.validate_python(fields)  # allowed endpoint pairs from Phase 0
            assert rel["source"] in mention_ids
            assert rel["target"] in mention_ids or node_type_of(rel["target"]) == NodeType.EVENT
            both_people = node_type_of(rel["source"]) == node_type_of(rel["target"]) == NodeType.PERSON
            if rel["type"] == "CALLED" and both_people:
                assert not {rel["source"], rel["target"]} & phone_users, (fir_id, rel)


# ---------- Money cycles ----------


def _txn_index(data):
    return {r["txn_id"]: r for r in _rows(data, "transactions.csv")}


def _acct(r, side):
    return f"BankAccount:{r[side + '_ifsc']}:{r[side + '_account']}"


def test_no_incidental_cycles(data):
    assert _truth(data)["money_cycles"]["incidental"] == []


def test_planted_cycle_is_time_ordered_with_shrinking_amounts(data):
    txns = _txn_index(data)
    planted = _truth(data)["money_cycles"]["planted"][0]
    cycle = planted["account_cycle"]
    for rnd in planted["rounds"]:
        hops = [txns[t] for t in rnd["transactions"]]
        assert len(hops) == len(cycle)
        for i, hop in enumerate(hops):
            assert (_acct(hop, "from"), _acct(hop, "to")) == (cycle[i], cycle[(i + 1) % len(cycle)])
        times = [datetime.fromisoformat(h["timestamp"]) for h in hops]
        assert times == sorted(times) and len(set(times)) == len(times)
        amounts = [float(h["amount_inr"]) for h in hops]
        assert all(0.95 <= b / a <= 0.99 for a, b in zip(amounts, amounts[1:]))


def test_decoy_cycle_has_no_time_respecting_order(data):
    txns = _txn_index(data)
    decoy = _truth(data)["money_cycles"]["decoys"][0]
    hops = [txns[t] for t in decoy["transactions"]]
    cycle = decoy["account_cycle"]
    for i, hop in enumerate(hops):
        assert (_acct(hop, "from"), _acct(hop, "to")) == (cycle[i], cycle[(i + 1) % len(cycle)])
    times = [datetime.fromisoformat(h["timestamp"]) for h in hops]
    ascents = sum(times[i] < times[(i + 1) % len(times)] for i in range(len(times)))
    assert ascents != len(times) - 1  # no rotation of the loop is in time order
    amounts = [float(h["amount_inr"]) for h in hops]
    assert max(amounts) / min(amounts) > 5


# ---------- Call spikes ----------


def test_planted_spikes_stand_out_from_baseline(data):
    truth = _truth(data)
    owner = {n.lstrip("+"): p["true_id"] for p in truth["persons"] for n in p["phones"]}
    calls = [(datetime.fromisoformat(r["start_time"]), owner.get(r["calling_number"]), owner.get(r["called_number"]))
             for r in _rows(data, "cdr.csv")]
    start = datetime.fromisoformat(truth["generator"]["window_start"])
    total_hours = truth["generator"]["window_days"] * 24
    spikes = [e for e in truth["events"] if e["planted_call_spike"]]
    assert spikes
    for event in spikes:
        people = set(event["spike_participants"])
        lo, hi = (datetime.fromisoformat(t) for t in event["spike_window"])
        inside = [t for t, a, b in calls if a in people and b in people and a != b]
        in_window = sum(lo <= t < hi for t in inside)
        window_hours = (hi - lo).total_seconds() / 3600
        baseline_rate = (len(inside) - in_window) / (total_hours - window_hours)
        # Planted multiplier is 5x; require at least 2.5x so random variation can't make this flaky.
        assert in_window >= 2.5 * baseline_rate * window_hours, (event["event_ref"], in_window, baseline_rate)
        assert start <= lo


# ---------- Planted structure notes are true ----------


def test_calls_follow_insulated_hierarchy(data):
    truth = _truth(data)
    owner = {n.lstrip("+"): p["true_id"] for p in truth["persons"] for n in p["phones"]}
    pair_calls = defaultdict(int)
    for r in _rows(data, "cdr.csv"):
        a, b = owner.get(r["calling_number"]), owner.get(r["called_number"])
        pair_calls[frozenset((a, b))] += 1
    for c in truth["clusters"]:
        leader, lts, members = c["leader"], set(c["lieutenants"]), c["members"]
        member_to_lt = sum(pair_calls[frozenset((m, lt))] for m in members for lt in lts)
        member_to_leader = sum(pair_calls[frozenset((m, leader))] for m in members)
        leader_to_lt = sum(pair_calls[frozenset((leader, lt))] for lt in lts)
        assert member_to_lt > 2 * member_to_leader, c["cluster_id"]
        assert leader_to_lt > member_to_leader, c["cluster_id"]


def test_money_flow_notes(data):
    truth = _truth(data)
    clusters = {c["cluster_id"]: c for c in truth["clusters"]}
    persons = {p["true_id"]: p for p in truth["persons"]}
    inflows = defaultdict(set)
    for r in _rows(data, "transactions.csv"):
        inflows[_acct(r, "to")].add(_acct(r, "from"))

    def acct(true_id):
        return persons[true_id]["account"]

    for cid, source_ids in (("A", clusters["A"]["lieutenants"]), ("D", [clusters["D"]["members"][0]])):
        assert {acct(i) for i in source_ids} <= inflows[acct(clusters[cid]["leader"])], cid  # converge on leader
    b = clusters["B"]
    assert not {acct(i) for i in b["members"] + b["lieutenants"] if acct(i)} & inflows[acct(b["leader"])]
    assert acct(b["leader"]) in inflows[acct(truth["bridges"][1]["true_id"])]  # B leader -> bridge2
    assert acct(clusters["C"]["leader"]) in truth["money_cycles"]["planted"][0]["account_cycle"]


# ---------- Bridge structure ----------


def test_bridges_are_the_only_links_between_clusters(data):
    truth = _truth(data)
    cluster_of = {p["true_id"]: p["cluster"] for p in truth["persons"] if p["cluster"]}
    bridge_ids = {b["true_id"]: b["connects"] for b in truth["bridges"]}
    owner = {n.lstrip("+"): p["true_id"] for p in truth["persons"] for n in p["phones"]}
    graph = nx.Graph()
    graph.add_nodes_from([*cluster_of, *bridge_ids])
    for r in _rows(data, "cdr.csv"):
        a, b = owner.get(r["calling_number"]), owner.get(r["called_number"])
        if a in graph and b in graph and a != b:
            graph.add_edge(a, b)
    for a, b in graph.edges:  # no direct call between members of different clusters
        if a in cluster_of and b in cluster_of:
            assert cluster_of[a] == cluster_of[b]

    def members(cid):
        return [p for p, c in cluster_of.items() if c == cid]

    for bridge, (x, y) in bridge_ids.items():
        assert nx.has_path(graph, members(x)[0], members(y)[0])
        without = graph.copy()
        without.remove_node(bridge)
        assert not nx.has_path(without, members(x)[0], members(y)[0]), f"{x}-{y} connected without bridge {bridge}"
    unbridged = [c["cluster_id"] for c in truth["clusters"] if not any(c["cluster_id"] in v for v in bridge_ids.values())]
    for cid in unbridged:
        others = [p for p, c in cluster_of.items() if c != cid]
        assert not any(nx.has_path(graph, members(cid)[0], o) for o in others)

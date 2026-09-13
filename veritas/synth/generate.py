"""Writes the synthetic dataset: structured CSVs, FIR text files and ground_truth.json."""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import networkx as nx

from veritas.synth.activity import generate_calls, generate_transactions
from veritas.synth.catalog import WINDOW_DAYS, WINDOW_START
from veritas.synth.reports import render_report
from veritas.synth.scenarios import SPIKE_AFTER, SPIKE_BEFORE, SPIKE_FACTOR, build_scenarios
from veritas.synth.world import build_world


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _iso(dt) -> str:
    return dt.isoformat(timespec="seconds")


def _follow_cycle(txns) -> tuple[list[str], list]:
    # Order a set of transactions that form one loop by following money, starting at the smallest account id.
    by_source = {t.from_account: t for t in txns}
    start = cur = min(by_source)
    accounts, ordered = [], []
    while True:
        accounts.append(cur)
        ordered.append(by_source[cur])
        cur = by_source[cur].to_account
        if cur == start:
            return accounts, ordered


def _cycles(txns, min_len: int = 3) -> list[list[str]]:
    # Every simple directed cycle among accounts, each rotated to start at its smallest id.
    graph = nx.DiGraph((t.from_account, t.to_account) for t in txns)
    found = []
    for cycle in nx.simple_cycles(graph, length_bound=8):
        if len(cycle) >= min_len:
            i = cycle.index(min(cycle))
            found.append(cycle[i:] + cycle[:i])
    return sorted(found)


def generate(seed: int, out_dir: Path) -> dict[str, int]:
    world = build_world(seed)
    scenarios = build_scenarios(world)
    calls = generate_calls(world, scenarios)
    txns = generate_transactions(world, scenarios)
    reports = [render_report(s, seed) for s in scenarios]

    structured, firs = out_dir / "structured", out_dir / "firs"
    structured.mkdir(parents=True, exist_ok=True)
    firs.mkdir(parents=True, exist_ok=True)
    for stale in firs.glob("FIR-*.txt"):  # only files this generator wrote earlier
        stale.unlink()

    P = world.persons
    people = list(P.values())

    # SIM subscriber registry: one row per SIM. Numbers are bare 10-digit, unlike the CDR.
    sims = [(p, n) for p in people for n in p.phones]
    sim_rng = random.Random(f"{seed}:sims")
    activations = [WINDOW_START - timedelta(days=sim_rng.randint(30, 3000), hours=sim_rng.randint(0, 12)) for _ in sims]
    _write_csv(structured / "subscribers.csv", ["record_id", "msisdn", "subscriber_name", "city", "activation_date"],
               [[f"SUB-{i:04d}", n, p.name, p.city, _iso(activations[i - 1])] for i, (p, n) in enumerate(sims, start=1)])

    # CDR: numbers carry the 91 prefix, as operator exports usually do.
    _write_csv(structured / "cdr.csv", ["record_id", "calling_number", "called_number", "start_time", "duration_seconds", "call_type"],
               [[f"CDR-{i:06d}", "91" + c.caller, "91" + c.callee, _iso(c.at), c.seconds, c.kind]
                for i, c in enumerate(calls, start=1)])

    accounts = [p.account for p in people if p.account] + [o.account for o in world.orgs.values()]
    _write_csv(structured / "bank_accounts.csv",
               ["record_id", "ifsc", "account_number", "bank_name", "holder_name", "holder_type", "opened_on"],
               [[f"KYC-{i:04d}", a.ifsc, a.number, a.bank_name, a.holder_name, a.holder_type, _iso(a.opened_on)]
                for i, a in enumerate(accounts, start=1)])
    by_node = {a.node_id: a for a in accounts}

    txn_ids = {}
    rows = []
    for i, t in enumerate(txns, start=1):
        txn_ids[id(t)] = f"TXN-{i:06d}"
        src, dst = by_node[t.from_account], by_node[t.to_account]
        rows.append([f"TXN-{i:06d}", src.ifsc, src.number, dst.ifsc, dst.number, f"{t.amount:.2f}", t.mode, _iso(t.at)])
    _write_csv(structured / "transactions.csv",
               ["txn_id", "from_ifsc", "from_account", "to_ifsc", "to_account", "amount_inr", "mode", "timestamp"], rows)

    vehicles = [v for p in people for v in p.vehicles]
    _write_csv(structured / "vehicle_registry.csv",
               ["record_id", "registration_number", "make_model", "color", "owner_name", "owner_type", "registered_on"],
               [[f"VEH-{i:04d}", v.plate, v.make_model, v.color, v.owner_name, v.owner_type, _iso(v.registered_on)]
                for i, v in enumerate(vehicles, start=1)])

    _write_csv(structured / "company_registry.csv",
               ["record_id", "company_name", "company_type", "city", "director_name", "role", "appointed_on"],
               [[f"ROC-{i:04d}", o.name, o.org_type, o.city, P[d].name, "director", _iso(o.appointed_on)]
                for i, (o, d) in enumerate(((o, d) for o in world.orgs.values() for d in o.directors), start=1)])

    _write_csv(structured / "incident_register.csv",
               ["record_id", "event_ref", "event_type", "occurred_at", "location_name", "city", "police_station"],
               [[f"INC-{i:04d}", s.fir_id, s.event_type, _iso(s.occurred_at), s.place.name, s.city, s.police_station]
                for i, s in enumerate(scenarios, start=1)])

    for r in reports:
        (firs / f"{r.fir_id}.txt").write_text(r.file_text, encoding="utf-8", newline="\n")

    ground_truth = _ground_truth(world, scenarios, txns, txn_ids, reports, calls)
    (out_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8", newline="\n")
    return {"persons": len(people), "sims": len(sims), "calls": len(calls), "accounts": len(accounts),
            "transactions": len(txns), "vehicles": len(vehicles), "organizations": len(world.orgs), "firs": len(reports)}


def _visibility(world, calls) -> dict[str, Any]:
    # How visible each key person is from raw call counts alone, measured with perfect identity resolution.
    owner = {n: p.true_id for p in world.persons.values() for n in p.phones}
    volume: dict[str, int] = defaultdict(int)
    contacts: dict[str, set[str]] = defaultdict(set)
    for c in calls:
        for me, other in ((c.caller, c.callee), (c.callee, c.caller)):
            if me in owner:
                volume[owner[me]] += 1
                contacts[owner[me]].add(owner.get(other, other))
    ids = list(world.persons)
    by_volume = sorted(ids, key=lambda i: (-volume[i], i))
    by_contacts = sorted(ids, key=lambda i: (-len(contacts[i]), i))
    key_ids = [*(c.leader for c in world.clusters.values()),
               *(lt for c in world.clusters.values() for lt in c.lieutenants), *world.bridge_ids]
    return {
        "note": ("rank 1 = most calls / most distinct contacts among all people; ties broken by true_id. "
                 "Computed from true identities, so real pipeline output can only be noisier."),
        "population": len(ids),
        "people": [{"true_id": i, "role": world.persons[i].role, "call_count": volume[i],
                    "call_count_rank": by_volume.index(i) + 1, "distinct_contacts": len(contacts[i]),
                    "distinct_contacts_rank": by_contacts.index(i) + 1} for i in key_ids],
        "top_10_by_call_count_roles": [world.persons[i].role for i in by_volume[:10]],
    }


def _spike_strength(world, scenario, calls) -> dict[str, float] | None:
    # Realized strength of a planted spike: participant-to-participant calls in the window vs. the same-length baseline.
    if not scenario.spike_ids:
        return None
    people = set(scenario.spike_ids)
    owner = {n: p.true_id for p in world.persons.values() for n in p.phones}
    lo, hi = scenario.spike_window
    among = [c.at for c in calls if owner.get(c.caller) in people and owner.get(c.callee) in people]
    inside = sum(lo <= t < hi for t in among)
    window_hours = (hi - lo).total_seconds() / 3600
    baseline = (len(among) - inside) / (WINDOW_DAYS * 24 - window_hours) * window_hours
    return {"calls_in_window": inside, "baseline_calls_per_window": round(baseline, 2),
            "ratio": round(inside / baseline, 2) if baseline else None}


def _ground_truth(world, scenarios, txns, txn_ids, reports, calls) -> dict[str, Any]:
    P = world.persons
    C = world.clusters["C"]
    chain_holders = [C.leader, C.members[0], C.members[1]]
    front = world.orgs[C.front_org]
    planted_accounts = [P[i].account.node_id for i in chain_holders] + [front.account.node_id]
    planted_txns = [t for t in txns if t.tag.startswith("planted_cycle")]
    decoy_accounts, decoy_txns = _follow_cycle([t for t in txns if t.tag == "decoy_cycle"])

    def rotated(cycle):
        i = cycle.index(min(cycle))
        return cycle[i:] + cycle[:i]

    all_cycles = _cycles(txns)
    known = [rotated(planted_accounts), rotated(decoy_accounts)]
    incidental = [c for c in all_cycles if c not in known]

    def person_entry(p):
        return {
            "true_id": p.true_id, "name": p.name, "expected_node_id": p.node_id, "role": p.role,
            "cluster": p.cluster, "bridges": p.bridges, "city": p.city, "tags": p.tags, "reports_to": p.reports_to,
            "phones": ["+91" + n for n in p.phones],
            "account": p.account.node_id if p.account else None,
            "vehicles": [v.node_id for v in p.vehicles],
        }

    b1, b2 = (P[i] for i in world.bridge_ids)
    collision = [P[i] for i in world.collision_ids]
    return {
        "_readme": ("Evaluation-only ground truth for synthetic data. The pipeline (Phases 2-6) must never read this "
                    "file; it exists to score pipeline output. All people, numbers and records are fictional."),
        "generator": {"seed": world.seed, "window_start": _iso(WINDOW_START), "window_days": WINDOW_DAYS},
        "clusters": [
            {"cluster_id": c.cluster_id, "theme": c.theme, "city": c.city, "size": len(c.everyone),
             "leader": c.leader, "lieutenants": c.lieutenants, "members": c.members,
             "meeting_places": [pl.node_id for pl in c.meeting_places],
             "front_organization": world.orgs[c.front_org].node_id if c.front_org else None}
            for c in world.clusters.values()
        ],
        "key_individuals": [
            *({"true_id": c.leader, "role": "leader", "cluster": c.cluster_id,
               "why": "runs the cluster; calls mainly its lieutenants"} for c in world.clusters.values()),
            *({"true_id": lt, "role": "lieutenant", "cluster": c.cluster_id,
               "why": "relays between leader and members"}
              for c in world.clusters.values() for lt in c.lieutenants),
            {"true_id": b1.true_id, "role": "bridge", "cluster": None, "why": "only call link between clusters A and B (transporter)"},
            {"true_id": b2.true_id, "role": "bridge", "cluster": None, "why": "only call link between clusters B and C (money handler)"},
        ],
        "planted_structure_notes": [
            "Calls follow an insulated hierarchy: members call their lieutenants far more than the leader, and the leader "
            "talks mainly to lieutenants. Whether the leader or a lieutenant is the busiest caller varies by cluster "
            "(see signal_visibility).",
            "Bridges have ordinary call volume; what makes them important is connectivity, not traffic.",
            "Money A: buyers -> street members -> lieutenant -> leader (flows converge on the leader).",
            "Money B: leader -> bridge2 -> cluster C's front company (the leader sends money out; no inflow from members).",
            "Money C: fraud victims -> mule1 -> mule2 -> front company; the planted cycle runs through the leader.",
            "Money D: shopkeepers -> collector -> leader (flows converge on the leader).",
            "No per-metric outcome (degree, betweenness, PageRank) is promised here; Phase 4 measures it.",
        ],
        "signal_visibility": _visibility(world, calls),
        "bridges": [
            {"true_id": b.true_id, "connects": b.bridges, "member_of_cluster": None,
             "scoring_rule": "not a cluster member; a community assignment to either connected cluster counts as correct"}
            for b in (b1, b2)
        ],
        "planted_collisions": [{
            "name": collision[0].name,
            "expected_node_id": collision[0].node_id,
            "true_persons": [{"true_id": p.true_id, "role": p.role, "cluster": p.cluster, "city": p.city,
                              "phones": ["+91" + n for n in p.phones]} for p in collision],
            "intended": "two distinct people who share a common name",
            "expected_pipeline_behavior": ("exact normalized-name matching merges both into one Person node "
                                           "(known false merge, schema.md section 7)"),
            "expected_effect": ("the merged node holds both phones, so cluster A appears linked to the Delhi "
                                "contacts of the unrelated Rahul Sharma"),
        }],
        "money_cycles": {
            "planted": [{
                "cluster": "C",
                "account_cycle": planted_accounts,
                "rounds": [
                    {"round": n, "transactions": [txn_ids[id(t)] for t in planted_txns if t.tag.startswith(f"planted_cycle:{n}:")]}
                    for n in (1, 2)
                ],
                "pattern": "every hop happens after the previous one and is 2-4% smaller (layering with commission)",
            }],
            "decoys": [{
                "account_cycle": decoy_accounts,
                "transactions": [txn_ids[id(t)] for t in decoy_txns],  # in loop order, matching account_cycle
                "why_decoy": "friends' payments: dates run backwards around the loop and amounts differ by over 5x",
            }],
            "incidental": incidental,
            "note": "loan repayments create 2-cycles (A->B->A) by design; only cycles of length 3+ are listed",
        },
        "events": [
            {"event_ref": s.fir_id, "scenario": s.key, "cluster": s.cluster, "event_type": s.event_type,
             "occurred_at": _iso(s.occurred_at), "planted_call_spike": bool(s.spike_ids),
             "spike_window": [_iso(w) for w in s.spike_window] if s.spike_ids else None,
             "spike_participants": s.spike_ids,
             "spike_measured": _spike_strength(world, s, calls)}
            for s in scenarios
        ],
        "spike_parameters": {"hours_before": SPIKE_BEFORE.total_seconds() / 3600,
                             "hours_after": SPIKE_AFTER.total_seconds() / 3600, "rate_multiplier": SPIKE_FACTOR,
                             "applies_to": "calls between two spike participants inside the window",
                             "note": ("planted as a rate multiplier, so the realized rise is random; small groups can "
                                      "come out weaker than 5x. Check spike_measured per event.")},
        "unregistered_numbers": ["+91" + n for n in world.unregistered_numbers],
        "persons": [person_entry(p) for p in P.values()],
        "fir_annotations": {
            "offsets": "character offsets into the narrative line (the line after 'NARRATIVE'), counted in Python str indices",
            "reports": {r.fir_id: {"scenario": s.key, "cluster": s.cluster, "mentions": r.mentions, "relations": r.relations}
                        for r, s in zip(reports, scenarios)},
        },
    }

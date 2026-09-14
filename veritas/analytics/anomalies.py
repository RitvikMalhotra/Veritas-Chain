"""Rule-based anomaly detection: call-volume spikes around incidents, and time-ordered circular money flows."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import networkx as nx
from scipy.stats import poisson

from veritas.config import AnalyticsSettings


def _docs(attrs: dict[str, Any]) -> list[str]:
    docs = attrs.get("source_document_ids", [])
    return json.loads(docs) if isinstance(docs, str) else docs


def detect_call_spikes(graph: nx.MultiDiGraph, settings: AnalyticsSettings) -> list[dict[str, Any]]:
    """For each incident: calls on the phones of people named in its report, inside the window vs. their normal rate."""
    calls = [(datetime.fromisoformat(a["timestamp"]), s, d) for s, d, a in graph.edges(data=True)
             if a["type"] == "CALLED" and a["extraction_method"] == "structured"]
    if not calls:
        return []
    data_start, data_end = min(t for t, _, _ in calls), max(t for t, _, _ in calls)
    phones_of = defaultdict(set)
    for s, d, a in graph.edges(data=True):
        if a["type"] == "USES_PHONE":
            phones_of[s].add(d)
    people_by_doc = defaultdict(set)
    for n, a in graph.nodes(data=True):
        if a["type"] == "Person":
            for doc in _docs(a):
                people_by_doc[doc].add(n)

    results = []
    for node, a in sorted(graph.nodes(data=True)):
        if a["type"] != "Event":
            continue
        occurred = datetime.fromisoformat(a["occurred_at"])
        people = sorted(people_by_doc.get(a["event_ref"], set()))  # the Event's report shares its reference
        phones = set().union(*(phones_of[p] for p in people)) if people else set()
        lo = max(occurred - timedelta(hours=settings.spike_hours_before), data_start)
        hi = min(occurred + timedelta(hours=settings.spike_hours_after), data_end)
        entry = {"event": node, "event_ref": a["event_ref"], "occurred_at": a["occurred_at"], "people": people,
                 "phones": sorted(phones), "window": [lo.isoformat(), hi.isoformat()], "flagged": False}
        if not phones:
            results.append({**entry, "reason": "no phones known for people named in the report"})
            continue
        times = [t for t, s, d in calls if s in phones or d in phones]
        observed = sum(lo <= t < hi for t in times)
        window_h = (hi - lo).total_seconds() / 3600
        rest_h = (data_end - data_start).total_seconds() / 3600 - window_h
        expected = (len(times) - observed) / rest_h * window_h if rest_h > 0 else 0.0
        ratio = observed / expected if expected else None
        p_value = float(poisson.sf(observed - 1, expected)) if expected else 0.0  # P(X >= observed) at the normal rate
        flagged = (observed >= settings.spike_min_calls and (ratio is None or ratio >= settings.spike_min_ratio)
                   and p_value <= settings.spike_max_p_value)
        results.append({**entry, "observed_calls": observed, "expected_calls": round(expected, 2),
                        "ratio": round(ratio, 2) if ratio else None, "p_value": p_value, "flagged": flagged})
    return results


def detect_money_cycles(graph: nx.MultiDiGraph, settings: AnalyticsSettings) -> dict[str, Any]:
    """Account-level loops. A loop is flagged only if one pass through it is time-ordered with small deductions."""
    hops = defaultdict(list)  # (payer, payee) -> [(time, amount, txn_id)]
    for s, d, a in graph.edges(data=True):
        if a["type"] == "TRANSFERRED_MONEY_TO" and a["extraction_method"] == "structured":
            hops[(s, d)].append((datetime.fromisoformat(a["timestamp"]), float(a["amount_inr"]), a["source_document_id"]))
    for txns in hops.values():
        txns.sort()
    holders = defaultdict(list)
    for s, d, a in graph.edges(data=True):
        if a["type"] == "HOLDS_ACCOUNT":
            holders[d].append(s)

    accounts = nx.DiGraph(list(hops))
    topology = sorted(c for c in nx.simple_cycles(accounts, length_bound=settings.cycle_max_length)
                      if len(c) >= settings.cycle_min_length)
    gap = timedelta(days=settings.cycle_max_hop_gap_days)
    flagged: dict[frozenset, dict[str, Any]] = {}

    def passes(route, i, prev, chosen):
        if i == len(route):
            yield chosen
            return
        for t, amount, txn in hops[(route[i], route[(i + 1) % len(route)])]:
            if prev and not (prev[0] < t <= prev[0] + gap):
                continue  # each hop must follow the previous one within the gap
            if prev and not (settings.cycle_min_amount_retention * prev[1] <= amount <= prev[1]):
                continue  # money shrinks a little per hop; it never grows
            yield from passes(route, i + 1, (t, amount), chosen + [(t, amount, txn)])

    for cycle in topology:
        for r in range(len(cycle)):  # a time-ordered pass can start at any account in the loop
            route = cycle[r:] + cycle[:r]
            for chosen in passes(route, 0, None, []):
                key = frozenset(txn for _, _, txn in chosen)
                flagged.setdefault(key, {
                    "accounts": route,
                    "holders": [holders.get(acc, []) for acc in route],
                    "transactions": [txn for _, _, txn in chosen],
                    "amounts": [amount for _, amount, _ in chosen],
                    "start": chosen[0][0].isoformat(), "end": chosen[-1][0].isoformat(),
                })
    return {"topology_cycles": topology, "flagged": sorted(flagged.values(), key=lambda f: f["start"])}

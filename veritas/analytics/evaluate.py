"""Validates Phase 4 output against ground_truth.json (evaluation only). Expectations were fixed before the first run."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# Written before running analytics. Reported as met / not met; never edited to fit results.
EXPECTATIONS = {
    "bridges_high_betweenness": ("Both bridge individuals rank in the top 10% of people by betweenness on the "
                                 "structured-only graph, since removing either one disconnects its two clusters in the call data."),
    "clusters_recovered": ("For each planted cluster, one Louvain community holds at least 80% of its members "
                           "(structured-only graph; the merged Rahul Sharma node is excluded from scoring)."),
    "spike_events_flagged": "Every incident with a planted call spike is flagged.",
    "no_spike_false_alarms": "No incident without a planted call spike is flagged.",
    "laundering_rounds_flagged": "Both planted laundering rounds are flagged as time-ordered cycles made of exactly their transactions.",
    "decoy_not_flagged": "The decoy loop is not flagged, although topology alone finds it.",
}
NOT_EXPECTED = ("Leaders are insulated by design (approved in Phase 1), so no metric is expected to rank them first; "
                "their ranks are reported, not judged.")


def _truth_index(truth: dict[str, Any]) -> dict[str, Any]:
    by_true = {p["true_id"]: p for p in truth["persons"]}
    collision = truth["planted_collisions"][0]["expected_node_id"]
    key = []
    for c in truth["clusters"]:
        key.append((c["leader"], "leader", c["cluster_id"]))
        key += [(i, "lieutenant", c["cluster_id"]) for i in c["lieutenants"]]
    key += [(b["true_id"], "bridge", "-".join(b["connects"])) for b in truth["bridges"]]
    clusters = {c["cluster_id"]: {by_true[i]["expected_node_id"] for i in [c["leader"], *c["lieutenants"], *c["members"]]}
                - {collision} for c in truth["clusters"]}
    known_people = {p["expected_node_id"] for p in truth["persons"]} - {collision}
    return {"by_true": by_true, "collision": collision, "key": key, "clusters": clusters, "known_people": known_people}


def evaluate_centrality(rankings: dict[str, dict[str, list]], truth: dict[str, Any]) -> dict[str, Any]:
    idx = _truth_index(truth)
    key_nodes = {idx["by_true"][t]["expected_node_id"] for t, _, _ in idx["key"]}
    out = {}
    for variant, metrics in rankings.items():
        out[variant] = {}
        for metric, ranking in metrics.items():
            rank_of = {r["node"]: r["rank"] for r in ranking}
            k = len(key_nodes)
            top = [r["node"] for r in ranking[:k]]
            out[variant][metric] = {
                "people_ranked": len(ranking),
                f"key_individuals_in_top_{k}": sum(n in key_nodes for n in top),
                "top_10": [{"node": n, "role": _role(n, truth)} for n in top[:10]],
                "key_individual_ranks": [
                    {"true_id": t, "role": role, "group": group, "node": idx["by_true"][t]["expected_node_id"],
                     "rank": rank_of.get(idx["by_true"][t]["expected_node_id"])}
                    for t, role, group in idx["key"]
                ],
            }
    return out


def _role(node: str, truth: dict[str, Any]) -> str:
    roles = sorted({f"{p['role']}{'/' + p['cluster'] if p['cluster'] else ''}"
                    for p in truth["persons"] if p["expected_node_id"] == node})
    return "+".join(roles) if roles else "not a ground-truth person (text-only node)"


def evaluate_communities(communities: list[list[str]], truth: dict[str, Any]) -> dict[str, Any]:
    idx = _truth_index(truth)
    community_of = {n: i for i, c in enumerate(communities) for n in c}
    per_cluster, best_community = {}, {}
    for cid, members in idx["clusters"].items():
        counts = defaultdict(int)
        for n in members:
            if n in community_of:
                counts[community_of[n]] += 1
        best, hit = max(counts.items(), key=lambda kv: (kv[1], -kv[0])) if counts else (None, 0)
        best_community[cid] = best
        people_in_best = [n for n in communities[best] if n in idx["known_people"]] if best is not None else []
        per_cluster[cid] = {
            "members": len(members), "largest_share_in_one_community": hit, "recall": hit / len(members),
            "community": best, "community_size": len(communities[best]) if best is not None else 0,
            "purity": hit / len(people_in_best) if people_in_best else None,  # share of known people in it from this cluster
        }
    bridges = []
    for b in truth["bridges"]:
        node = idx["by_true"][b["true_id"]]["expected_node_id"]
        c = community_of.get(node)
        matched = [cid for cid, bc in best_community.items() if bc == c]
        bridges.append({"true_id": b["true_id"], "connects": b["connects"], "community": c, "matches_cluster": matched,
                        "correct": bool(set(matched) & set(b["connects"]))})
    collision = idx["collision"]
    return {
        "communities": len(communities),
        "communities_of_2_or_more": sum(len(c) >= 2 for c in communities),
        "per_cluster": per_cluster,
        "bridges": bridges,
        "collision_node_community": {"node": collision, "community": community_of.get(collision),
                                     "clusters_in_that_community": [cid for cid, bc in best_community.items()
                                                                    if bc == community_of.get(collision)]},
    }


def evaluate_spikes(spikes: list[dict[str, Any]], truth: dict[str, Any]) -> dict[str, Any]:
    planted = {e["event_ref"]: e for e in truth["events"]}
    rows, tp, fp, fn = [], 0, 0, 0
    for s in spikes:
        truth_event = planted[s["event_ref"]]
        is_planted = truth_event["planted_call_spike"]
        tp += is_planted and s["flagged"]
        fp += (not is_planted) and s["flagged"]
        fn += is_planted and not s["flagged"]
        rows.append({"event_ref": s["event_ref"], "scenario": truth_event["scenario"], "planted": is_planted,
                     "generator_measured_ratio": (truth_event["spike_measured"] or {}).get("ratio"),
                     "flagged": s["flagged"], "observed": s.get("observed_calls"), "expected": s.get("expected_calls"),
                     "ratio": s.get("ratio"), "p_value": s.get("p_value"), "people_named": len(s["people"]),
                     "note": s.get("reason")})
    return {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "events": rows}


def evaluate_cycles(cycles: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    planted = truth["money_cycles"]["planted"][0]
    decoy = truth["money_cycles"]["decoys"][0]

    def same_loop(a, b):
        return len(a) == len(b) and set(a) == set(b)

    flagged_sets = [set(f["transactions"]) for f in cycles["flagged"]]
    rounds = [{"round": r["round"], "flagged_exactly": set(r["transactions"]) in flagged_sets} for r in planted["rounds"]]
    return {
        "topology_only": {
            "cycles_found": len(cycles["topology_cycles"]),
            "planted_loop_found": any(same_loop(c, planted["account_cycle"]) for c in cycles["topology_cycles"]),
            "decoy_loop_found": any(same_loop(c, decoy["account_cycle"]) for c in cycles["topology_cycles"]),
        },
        "time_and_amount_rule": {
            "flagged": len(cycles["flagged"]),
            "planted_rounds": rounds,
            "decoy_flagged": any(set(f["transactions"]) & set(decoy["transactions"]) for f in cycles["flagged"]),
            "other_flagged": [f for f in cycles["flagged"] if not any(set(f["transactions"]) == set(r["transactions"])
                                                                       for r in planted["rounds"])],
        },
    }


def check_expectations(centrality: dict, communities: dict, spikes: dict, cycles: dict) -> dict[str, Any]:
    betweenness = centrality["structured_only"]["betweenness"]
    cutoff = max(1, round(0.10 * betweenness["people_ranked"]))
    bridge_ranks = [r["rank"] for r in betweenness["key_individual_ranks"] if r["role"] == "bridge"]
    recalls = {cid: c["recall"] for cid, c in communities["structured_only"]["per_cluster"].items()}
    rounds = cycles["time_and_amount_rule"]["planted_rounds"]
    results = {
        "bridges_high_betweenness": (all(r is not None and r <= cutoff for r in bridge_ranks),
                                     f"bridge ranks {bridge_ranks}; top 10% cutoff = rank {cutoff}"),
        "clusters_recovered": (all(v >= 0.8 for v in recalls.values()),
                               "recall per cluster " + ", ".join(f"{k}={v:.2f}" for k, v in recalls.items())),
        "spike_events_flagged": (spikes["false_negatives"] == 0,
                                 f"{spikes['true_positives']} flagged, {spikes['false_negatives']} missed"),
        "no_spike_false_alarms": (spikes["false_positives"] == 0, f"{spikes['false_positives']} false alarms"),
        "laundering_rounds_flagged": (all(r["flagged_exactly"] for r in rounds),
                                      ", ".join(f"round {r['round']}: {r['flagged_exactly']}" for r in rounds)),
        "decoy_not_flagged": (cycles["topology_only"]["decoy_loop_found"] and not cycles["time_and_amount_rule"]["decoy_flagged"],
                              f"found by topology: {cycles['topology_only']['decoy_loop_found']}; "
                              f"flagged by rule: {cycles['time_and_amount_rule']['decoy_flagged']}"),
    }
    return {name: {"expectation": EXPECTATIONS[name], "met": met, "detail": detail} for name, (met, detail) in results.items()}

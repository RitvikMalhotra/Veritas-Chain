"""CLI: python -m veritas.analytics --graph output/phase3/graph.graphml --out output/phase4 [--evaluate]"""

import argparse
import json
from pathlib import Path

from veritas.analytics.anomalies import detect_call_spikes, detect_money_cycles
from veritas.analytics.centrality import centrality_rankings, louvain
from veritas.analytics.projection import VARIANTS, actor_graph
from veritas.config import AnalyticsSettings
from veritas.graph.io import load_graphml

parser = argparse.ArgumentParser(description="Centrality, communities and anomaly rules on the built graph.")
parser.add_argument("--graph", type=Path, default=Path("output/phase3/graph.graphml"))
parser.add_argument("--data", type=Path, default=Path("data"))
parser.add_argument("--out", type=Path, default=Path("output/phase4"))
parser.add_argument("--evaluate", action="store_true", help="validate against data/ground_truth.json (evaluation only)")
args = parser.parse_args()

if not args.graph.exists():
    raise SystemExit(f"{args.graph} not found: run python -m veritas.graph first")
settings = AnalyticsSettings()
graph = load_graphml(args.graph)
actors = {v: actor_graph(graph, v) for v in VARIANTS}
rankings = {v: centrality_rankings(a) for v, a in actors.items()}
communities = {v: louvain(a, settings.louvain_seed, settings.louvain_resolution) for v, a in actors.items()}
spikes = detect_call_spikes(graph, settings)
cycles = detect_money_cycles(graph, settings)

args.out.mkdir(parents=True, exist_ok=True)


def write_json(name, payload):
    path = args.out / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


write_json("analytics.json", {
    "settings": settings.model_dump(),
    "actor_graphs": {v: {"nodes": a.number_of_nodes(), "edges": a.number_of_edges()} for v, a in actors.items()},
    "rankings": rankings, "communities": communities, "call_spikes": spikes, "money_cycles": cycles,
})
print("actor graphs:", {v: (a.number_of_nodes(), a.number_of_edges()) for v, a in actors.items()})
print("flagged incidents:", [s["event_ref"] for s in spikes if s["flagged"]])
print(f"money loops: {len(cycles['topology_cycles'])} by topology, {len(cycles['flagged'])} flagged by time/amount rule")

if args.evaluate:
    from veritas.analytics import evaluate as ev  # ground truth is only touched in evaluation mode

    truth = json.loads((args.data / "ground_truth.json").read_text(encoding="utf-8"))
    centrality = ev.evaluate_centrality(rankings, truth)
    community_eval = {v: ev.evaluate_communities(c, truth) for v, c in communities.items()}
    stability = {seed: ev.evaluate_communities(louvain(actors["structured_only"], seed, settings.louvain_resolution), truth)
                 for seed in range(10)}
    spike_eval = ev.evaluate_spikes(spikes, truth)
    cycle_eval = ev.evaluate_cycles(cycles, truth)
    expectations = ev.check_expectations(centrality, community_eval, spike_eval, cycle_eval)
    path = write_json("evaluation.json", {
        "expectations": expectations, "not_expected": ev.NOT_EXPECTED, "centrality": centrality,
        "communities": community_eval,
        "louvain_stability_structured_only": {
            cid: {"recall_by_seed": [stability[s]["per_cluster"][cid]["recall"] for s in range(10)]}
            for cid in stability[0]["per_cluster"]
        },
        "call_spikes": spike_eval, "money_cycles": cycle_eval,
    })
    print("\nexpectations (fixed before running):")
    for name, e in expectations.items():
        print(f"  [{'MET' if e['met'] else 'NOT MET'}] {name}: {e['detail']}")
    k = next(key for key in centrality["all_evidence"]["degree"] if key.startswith("key_individuals_in_top_"))
    print(f"\n{k.replace('_', ' ')} (leaders + lieutenants + bridges):")
    for variant in VARIANTS:
        print(f"  {variant:<16}" + "  ".join(f"{m}={centrality[variant][m][k]}" for m in ("degree", "betweenness", "pagerank")))
    print("->", path)

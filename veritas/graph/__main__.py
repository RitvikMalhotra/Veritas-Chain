"""CLI: python -m veritas.graph --data data --entities output/phase2/entities.en_core_web_md.json --out output/phase3 [--evaluate]"""

import argparse
import json
from pathlib import Path

from veritas.audit.chain import AuditLog
from veritas.graph.builder import GraphBuilder
from veritas.graph.io import save_graphml
from veritas.graph.loaders import load_structured, load_text
from veritas.graph.report import build_report

parser = argparse.ArgumentParser(description="Build the criminal-network graph from structured data and FIR text.")
parser.add_argument("--data", type=Path, default=Path("data"))
parser.add_argument("--entities", type=Path, default=Path("output/phase2/entities.en_core_web_md.json"))
parser.add_argument("--out", type=Path, default=Path("output/phase3"))
parser.add_argument("--audit", type=Path, default=None,
                    help="hash-chain audit log of every graph write (default: <out>/../phase5/audit.sqlite); "
                         "each build starts a new chain")
parser.add_argument("--evaluate", action="store_true", help="score against data/ground_truth.json (evaluation only)")
args = parser.parse_args()
args.audit = args.audit or args.out.parent / "phase5" / "audit.sqlite"  # holdout builds keep their own log


def write_json(name: str, payload) -> Path:
    path = args.out / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


args.audit.unlink(missing_ok=True)  # the graph is rebuilt from scratch, so its history starts from scratch too
with AuditLog(args.audit) as audit:
    builder = GraphBuilder(audit=audit)
    load_structured(builder, args.data)
    evidence = load_text(builder, args.data, args.entities)
    graph = builder.finalize()
    head = audit.head()
# The anchor belongs outside the database; next to it is only good enough for a demo (see README, production changes).
anchor_path = args.audit.with_name("anchor.json")
anchor_path.write_text(json.dumps({"idx": head.idx, "hash": head.hash}, indent=2) + "\n", encoding="utf-8", newline="\n")
args.out.mkdir(parents=True, exist_ok=True)
save_graphml(graph, args.out / "graph.graphml")
report = build_report(graph, builder.stats, builder.name_variants)
write_json("build_report.json", report)
write_json("text_edge_evidence.json", evidence)

print(f"graph: {report['nodes']} nodes, {report['edges']} edges -> {args.out / 'graph.graphml'}")
print(f"audit: {head.idx} blocks -> {args.audit} (anchor {anchor_path}: block {head.idx}, {head.hash[:16]}...)")
for kind, count in report["nodes_by_type"].items():
    print(f"  node {kind:<14}{count}")
for kind, count in report["edges_by_type"].items():
    print(f"  edge {kind:<40}{count}")
er = report["entity_resolution"]
print("persons with several subscriber records:", {k: len(v) for k, v in er["persons_with_several_subscriber_records"].items()})
print("text-only nodes:", {k: len(v) for k, v in er["text_only_nodes"].items()})

if args.evaluate:
    from veritas.graph.report import evaluate_graph  # ground truth is only touched in evaluation mode

    truth = json.loads((args.data / "ground_truth.json").read_text(encoding="utf-8"))
    result = evaluate_graph(graph, truth)
    path = write_json("graph_evaluation.json", result)
    print("\nevaluation:")
    print("  true persons present:", result["true_persons_present"])
    print("  planted collision merged as expected:", result["planted_collision"]["merged_as_expected"],
          result["planted_collision"]["phones_on_merged_node"])
    for t, v in result["text_mentions_linked_to_expected_node"].items():
        print(f"  text mentions linked, {t:<13}{v['as_node'] + v['as_city_of_place']}/{v['total']} ({100 * v['rate']:.1f}%)"
              f"  [as node {v['as_node']}, as city of a place {v['as_city_of_place']}, unlinked {v['unlinked']}]")
    print("  text-only nodes not in ground truth:", {k: len(v) for k, v in result["text_only_nodes_not_in_ground_truth"].items()})
    m = result["text_pattern_edges_vs_annotations"]["micro"]
    print(f"  text pattern edges in graph vs annotations: P {100 * m['precision']:.1f} R {100 * m['recall']:.1f}")
    print("  ->", path)

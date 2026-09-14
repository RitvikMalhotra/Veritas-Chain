"""CLI: python -m veritas.audit — verify the chain, check it against its anchor, and replay it against the saved graph."""

import argparse
import json
from collections import Counter
from pathlib import Path

from veritas.audit.chain import Anchor, AuditLog, verify_chain
from veritas.audit.replay import graph_differences, replay
from veritas.graph.io import load_graphml

parser = argparse.ArgumentParser(description="Verify the hash-chain audit log of graph writes.")
parser.add_argument("--audit", type=Path, default=Path("output/phase5/audit.sqlite"))
parser.add_argument("--anchor", type=Path, default=Path("output/phase5/anchor.json"))
parser.add_argument("--graph", type=Path, default=Path("output/phase3/graph.graphml"))
parser.add_argument("--out", type=Path, default=Path("output/phase5"))
args = parser.parse_args()

if not args.audit.exists():
    raise SystemExit(f"{args.audit} not found: run python -m veritas.graph first")
anchor = Anchor(**json.loads(args.anchor.read_text(encoding="utf-8"))) if args.anchor.exists() else None
result = verify_chain(args.audit, anchor)
log = AuditLog(args.audit)
try:
    blocks = list(log.blocks())
finally:
    log.close()
rebuilt = replay(blocks)
saved = load_graphml(args.graph)
differences = graph_differences(saved, rebuilt)

report = {
    "verification": {"ok": result.ok, "blocks_checked": result.blocks_checked, "anchor_checked": anchor is not None,
                     "problems": result.problems},
    "blocks_by_operation": dict(sorted(Counter(b.operation for b in blocks).items())),
    "replay": {"graph_file": args.graph.as_posix(), "nodes": rebuilt.number_of_nodes(), "edges": rebuilt.number_of_edges(),
               "matches_saved_graph": not differences, "differences": differences},
}
args.out.mkdir(parents=True, exist_ok=True)
path = args.out / "audit_report.json"  # no hashes or timestamps, so the committed report only changes when the data does
path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")

print(f"chain: {result.blocks_checked} blocks, {'VERIFIED' if result.ok else 'FAILED'}"
      f" ({'with' if anchor else 'without'} anchor)")
for p in result.problems[:10]:
    print(f"  block {p['idx']}: {p['check']}: {p['detail']}")
print("blocks by operation:", report["blocks_by_operation"])
print(f"replay: {rebuilt.number_of_nodes()} nodes, {rebuilt.number_of_edges()} edges; "
      f"matches {args.graph}: {not differences}")
for d in differences:
    print("  ", d)
print("->", path)

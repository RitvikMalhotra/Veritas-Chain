"""CLI: python -m veritas.extract --data data --out output/phase2 [--model en_core_web_sm] [--evaluate]"""

import argparse
import json
from pathlib import Path

from veritas.extract.documents import load_firs
from veritas.extract.pipeline import DEFAULT_MODEL, Extractor

parser = argparse.ArgumentParser(description="Extract entities from FIR narratives.")
parser.add_argument("--data", type=Path, default=Path("data"))
parser.add_argument("--out", type=Path, default=Path("output/phase2"))
parser.add_argument("--model", default=DEFAULT_MODEL)
parser.add_argument("--evaluate", action="store_true", help="score against data/ground_truth.json (evaluation only)")
args = parser.parse_args()

extractor = Extractor(args.model)
documents = load_firs(args.data / "firs")
predictions = {doc.fir_id: extractor.extract(doc) for doc in documents}
args.out.mkdir(parents=True, exist_ok=True)
entities_path = args.out / f"entities.{args.model}.json"
entities_path.write_text(json.dumps({
    "model": args.model, "model_version": extractor.model_version, "spacy_version": extractor.spacy_version,
    "confidence_note": ("fixed per method and label from veritas/config.py (NER values measured for en_core_web_md); "
                        "not a model probability"),
    "documents": [{"document_id": doc_id, "entities": ents} for doc_id, ents in predictions.items()],
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
print(f"{sum(len(e) for e in predictions.values())} entities from {len(documents)} FIRs -> {entities_path}")

if args.evaluate:
    from veritas.extract.evaluate import score  # ground truth is only touched in evaluation mode

    truth = json.loads((args.data / "ground_truth.json").read_text(encoding="utf-8"))
    result = score(truth["fir_annotations"]["reports"], predictions)
    result = {"model": args.model, "model_version": extractor.model_version, "data": str(args.data), **result}
    eval_path = args.out / f"evaluation.{args.model}.json"
    eval_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    def pct(x):
        return "  n/a" if x is None else f"{100 * x:5.1f}"

    print(f"\n{'type':<13}{'gold':>5}{'pred':>5} | strict P / R / F1    | lenient P / R / F1   | same-key R")
    for t, r in result["per_type"].items():
        s, l, k = r["strict"], r["lenient"], r["same_key"]
        print(f"{t:<13}{r['gold']:>5}{r['predicted']:>5} | {pct(s['precision'])} {pct(s['recall'])} {pct(s['f1'])} "
              f"| {pct(l['precision'])} {pct(l['recall'])} {pct(l['f1'])} | {pct(k['recall'])}")
    print("errors:", {kind: len(items) for kind, items in result["errors"].items()}, "->", eval_path)

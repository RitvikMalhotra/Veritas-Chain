"""Scores relation extraction against ground truth and the hand-written challenge set (evaluation only)."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from veritas import normalize
from veritas.extract.documents import load_firs
from veritas.extract.relations import TextRelation, interpret_document
from veritas.models import EdgeType, ExtractionMethod, NodeType, make_node_id

PATTERN_TYPES = [t.value for t in EdgeType if t != EdgeType.ASSOCIATED_WITH]


def event_id(document_id: str) -> str:
    return make_node_id(NodeType.EVENT, normalize.text_key(document_id))


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p and r else None}


def score_relations(gold: dict[str, set[tuple]], predicted: dict[str, list[TextRelation]]) -> dict[str, Any]:
    counts = {t: [0, 0, 0] for t in PATTERN_TYPES}  # tp, fp, fn
    errors: dict[str, list] = {"false_positive": [], "false_negative": []}
    for doc_id in sorted(set(gold) | set(predicted)):
        pred = {(r.edge_type.value, r.source_id, r.target_id): r for r in predicted.get(doc_id, [])
                if r.method == ExtractionMethod.TEXT_PATTERN}
        want = gold.get(doc_id, set())
        for key, rel in pred.items():
            counts[key[0]][0 if key in want else 1] += 1
            if key not in want:
                errors["false_positive"].append({"document_id": doc_id, "type": key[0], "source": key[1],
                                                 "target": key[2], "rule": rel.rule, "sentence": rel.sentence})
        for key in sorted(want - set(pred)):  # sorted: set order follows the hash seed, which made reports differ per run
            counts[key[0]][2] += 1
            errors["false_negative"].append({"document_id": doc_id, "type": key[0], "source": key[1], "target": key[2]})
    per_type = {t: _prf(*c) for t, c in counts.items() if any(c)}
    micro = _prf(*(sum(c[i] for c in counts.values()) for i in range(3)))
    return {"per_type": per_type, "micro": micro, "errors": errors}


def planted_ties(truth: dict[str, Any]) -> set[frozenset[str]]:
    """Pairs of Person node ids with a real tie in the synthetic world. Defined before scoring co-occurrence edges."""
    persons = truth["persons"]
    by_true = {p["true_id"]: p["expected_node_id"] for p in persons}
    ties: set[frozenset[str]] = set()

    def link(ids):
        ties.update(frozenset(pair) for pair in combinations(sorted(set(ids)), 2))

    for c in truth["clusters"]:
        link(by_true[i] for i in [c["leader"], *c["lieutenants"], *c["members"]])  # same cluster
    for b in truth["bridges"]:
        for c in truth["clusters"]:
            if c["cluster_id"] in b["connects"]:
                for i in [c["leader"], *c["lieutenants"], *c["members"]]:
                    ties.add(frozenset((by_true[b["true_id"]], by_true[i])))  # bridge and a member it connects to
    by_org = defaultdict(list)
    for p in persons:
        for org in [p["employer"], *p["director_of"]]:
            if org:
                by_org[org].append(p["expected_node_id"])
    for ids in by_org.values():
        link(ids)  # same company
    for ann in truth["fir_annotations"]["reports"].values():
        present = [r["source"] for r in ann["relations"] if r["type"] == "PRESENT_AT_EVENT" and r["source"].startswith("Person:")]
        link(present)  # present at the same incident
        for r in ann["relations"]:
            if r["source"].startswith("Person:") and r["target"].startswith("Person:"):
                ties.add(frozenset((r["source"], r["target"])))  # a stated person-to-person relation
    return {t for t in ties if len(t) == 2}


def score_cooccurrence(predicted: dict[str, list[TextRelation]], ties: set[frozenset[str]]) -> dict[str, Any]:
    edges = [(doc_id, r) for doc_id, rels in predicted.items() for r in rels if r.method == ExtractionMethod.TEXT_COOCCURRENCE]
    good = [(d, r) for d, r in edges if frozenset((r.source_id, r.target_id)) in ties]
    return {
        "edges": len(edges), "tied": len(good), "precision": len(good) / len(edges) if edges else None,
        "tie_definition": "same cluster; bridge and a member of a cluster it connects; same company; "
                          "present at the same incident; or a stated person-to-person relation in any report",
        "untied": [{"document_id": d, "source": r.source_id, "target": r.target_id, "sentence": r.sentence}
                   for d, r in edges if (d, r) not in good],
    }


def gold_relations(truth: dict[str, Any]) -> dict[str, set[tuple]]:
    return {doc_id: {(r["type"], r["source"], r["target"]) for r in ann["relations"]}
            for doc_id, ann in truth["fir_annotations"]["reports"].items()}


def run_documents(data: Path, records_by_doc: dict[str, list[dict]]) -> dict[str, list[TextRelation]]:
    return {doc.fir_id: interpret_document(doc.fir_id, doc.narrative, records_by_doc.get(doc.fir_id, []),
                                           event_id(doc.fir_id)).relations
            for doc in load_firs(data / "firs")}


def challenge_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        records, pos = [], 0
        for text, node_type in case["entities"]:  # locate each entity in order of appearance
            start = case["text"].index(text, pos)
            records.append({"text": text, "node_type": node_type, "start": start, "end": start + len(text)})
            pos = start + len(text)
        case["records"] = records
    return cases


def score_challenge(path: Path) -> dict[str, Any]:
    cases = challenge_cases(path)
    predicted, gold = {}, {}
    for case in cases:
        predicted[case["id"]] = interpret_document(case["id"], case["text"], case["records"], event_id(case["id"])).relations
        gold[case["id"]] = {(t, s, event_id(case["id"]) if d == "EVENT" else d) for t, s, d in case["expected"]}
    result = score_relations(gold, predicted)
    result["per_case"] = {
        case["id"]: {"text": case["text"],
                     "expected": sorted(gold[case["id"]]),
                     "predicted": sorted((r.edge_type.value, r.source_id, r.target_id) for r in predicted[case["id"]]
                                         if r.method == ExtractionMethod.TEXT_PATTERN)}
        for case in cases
    }
    return result


def _pct(x):
    return "  n/a" if x is None else f"{100 * x:5.1f}"


def _print_block(title: str, result: dict[str, Any]) -> None:
    print(f"\n{title}")
    print(f"  {'type':<22}{'tp':>4}{'fp':>4}{'fn':>4}   P      R      F1")
    for t, r in result["per_type"].items():
        print(f"  {t:<22}{r['tp']:>4}{r['fp']:>4}{r['fn']:>4} {_pct(r['precision'])}  {_pct(r['recall'])}  {_pct(r['f1'])}")
    m = result["micro"]
    print(f"  {'ALL (micro)':<22}{m['tp']:>4}{m['fp']:>4}{m['fn']:>4} {_pct(m['precision'])}  {_pct(m['recall'])}  {_pct(m['f1'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate relation extraction.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--entities", type=Path, default=Path("output/phase2/entities.en_core_web_md.json"))
    parser.add_argument("--challenge", type=Path, default=Path("tests/fixtures/relation_challenge.json"))
    parser.add_argument("--out", type=Path, default=Path("output/phase3"))
    args = parser.parse_args()

    truth = json.loads((args.data / "ground_truth.json").read_text(encoding="utf-8"))
    gold = gold_relations(truth)
    oracle_records = {d: a["mentions"] for d, a in truth["fir_annotations"]["reports"].items()}
    extracted = json.loads(args.entities.read_text(encoding="utf-8"))
    e2e_records = {d["document_id"]: d["entities"] for d in extracted["documents"]}

    oracle_pred = run_documents(args.data, oracle_records)
    e2e_pred = run_documents(args.data, e2e_records)
    ties = planted_ties(truth)
    report = {
        "data": str(args.data),
        "oracle_entities": score_relations(gold, oracle_pred),
        "end_to_end": {"entities": str(args.entities), **score_relations(gold, e2e_pred)},
        "cooccurrence_oracle": score_cooccurrence(oracle_pred, ties),
        "cooccurrence_end_to_end": score_cooccurrence(e2e_pred, ties),
        "challenge_set": score_challenge(args.challenge),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "relations_evaluation.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    _print_block("Gold entities -> relation rules", report["oracle_entities"])
    _print_block("End to end (spaCy md entities -> relation rules)", report["end_to_end"])
    _print_block("Challenge set (gold entities, different phrasing)", report["challenge_set"])
    for label in ("cooccurrence_oracle", "cooccurrence_end_to_end"):
        c = report[label]
        print(f"\n{label}: {c['tied']}/{c['edges']} same-sentence edges join people with a planted tie -> precision {_pct(c['precision'])}")
    print(f"\n-> {out_path}")


if __name__ == "__main__":
    main()

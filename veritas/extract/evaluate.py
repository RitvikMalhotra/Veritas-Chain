"""Scores extracted entities against the planted mentions in ground_truth.json (evaluation only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from veritas.extract.pipeline import canonical_key
from veritas.models import NodeType

NER_TYPES = ("Person", "Location", "Organization")
REGEX_TYPES = ("Phone", "Vehicle")


def _overlap(a: dict, b: dict) -> int:
    return max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def score_document(gold: list[dict], predicted: list[dict]) -> dict[str, Any]:
    """Match one document. Strict = same span and type. Lenient = overlapping span, same type, one-to-one."""
    g = [{"start": m["start"], "end": m["end"], "type": m["node_type"], "text": m["text"]} for m in gold]
    p = [{"start": m["start_char"], "end": m["end_char"], "type": m["node_type"], "text": m["text"],
          "label": m["raw_label"]} for m in predicted]

    strict = {(x["start"], x["end"], x["type"]) for x in g} & {(x["start"], x["end"], x["type"]) for x in p}

    # Greedy one-to-one lenient matching, largest overlap first.
    pairs = sorted(((_overlap(gi, pi), i, j) for i, gi in enumerate(g) for j, pi in enumerate(p)
                    if gi["type"] == pi["type"] and _overlap(gi, pi) > 0), reverse=True)
    g_matched: dict[int, int] = {}
    p_matched: set[int] = set()
    for _, i, j in pairs:
        if i not in g_matched and j not in p_matched:
            g_matched[i] = j
            p_matched.add(j)

    errors: dict[str, list] = {"boundary": [], "wrong_type": [], "false_positive": [], "false_negative": []}
    for i, j in g_matched.items():
        if (g[i]["start"], g[i]["end"]) != (p[j]["start"], p[j]["end"]):
            errors["boundary"].append({"gold": g[i]["text"], "predicted": p[j]["text"], "type": g[i]["type"]})
    for j, pj in enumerate(p):
        if j in p_matched:
            continue
        clash = next((gi for i, gi in enumerate(g) if i not in g_matched and _overlap(gi, pj) > 0), None)
        if clash:
            errors["wrong_type"].append({"text": pj["text"], "gold_type": clash["type"], "predicted_type": pj["type"],
                                         "spacy_label": pj["label"]})
        else:
            errors["false_positive"].append({"text": pj["text"], "predicted_type": pj["type"], "spacy_label": pj["label"]})
    for i, gi in enumerate(g):
        if i not in g_matched:
            errors["false_negative"].append({"text": gi["text"], "type": gi["type"]})

    counts = {}
    for t in (*NER_TYPES, *REGEX_TYPES):
        g_t = [i for i, x in enumerate(g) if x["type"] == t]
        p_t = [j for j, x in enumerate(p) if x["type"] == t]
        strict_tp = sum(1 for k in strict if k[2] == t)
        lenient_tp = sum(1 for i in g_t if i in g_matched)
        same_key = sum(1 for i in g_t if i in g_matched
                       and canonical_key(NodeType(t), p[g_matched[i]]["text"]) == canonical_key(NodeType(t), g[i]["text"]))
        counts[t] = {"gold": len(g_t), "predicted": len(p_t), "strict_tp": strict_tp, "lenient_tp": lenient_tp,
                     "same_key_tp": same_key}
    return {"counts": counts, "errors": errors}


def score(gold_reports: dict[str, dict], predictions: dict[str, list[dict]]) -> dict[str, Any]:
    totals = {t: defaultdict(int) for t in (*NER_TYPES, *REGEX_TYPES)}
    errors: dict[str, list] = defaultdict(list)
    for doc_id, ann in sorted(gold_reports.items()):
        result = score_document(ann["mentions"], predictions.get(doc_id, []))
        for t, c in result["counts"].items():
            for k, v in c.items():
                totals[t][k] += v
        for kind, items in result["errors"].items():
            errors[kind].extend({"document_id": doc_id, **item} for item in items)

    def block(types) -> dict[str, Any]:
        out = {}
        for mode, tp_key in (("strict", "strict_tp"), ("lenient", "lenient_tp"), ("same_key", "same_key_tp")):
            tp = sum(totals[t][tp_key] for t in types)
            gold = sum(totals[t]["gold"] for t in types)
            pred = sum(totals[t]["predicted"] for t in types)
            out[mode] = _prf(tp, pred - tp, gold - tp)
        return out

    return {
        "matching": {
            "strict": "same start, end and type",
            "lenient": "overlapping span and same type, matched one-to-one",
            "same_key": "lenient match whose canonical key equals the gold mention's key (boundary error is harmless)",
        },
        "per_type": {t: {"gold": totals[t]["gold"], "predicted": totals[t]["predicted"], **block([t])} for t in totals},
        "spacy_types_micro": block(NER_TYPES),
        "regex_types_micro": block(REGEX_TYPES),
        "errors": dict(errors),
    }

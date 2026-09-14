"""Build report (pipeline facts only) and graph evaluation against ground truth (evaluation only)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

import networkx as nx

from veritas.extract.relation_eval import gold_relations, score_relations
from veritas.extract.relations import TextRelation
from veritas.models import EdgeType, ExtractionMethod


def _docs(attrs: dict[str, Any]) -> list[str]:
    docs = attrs.get("source_document_ids", [])
    return json.loads(docs) if isinstance(docs, str) else docs


def build_report(graph: nx.MultiDiGraph, stats: Counter, name_variants: dict[str, set[str]]) -> dict[str, Any]:
    nodes_by_type = Counter(attrs["type"] for _, attrs in graph.nodes(data=True))
    edges_by_type = Counter(f"{a['type']} ({a['extraction_method']})" for _, _, a in graph.edges(data=True))

    phones_by_person = defaultdict(list)
    for src, dst, a in graph.edges(data=True):
        if a["type"] == "USES_PHONE" and a["extraction_method"] == "structured":
            phones_by_person[src].append((dst, a["source_document_id"]))
    text_only = defaultdict(list)
    for node_id, attrs in graph.nodes(data=True):
        if all(d.startswith("FIR-") for d in _docs(attrs)):
            text_only[attrs["type"]].append(node_id)

    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "nodes_by_type": dict(sorted(nodes_by_type.items())),
        "edges_by_type": dict(sorted(edges_by_type.items())),
        "builder_stats": dict(sorted(stats.items())),
        "entity_resolution": {
            "rule": "exact match on canonical key (schema.md section 7); no fuzzy matching",
            "persons_with_several_subscriber_records": {
                p: [{"phone": ph, "record": doc} for ph, doc in v] for p, v in sorted(phones_by_person.items()) if len(v) > 1
            },
            "note_on_several_subscriber_records": ("either one person with several SIMs or several people sharing a name; "
                                                   "exact matching cannot tell these apart"),
            "display_name_variants_merged": {k: sorted(v) for k, v in sorted(name_variants.items()) if len(v) > 1},
            "text_only_nodes": {t: sorted(ids) for t, ids in sorted(text_only.items())},
        },
    }


def evaluate_graph(graph: nx.MultiDiGraph, truth: dict[str, Any]) -> dict[str, Any]:
    persons = truth["persons"]
    person_ids = {p["expected_node_id"] for p in persons}

    collision = truth["planted_collisions"][0]
    phones_of_node = {dst for _, dst, a in graph.out_edges(collision["expected_node_id"], data=True)
                      if a["type"] == "USES_PHONE" and a["extraction_method"] == "structured"}
    collision_phones = {f"Phone:{n}" for p in collision["true_persons"] for n in p["phones"]}

    def in_graph_for(node: str, doc_id: str) -> bool:
        return graph.has_node(node) and doc_id in _docs(graph.nodes[node])

    linked = defaultdict(lambda: {"as_node": 0, "as_city_of_place": 0, "unlinked": 0})
    unlinked = []
    for doc_id, ann in truth["fir_annotations"]["reports"].items():
        previous = None
        for m in sorted(ann["mentions"], key=lambda x: x["start"]):
            node, bucket = m["expected_node_id"], "unlinked"
            if in_graph_for(node, doc_id):
                bucket = "as_node"
            elif (m["node_type"] == "Location" and previous and previous["node_type"] == "Location"
                  and previous["end"] + 2 == m["start"] and previous["expected_node_id"].endswith(":" + node.split(":", 1)[1])
                  and in_graph_for(previous["expected_node_id"], doc_id)):
                bucket = "as_city_of_place"  # "Balan Warehouse, Mumbai": the city is stored on the place node, by design
            linked[m["node_type"]][bucket] += 1
            if bucket == "unlinked":
                unlinked.append({"document_id": doc_id, "text": m["text"], "type": m["node_type"], "expected": node})
            previous = m

    known = set(person_ids)
    for p in persons:
        known.update(f"Phone:{n}" for n in p["phones"])
        known.update(x for x in [p["account"], p["employer"], *p["vehicles"], *p["director_of"]] if x)
    for c in truth["clusters"]:
        known.update(c["meeting_places"])
        if c["front_organization"]:
            known.add(c["front_organization"])
    known.update(m["expected_node_id"] for a in truth["fir_annotations"]["reports"].values() for m in a["mentions"])
    junk = defaultdict(list)
    for node_id, attrs in graph.nodes(data=True):
        if all(d.startswith("FIR-") for d in _docs(attrs)) and node_id not in known:
            junk[attrs["type"]].append(node_id)

    # Text edges actually written to the graph, scored against annotated relations (should match relation_eval end to end).
    in_graph = defaultdict(list)
    for src, dst, a in graph.edges(data=True):
        if a["extraction_method"] == ExtractionMethod.TEXT_PATTERN.value:
            in_graph[a["source_document_id"]].append(
                TextRelation(EdgeType(a["type"]), src, dst, ExtractionMethod.TEXT_PATTERN, "", a["confidence"], ""))

    return {
        "true_persons_present": f"{sum(1 for p in person_ids if graph.has_node(p))}/{len(person_ids)}",
        "planted_collision": {
            "node": collision["expected_node_id"],
            "merged_as_expected": collision_phones <= phones_of_node,
            "phones_on_merged_node": sorted(phones_of_node),
            "explanation": "two different people named Rahul Sharma became one node (known false merge, schema.md section 7)",
        },
        "text_mentions_linked_to_expected_node": {
            t: {**v, "total": sum(v.values()), "rate": (v["as_node"] + v["as_city_of_place"]) / sum(v.values())}
            for t, v in sorted(linked.items())
        },
        "unlinked_mentions": unlinked,
        "text_only_nodes_not_in_ground_truth": {t: sorted(v) for t, v in sorted(junk.items())},
        "text_pattern_edges_vs_annotations": score_relations(gold_relations(truth), in_graph),
    }

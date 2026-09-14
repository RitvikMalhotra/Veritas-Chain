"""Projects the heterogeneous graph onto actors (people and companies) so centrality ranks individuals, not phones."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx

ACTOR_TYPES = ("Person", "Organization")
VARIANTS = ("all_evidence", "no_cooccurrence", "structured_only")


def _keep(attrs: dict, variant: str) -> bool:
    if variant == "structured_only":
        return attrs["extraction_method"] == "structured"
    if variant == "no_cooccurrence":
        return attrs["extraction_method"] != "text_cooccurrence"
    return True


def actor_graph(graph: nx.MultiDiGraph, variant: str = "all_evidence") -> nx.DiGraph:
    """Directed, weighted actor graph. Each underlying record adds its confidence to the weight of the actor pair."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    actors = nx.DiGraph()
    actors.add_nodes_from((n, {"type": a["type"]}) for n, a in graph.nodes(data=True) if a["type"] in ACTOR_TYPES)
    edges = [(s, d, a) for s, d, a in graph.edges(data=True) if _keep(a, variant)]

    def bump(u: str, v: str, weight: float, kind: str) -> None:
        if u == v:
            return  # e.g. two phones of the same person calling each other
        data = actors.get_edge_data(u, v) or {"weight": 0.0}
        data["weight"] += weight
        data[kind] = data.get(kind, 0.0) + weight
        actors.add_edge(u, v, **data)

    users, holders = defaultdict(list), defaultdict(list)  # phone -> [(person, conf)], account -> [(holder, conf)]
    by_event, by_meeting = defaultdict(list), defaultdict(list)
    for s, d, a in edges:
        if a["type"] == "USES_PHONE":
            users[d].append((s, a["confidence"]))
        elif a["type"] == "HOLDS_ACCOUNT":
            holders[d].append((s, a["confidence"]))
        elif a["type"] == "PRESENT_AT_EVENT" and s.startswith("Person:"):
            by_event[d].append((s, a["confidence"]))
        elif a["type"] == "MET_AT":
            by_meeting[(d, a["source_document_id"])].append((s, a["confidence"]))

    for s, d, a in edges:
        conf, kind = a["confidence"], a["type"]
        if kind in ("CALLED", "TRANSFERRED_MONEY_TO"):
            if s.startswith(ACTOR_TYPES) and d.startswith(ACTOR_TYPES):
                bump(s, d, conf, kind)  # text: person to person
                continue
            owners = users if kind == "CALLED" else holders
            src, dst = owners.get(s, []), owners.get(d, [])
            share = 1 / (len(src) * len(dst)) if src and dst else 0  # a shared phone or account splits its weight
            for u, cu in src:
                for v, cv in dst:
                    bump(u, v, min(conf, cu, cv) * share, kind)
        elif kind == "MEMBER_OF":
            bump(s, d, conf, kind)
            bump(d, s, conf, kind)
        elif kind == "ASSOCIATED_WITH" and s.startswith("Person:") and d.startswith("Person:"):
            bump(s, d, conf, kind)
            bump(d, s, conf, kind)
    for group, kind in ((by_event, "co_present"), (by_meeting, "met_together")):
        for members in group.values():
            for (u, cu), (v, cv) in combinations(members, 2):  # being at the same incident or meeting
                bump(u, v, min(cu, cv), kind)
                bump(v, u, min(cu, cv), kind)
    return actors


def undirected(actors: nx.DiGraph) -> nx.Graph:
    """Sums both directions. 'distance' = 1/weight, so strong ties are short paths for betweenness."""
    und = nx.Graph()
    und.add_nodes_from(actors.nodes(data=True))
    for u, v, a in actors.edges(data=True):
        w = a["weight"] + (und[u][v]["weight"] if und.has_edge(u, v) else 0.0)
        und.add_edge(u, v, weight=w, distance=1 / w)
    return und

"""Degree, betweenness and PageRank rankings for people, and Louvain communities, on the actor graph."""

from __future__ import annotations

from typing import Any

import networkx as nx

from veritas.analytics.projection import undirected


def _ranked(scores: dict[str, float], nodes: list[str]) -> list[dict[str, Any]]:
    order = sorted(nodes, key=lambda n: (-scores.get(n, 0.0), n))  # ties broken by node id, so output is stable
    return [{"rank": i + 1, "node": n, "score": round(scores.get(n, 0.0), 6)} for i, n in enumerate(order)]


def centrality_rankings(actors: nx.DiGraph) -> dict[str, list[dict[str, Any]]]:
    """Scores are computed on all actors; rankings list people only."""
    und = undirected(actors)
    people = sorted(n for n, a in actors.nodes(data=True) if a["type"] == "Person")
    return {
        # Number of distinct contacts, ignoring strength.
        "degree": _ranked(nx.degree_centrality(und), people),
        # Share of shortest paths passing through a person; strong ties count as short (distance = 1/weight).
        "betweenness": _ranked(nx.betweenness_centrality(und, weight="distance", normalized=True), people),
        # Importance flowing along directed calls, payments and ties, weighted by evidence strength.
        "pagerank": _ranked(nx.pagerank(actors, weight="weight"), people),
    }


def _sorted(communities) -> list[list[str]]:
    return sorted((sorted(c) for c in communities), key=lambda c: (-len(c), c[0]))


def louvain(actors: nx.DiGraph, seed: int, resolution: float) -> list[list[str]]:
    und = undirected(actors)
    return _sorted(nx.community.louvain_communities(und, weight="weight", resolution=resolution, seed=seed))


def nested_louvain(actors: nx.DiGraph, seed: int, resolution: float, min_modularity: float) -> list[list[str]]:
    """Louvain, then Louvain again inside each community. A split is kept only if its own modularity is high enough."""
    und = undirected(actors)
    result = []
    for community in nx.community.louvain_communities(und, weight="weight", resolution=resolution, seed=seed):
        # A copy minus other nodes keeps the parent's node order; und.subgraph(set) iterates in hash order, so results varied.
        sub = und.copy()
        sub.remove_nodes_from([n for n in und if n not in community])
        if sub.number_of_edges():  # modularity is undefined without edges
            parts = nx.community.louvain_communities(sub, weight="weight", resolution=resolution, seed=seed)
            if len(parts) > 1 and nx.community.modularity(sub, parts, weight="weight", resolution=resolution) >= min_modularity:
                result.extend(parts)
                continue
        result.append(community)
    return _sorted(result)

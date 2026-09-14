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


def louvain(actors: nx.DiGraph, seed: int, resolution: float) -> list[list[str]]:
    und = undirected(actors)
    communities = nx.community.louvain_communities(und, weight="weight", resolution=resolution, seed=seed)
    return sorted((sorted(c) for c in communities), key=lambda c: (-len(c), c[0]))

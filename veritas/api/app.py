"""Read-only API: the graph, neighbourhoods, centrality rankings, audit history and chain verification."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from fastapi import FastAPI, HTTPException, Query

from veritas.analytics.centrality import centrality_rankings
from veritas.analytics.projection import VARIANTS, actor_graph
from veritas.audit.chain import Anchor, Block, read_blocks, read_history, verify_chain
from veritas.audit.replay import graph_differences, replay
from veritas.config import ApiSettings
from veritas.graph.io import load_graphml

SYNTHETIC_NOTICE = "All data is synthetic. No real people, numbers, accounts or law-enforcement records."
Metric = Literal["degree", "betweenness", "pagerank"]
Variant = Literal["all_evidence", "no_cooccurrence", "structured_only"]


def node_label(attrs: dict[str, Any]) -> str:
    kind = attrs["type"]
    if kind == "Location" and attrs.get("city"):
        return f"{attrs['name']}, {attrs['city']}"
    if kind == "BankAccount":
        return f"{attrs['ifsc']} {attrs['account_number']}"
    field = {"Phone": "number", "Vehicle": "registration_number", "Event": "event_ref"}.get(kind, "name")
    return str(attrs[field])


def _node_element(graph: nx.MultiDiGraph, node_id: str, position: tuple[float, float]) -> dict[str, Any]:
    attrs = graph.nodes[node_id]
    data = {k: v for k, v in attrs.items() if k != "source_document_ids"}  # the full list is on the node endpoint
    data.update(id=node_id, label=node_label(attrs), source_document_count=len(attrs["source_document_ids"]))
    return {"group": "nodes", "data": data, "position": {"x": position[0], "y": position[1]}}


def _edge_elements(edges: list[tuple[str, str, str, dict[str, Any]]], aggregate: bool) -> list[dict[str, Any]]:
    if not aggregate:
        return [{"group": "edges", "data": {**attrs, "id": key, "source": u, "target": v}} for u, v, key, attrs in edges]
    groups: dict[tuple[str, str, str], list[tuple[str, dict[str, Any]]]] = {}
    for u, v, key, attrs in edges:
        groups.setdefault((u, v, attrs["type"]), []).append((key, attrs))
    elements = []
    for (u, v, kind), members in groups.items():
        members.sort(key=lambda m: (datetime.fromisoformat(m[1]["timestamp"]), m[0]))  # oldest first
        elements.append({"group": "edges", "data": {
            "id": f"group:{kind}:{u}->{v}", "source": u, "target": v, "type": kind, "count": len(members),
            "edge_ids": [m[0] for m in members],
            "first": members[0][1]["timestamp"], "last": members[-1][1]["timestamp"],
            "extraction_methods": sorted({m[1]["extraction_method"] for m in members}),
            "max_confidence": max(m[1]["confidence"] for m in members),
        }})
    return elements


def _elements(graph: nx.MultiDiGraph, nodes, aggregate: bool, positions: dict[str, tuple[float, float]]) -> dict[str, Any]:
    nodes = set(nodes)
    edges = [(u, v, k, a) for u, v, k, a in graph.edges(keys=True, data=True) if u in nodes and v in nodes]
    node_elements = [_node_element(graph, n, positions[n]) for n in graph.nodes if n in nodes]  # graph order: stable output
    edge_elements = _edge_elements(edges, aggregate)
    return {"counts": {"nodes": len(node_elements), "edges": len(edges), "edge_elements": len(edge_elements)},
            "elements": node_elements + edge_elements}


def _block_json(block: Block) -> dict[str, Any]:
    data = asdict(block)
    data["payload"] = block.content()
    return data


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Loads everything once at startup; every endpoint is read-only."""
    settings = settings or ApiSettings()
    for label, path in (("graph", settings.graph_path), ("audit log", settings.audit_path)):
        if not Path(path).exists():
            raise FileNotFoundError(f"{label} not found at {path}: run python -m veritas.graph first")
    graph = load_graphml(settings.graph_path)
    neighbourhoods = nx.Graph(graph)  # undirected, parallel edges collapsed: only used to find who is near whom
    # Seeded layout computed once (~2 s): the browser draws instantly and every load shows the same map.
    positions = {n: (round(float(x) * 1500, 1), round(float(y) * 1500, 1))
                 for n, (x, y) in nx.spring_layout(neighbourhoods, seed=42, iterations=100).items()}
    edge_ids = {k for _, _, k in graph.edges(keys=True)}
    # Rankings come from the graph being served, with the Phase 4 code, so they can't drift from what is shown.
    rankings = {variant: centrality_rankings(actor_graph(graph, variant)) for variant in VARIANTS}
    loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    app = FastAPI(title="Veritas-Chain", description=SYNTHETIC_NOTICE, version="1.0")

    def require_node(node_id: str) -> None:
        if node_id not in graph:
            raise HTTPException(404, f"no node {node_id!r}")

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {
            "notice": SYNTHETIC_NOTICE, "loaded_at": loaded_at,
            "graph": {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
                      "node_types": dict(sorted(Counter(a["type"] for _, a in graph.nodes(data=True)).items())),
                      "edge_types": dict(sorted(Counter(a["type"] for _, _, a in graph.edges(data=True)).items()))},
            "metrics": ["betweenness", "pagerank", "degree"], "variants": list(VARIANTS),
            "anchor_available": Path(settings.anchor_path).exists(),
        }

    @app.get("/api/graph")
    def full_graph(aggregate: bool = True) -> dict[str, Any]:
        return _elements(graph, graph.nodes, aggregate, positions)

    @app.get("/api/nodes/{node_id}")
    def node(node_id: str) -> dict[str, Any]:
        require_node(node_id)
        attrs = graph.nodes[node_id]
        return {
            "id": node_id, "type": attrs["type"], "label": node_label(attrs),
            "attributes": {k: v for k, v in attrs.items() if k != "source_document_ids"},
            "source_document_ids": attrs["source_document_ids"],
            "outgoing_edges": dict(sorted(Counter(a["type"] for _, _, a in graph.out_edges(node_id, data=True)).items())),
            "incoming_edges": dict(sorted(Counter(a["type"] for _, _, a in graph.in_edges(node_id, data=True)).items())),
            "neighbours": neighbourhoods.degree(node_id),
        }

    @app.get("/api/nodes/{node_id}/subgraph")
    def subgraph(node_id: str, depth: int = Query(1, ge=1, le=3), aggregate: bool = True) -> dict[str, Any]:
        require_node(node_id)
        nearby = nx.single_source_shortest_path_length(neighbourhoods, node_id, cutoff=depth)
        return {"center": node_id, "depth": depth, **_elements(graph, nearby, aggregate, positions)}

    @app.get("/api/centrality")
    def centrality(metric: Metric = "betweenness", variant: Variant = "structured_only",
                   limit: int = Query(15, ge=1, le=1000)) -> dict[str, Any]:
        ranking = rankings[variant][metric]
        return {
            "metric": metric, "variant": variant, "people_ranked": len(ranking),
            "note": ("Computed on the actor projection (people and companies); only people are listed. "
                     "Leaders who stay insulated can rank low, so a low rank is not evidence of innocence."),
            "ranking": [{**row, "label": node_label(graph.nodes[row["node"]])} for row in ranking[:limit]],
        }

    @app.get("/api/audit/history/{entity_id}")
    def history(entity_id: str, include_edges: bool = False, limit: int = Query(50, ge=1, le=1000),
                offset: int = Query(0, ge=0)) -> dict[str, Any]:
        if entity_id not in graph and entity_id not in edge_ids:
            raise HTTPException(404, f"no node or edge {entity_id!r}")
        total, blocks = read_history(settings.audit_path, entity_id, include_edges, limit, offset)
        return {"entity_id": entity_id, "include_edges": include_edges, "total": total, "offset": offset,
                "limit": limit, "blocks": [_block_json(b) for b in blocks]}

    @app.post("/api/audit/verify")
    def verify() -> dict[str, Any]:
        anchor_path = Path(settings.anchor_path)
        anchor = Anchor(**json.loads(anchor_path.read_text(encoding="utf-8"))) if anchor_path.exists() else None
        result = verify_chain(settings.audit_path, anchor)
        try:
            differences, replay_error = graph_differences(graph, replay(read_blocks(settings.audit_path))), None
        except (KeyError, ValueError) as exc:  # a tampered log may not even replay
            differences, replay_error = [], f"{type(exc).__name__}: {exc}"
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chain": {"ok": result.ok, "blocks_checked": result.blocks_checked, "anchor_checked": anchor is not None,
                      "head": asdict(result.head) if result.head else None,
                      "problem_count": len(result.problems), "problems": result.problems[:50]},
            "served_graph_matches_log": replay_error is None and not differences,
            "differences": differences, "replay_error": replay_error,
        }

    return app

"""Rebuilds a graph from audit blocks alone, to check the log records every write."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import networkx as nx

from veritas.audit.chain import Block
from veritas.graph.io import model_attrs
from veritas.models import EDGE_ADAPTER, NODE_ADAPTER


def replay(blocks: Iterable[Block]) -> nx.MultiDiGraph:
    """Deliberately does not use GraphBuilder, so a builder bug can't hide a gap in the log."""
    nodes: dict[str, Any] = {}
    edges: dict[str, Any] = {}
    for block in blocks:
        data = block.content()
        if block.operation == "node_created":
            node = NODE_ADAPTER.validate_python(data["node"])
            _same_id(block, node.id)
            nodes[node.id] = node
        elif block.operation == "node_merged":
            node = nodes[block.entity_id]
            docs = tuple(dict.fromkeys([*node.source_document_ids, *data["source_document_ids_added"]]))
            nodes[block.entity_id] = node.model_copy(update={"source_document_ids": docs})
        elif block.operation == "edge_created":
            edge = EDGE_ADAPTER.validate_python(data["edge"])
            _same_id(block, edge.id)
            edges[edge.id] = edge
        else:
            raise ValueError(f"block {block.idx}: unknown operation {block.operation!r}")

    graph = nx.MultiDiGraph()
    for edge_id, edge in edges.items():
        attrs = model_attrs(edge)
        attrs.pop("id", None)
        graph.add_edge(edge.source_id, edge.target_id, key=edge_id, **attrs)
    for node_id, node in nodes.items():
        attrs = model_attrs(node)
        attrs.pop("id", None)
        graph.add_node(node_id, **attrs)
    return graph


def _same_id(block: Block, computed: str) -> None:
    if computed != block.entity_id:
        raise ValueError(f"block {block.idx}: payload resolves to {computed}, not {block.entity_id}")


def graph_differences(expected: nx.MultiDiGraph, actual: nx.MultiDiGraph, limit: int = 20) -> list[str]:
    """Human-readable differences in nodes, edge keys and attributes (source_document_ids compared as lists)."""

    def node_attrs(g, n):
        a = dict(g.nodes[n])
        if isinstance(a.get("source_document_ids"), str):
            a["source_document_ids"] = json.loads(a["source_document_ids"])
        return a

    out = []
    for n in sorted(set(expected.nodes) ^ set(actual.nodes)):
        out.append(f"node {n} only in {'expected' if n in expected else 'actual'}")
    for n in sorted(set(expected.nodes) & set(actual.nodes)):
        if node_attrs(expected, n) != node_attrs(actual, n):
            out.append(f"node {n} attributes differ")
    exp_edges = {k: (u, v, a) for u, v, k, a in expected.edges(keys=True, data=True)}
    act_edges = {k: (u, v, a) for u, v, k, a in actual.edges(keys=True, data=True)}
    for k in sorted(set(exp_edges) ^ set(act_edges)):
        out.append(f"edge {k} only in {'expected' if k in exp_edges else 'actual'}")
    for k in sorted(set(exp_edges) & set(act_edges)):
        if exp_edges[k] != act_edges[k]:
            out.append(f"edge {k} differs")
    return out[:limit] + ([f"... {len(out) - limit} more"] if len(out) > limit else [])

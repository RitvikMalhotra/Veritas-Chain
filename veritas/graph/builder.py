"""Builds the NetworkX MultiDiGraph. Every node and edge goes through one validated write path."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import networkx as nx

from veritas.audit.chain import AuditLog
from veritas.graph.io import model_attrs


class GraphBuilder:
    """With an AuditLog attached, every write is recorded as a block *before* the graph changes."""

    def __init__(self, audit: AuditLog | None = None, actor: str = "pipeline") -> None:
        self.graph = nx.MultiDiGraph()
        self.nodes: dict[str, object] = {}  # node id -> Pydantic node model (kept until finalize)
        self.stats: Counter[str] = Counter()
        self.name_variants: dict[str, set[str]] = defaultdict(set)  # node id -> display names that resolved to it
        self.audit = audit
        self.actor = actor  # who these writes are attributed to in the audit log

    def _record(self, operation: str, kind: str, entity_id: str, payload: dict[str, Any],
                source_id: str | None = None, target_id: str | None = None) -> None:
        if self.audit is not None:
            self.audit.append(operation, kind, entity_id, payload, self.actor, source_id, target_id)

    def add_node(self, node) -> str:
        """Exact-match entity resolution: same id = same node. First-seen fields win; provenance is unioned."""
        existing = self.nodes.get(node.id)
        label = getattr(node, "name", None)
        if existing is None:
            self._record("node_created", "node", node.id, {"node": node.model_dump(mode="json")})
            self.nodes[node.id] = node
            self.stats[f"nodes_created:{node.type}"] += 1
        else:
            docs = tuple(dict.fromkeys([*existing.source_document_ids, *node.source_document_ids]))
            if docs != existing.source_document_ids:
                added = list(docs[len(existing.source_document_ids):])
                self._record("node_merged", "node", node.id, {"source_document_ids_added": added})
                self.nodes[node.id] = existing.model_copy(update={"source_document_ids": docs})
            self.stats[f"node_merges:{node.type}"] += 1
        if label:
            self.name_variants[node.id].add(label)
        return node.id

    def add_edge(self, edge) -> bool:
        for endpoint in (edge.source_id, edge.target_id):
            if endpoint not in self.nodes:
                raise KeyError(f"edge {edge.id} ({edge.type}) references missing node {endpoint}")
        if self.graph.has_edge(edge.source_id, edge.target_id, key=edge.id):
            self.stats["duplicate_edges_skipped"] += 1  # deterministic ids make re-loading the same record harmless
            return False
        self._record("edge_created", "edge", edge.id, {"edge": edge.model_dump(mode="json")},
                     source_id=edge.source_id, target_id=edge.target_id)
        attrs = model_attrs(edge)
        attrs.pop("id", None)  # the edge id is the MultiDiGraph key
        self.graph.add_edge(edge.source_id, edge.target_id, key=edge.id, **attrs)
        self.stats[f"edges:{edge.type}:{edge.extraction_method}"] += 1
        return True

    def finalize(self) -> nx.MultiDiGraph:
        for node_id, node in self.nodes.items():
            attrs = model_attrs(node)
            attrs.pop("id", None)
            self.graph.add_node(node_id, **attrs)
        return self.graph

"""Flattening models into graph attributes, and GraphML save/load."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

_JSON_FIELDS = ("source_document_ids",)  # GraphML only stores scalars, so lists are JSON strings on disk


def model_attrs(model) -> dict[str, Any]:
    data = model.model_dump(mode="json")  # datetimes -> ISO strings, Decimal -> string
    return {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in data.items() if v is not None}


def save_graphml(graph: nx.MultiDiGraph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, path, encoding="utf-8")


def load_graphml(path: Path) -> nx.MultiDiGraph:
    graph = nx.read_graphml(path, force_multigraph=True)
    for _, attrs in graph.nodes(data=True):
        for field in _JSON_FIELDS:
            if field in attrs:
                attrs[field] = json.loads(attrs[field])
    return graph

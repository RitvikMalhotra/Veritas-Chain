"""Phase 6 tests: every endpoint checked against the code it serves from, verification on a tampered copy, frontend guards."""

import json
import re
import shutil
import sqlite3
from pathlib import Path
from urllib.parse import quote

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from veritas.analytics.centrality import centrality_rankings
from veritas.analytics.projection import VARIANTS, actor_graph
from veritas.api.app import STATIC, create_app
from veritas.audit.chain import AuditLog, read_history
from veritas.config import ApiSettings
from veritas.graph.builder import GraphBuilder
from veritas.graph.io import load_graphml, save_graphml
from veritas.graph.loaders import load_structured, load_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The real seed-42 build, written to a temp folder like python -m veritas.graph would."""
    out = tmp_path_factory.mktemp("api")
    settings = ApiSettings(graph_path=out / "graph.graphml", audit_path=out / "audit.sqlite", anchor_path=out / "anchor.json")
    with AuditLog(settings.audit_path) as log:
        builder = GraphBuilder(audit=log)
        load_structured(builder, ROOT / "data")
        load_text(builder, ROOT / "data", ROOT / "output" / "phase2" / "entities.en_core_web_md.json")
        graph = builder.finalize()
        head = log.head()
    save_graphml(graph, settings.graph_path)
    settings.anchor_path.write_text(json.dumps({"idx": head.idx, "hash": head.hash}), encoding="utf-8")
    return settings


@pytest.fixture(scope="module")
def client(built):
    return TestClient(create_app(built))


@pytest.fixture(scope="module")
def graph(built):
    return load_graphml(built.graph_path)


def url_id(entity_id):
    return quote(entity_id, safe="")


# ---------- The API matches its sources ----------


def test_full_graph_returns_exactly_the_loaded_graph(client, graph):
    raw = client.get("/api/graph?aggregate=false").json()
    ids = lambda group: sorted(e["data"]["id"] for e in raw["elements"] if e["group"] == group)
    assert ids("nodes") == sorted(graph.nodes)
    assert ids("edges") == sorted(k for _, _, k in graph.edges(keys=True))

    merged = client.get("/api/graph").json()
    groups = [e["data"] for e in merged["elements"] if e["group"] == "edges"]
    assert sum(g["count"] for g in groups) == graph.number_of_edges() == merged["counts"]["edges"]
    assert sorted(i for g in groups for i in g["edge_ids"]) == ids("edges")  # every edge sits in exactly one group
    for g in groups:
        assert all(graph.edges[g["source"], g["target"], i]["type"] == g["type"] for i in g["edge_ids"])


def test_every_node_has_a_repeatable_position(built, client):
    first = {e["data"]["id"]: e["position"] for e in client.get("/api/graph").json()["elements"] if e["group"] == "nodes"}
    assert all(isinstance(p["x"], float) and isinstance(p["y"], float) for p in first.values())
    again = TestClient(create_app(built)).get("/api/graph").json()
    assert first == {e["data"]["id"]: e["position"] for e in again["elements"] if e["group"] == "nodes"}


@pytest.mark.parametrize("depth", [1, 2])
def test_subgraph_is_the_undirected_neighbourhood(client, graph, depth):
    center = "Person:rahul_sharma"  # the planted false merge: a node with neighbours in two cities
    body = client.get(f"/api/nodes/{url_id(center)}/subgraph?depth={depth}").json()
    expected = nx.ego_graph(nx.Graph(graph), center, radius=depth)
    nodes = {e["data"]["id"] for e in body["elements"] if e["group"] == "nodes"}
    assert nodes == set(expected.nodes)
    induced = graph.subgraph(nodes)
    assert body["counts"]["edges"] == induced.number_of_edges()


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("metric", ["degree", "betweenness", "pagerank"])
def test_centrality_matches_phase4_code(client, graph, variant, metric):
    expected = centrality_rankings(actor_graph(graph, variant))[metric]
    body = client.get(f"/api/centrality?metric={metric}&variant={variant}&limit=1000").json()
    assert [(r["rank"], r["node"], r["score"]) for r in body["ranking"]] == [(r["rank"], r["node"], r["score"]) for r in expected]
    assert body["people_ranked"] == len(expected)


@pytest.mark.parametrize("include_edges", [False, True])
def test_audit_history_matches_the_log(client, built, graph, include_edges):
    phone = next(n for n, a in graph.nodes(data=True) if a["type"] == "Phone")  # id with "+" and ":"
    body = client.get(f"/api/audit/history/{url_id(phone)}?include_edges={str(include_edges).lower()}&limit=1000").json()
    total, blocks = read_history(built.audit_path, phone, include_edges)
    assert body["total"] == total and [b["idx"] for b in body["blocks"]] == [b.idx for b in blocks]
    with AuditLog(built.audit_path) as log:  # the writer's own query agrees with the read-only one
        assert [b.idx for b in log.history(phone, include_edges)] == [b.idx for b in blocks]

    page = client.get(f"/api/audit/history/{url_id(phone)}?include_edges={str(include_edges).lower()}&limit=5&offset=5").json()
    assert [b["idx"] for b in page["blocks"]] == [b.idx for b in blocks[5:10]]


def test_edge_history_is_its_creation_block(client, graph):
    u, v, key = next((u, v, k) for u, v, k, a in graph.edges(keys=True, data=True)
                     if a["type"] == "TRANSFERRED_MONEY_TO" and a["extraction_method"] == "structured")
    body = client.get(f"/api/audit/history/{url_id(key)}").json()
    assert [b["operation"] for b in body["blocks"]] == ["edge_created"]
    assert body["blocks"][0]["payload"]["edge"]["amount_inr"] == graph.edges[u, v, key]["amount_inr"]


# ---------- Verification is real ----------


def test_verify_passes_on_the_untampered_log(client):
    body = client.post("/api/audit/verify").json()
    assert body["chain"]["ok"] and body["chain"]["anchor_checked"] and body["served_graph_matches_log"]
    assert body["chain"]["problems"] == [] and body["replay_error"] is None


def test_verify_reports_a_tampered_copy(built, tmp_path):
    copy = tmp_path / "tampered.sqlite"
    shutil.copyfile(built.audit_path, copy)
    conn = sqlite3.connect(copy)
    conn.execute("DROP TRIGGER blocks_no_update")
    idx, payload = next((i, json.loads(p)) for i, p in conn.execute("SELECT idx, payload FROM blocks WHERE operation = 'edge_created'")
                        if json.loads(p)["edge"]["type"] == "TRANSFERRED_MONEY_TO")
    payload["edge"]["amount_inr"] = "1.00"
    conn.execute("UPDATE blocks SET payload = ? WHERE idx = ?", (json.dumps(payload), idx))
    conn.commit()
    conn.close()

    client = TestClient(create_app(built.model_copy(update={"audit_path": copy})))
    body = client.post("/api/audit/verify").json()
    assert not body["chain"]["ok"] and {(p["idx"], p["check"]) for p in body["chain"]["problems"]} == {(idx, "hash")}
    assert not body["served_graph_matches_log"] and any(payload["edge"]["id"] in d for d in body["differences"])
    trigger = sqlite3.connect(copy).execute("SELECT count(*) FROM sqlite_master WHERE name = 'blocks_no_update'").fetchone()[0]
    assert trigger == 0  # checking the evidence must not quietly repair it


# ---------- IDs and bad input ----------


def test_ids_with_plus_and_colon_round_trip(client, graph):
    for node_id in (next(n for n in graph if n.startswith("Phone:+")), next(n for n in graph if n.startswith("BankAccount:"))):
        body = client.get(f"/api/nodes/{url_id(node_id)}").json()
        assert body["id"] == node_id and len(body["source_document_ids"]) == len(graph.nodes[node_id]["source_document_ids"])


@pytest.mark.parametrize("path, status", [
    ("/api/nodes/Person:nobody", 404),
    ("/api/nodes/Person:nobody/subgraph", 404),
    ("/api/audit/history/edge:0000000000000000", 404),
    ("/api/centrality?metric=closeness", 422),
    ("/api/centrality?variant=everything", 422),
    ("/api/nodes/Person:rahul_sharma/subgraph?depth=9", 422),
])
def test_unknown_ids_and_bad_parameters(client, path, status):
    assert client.get(path).status_code == status


def test_page_and_vendored_library_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "synthetic" in page.text.lower()
    script = client.get("/static/app.js")
    assert script.status_code == 200 and client.get("/static/vendor/cytoscape.min.js").status_code == 200
    assert page.headers["cache-control"] == script.headers["cache-control"] == "no-cache"  # no stale app.js after updates


# ---------- Guards ----------


def test_frontend_never_writes_html_from_data():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in source, sink


def test_api_never_reads_ground_truth():
    for path in (ROOT / "veritas" / "api").rglob("*"):
        if path.suffix in {".py", ".js", ".html"}:
            assert not re.search(r"ground_truth", path.read_text(encoding="utf-8")), path

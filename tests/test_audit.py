"""Phase 5 tests: hash format, tamper detection per column, append-only guards, builder hooks, replay completeness."""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from veritas.audit.chain import GENESIS_HASH, Anchor, AuditLog, block_hash, verify_chain
from veritas.audit.replay import graph_differences, replay
from veritas.graph.builder import GraphBuilder
from veritas.graph.loaders import load_structured, load_text
from veritas.models import Person, Phone, UsesPhone

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2025, 1, 1, tzinfo=IST)


def fixed_clock():
    ticks = iter(range(10**6))
    return lambda: datetime(2025, 6, 1, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))


def _chain(path, n=3):
    with AuditLog(path, clock=fixed_clock()) as log:
        for i in range(n):
            log.append("node_created", "node", f"Person:p{i}", {"node": {"name": f"P {i}"}}, "test")
        return log.head()


def _tamper(path, sql, args=()):
    conn = sqlite3.connect(path)
    conn.execute("DROP TRIGGER blocks_no_update")
    conn.execute("DROP TRIGGER blocks_no_delete")
    conn.execute(sql, args)
    conn.commit()
    conn.close()


def _checks(result):
    return {(p["idx"], p["check"]) for p in result.problems}


# ---------- Hash format and chaining ----------


def test_block_hash_matches_the_documented_format():
    # Independent restatement of the README rule: SHA-256 of canonical JSON over every column except the hash.
    material = ('{"actor":"a","entity_id":"Person:x","entity_kind":"node","idx":1,"operation":"node_created",'
                '"payload":"{\\"k\\":1}","prev_hash":"' + GENESIS_HASH + '","recorded_at":"2025-06-01T00:00:00.000000+00:00",'
                '"source_id":null,"target_id":null}')
    expected = hashlib.sha256(material.encode("utf-8")).hexdigest()
    assert block_hash(1, "2025-06-01T00:00:00.000000+00:00", "node_created", "node", "Person:x", None, None, "a",
                      '{"k":1}', GENESIS_HASH) == expected


def test_blocks_link_to_the_previous_hash_and_verify(tmp_path):
    head = _chain(tmp_path / "a.sqlite")
    log = AuditLog(tmp_path / "a.sqlite")
    blocks = list(log.blocks())
    log.close()
    assert blocks[0].prev_hash == GENESIS_HASH
    assert all(b.prev_hash == a.hash for a, b in zip(blocks, blocks[1:]))
    result = verify_chain(tmp_path / "a.sqlite", head)
    assert result.ok and result.blocks_checked == 3 and result.head == head


def test_empty_chain_verifies(tmp_path):
    AuditLog(tmp_path / "e.sqlite").close()
    result = verify_chain(tmp_path / "e.sqlite")
    assert result.ok and result.blocks_checked == 0 and result.head is None


# ---------- Tamper detection ----------


@pytest.mark.parametrize("column, value, expected", [
    ("recorded_at", "2025-06-01T00:00:09.000000+00:00", {(2, "hash")}),
    ("operation", "node_merged", {(2, "hash")}),
    ("entity_kind", "edge", {(2, "hash")}),
    ("entity_id", "Person:someone_else", {(2, "hash")}),
    ("source_id", "Person:x", {(2, "hash")}),
    ("target_id", "Person:y", {(2, "hash")}),
    ("actor", "intruder", {(2, "hash")}),
    ("payload", '{"node":{"name":"Changed"}}', {(2, "hash")}),
    ("prev_hash", "f" * 64, {(2, "hash"), (2, "link")}),
    ("hash", "f" * 64, {(2, "hash"), (3, "link")}),
])
def test_changing_any_stored_column_is_detected(tmp_path, column, value, expected):
    path = tmp_path / "t.sqlite"
    _chain(path)
    _tamper(path, f"UPDATE blocks SET {column} = ? WHERE idx = 2", (value,))
    result = verify_chain(path)
    assert not result.ok and _checks(result) == expected


def test_append_only_triggers_refuse_update_and_delete(tmp_path):
    path = tmp_path / "g.sqlite"
    _chain(path)
    conn = sqlite3.connect(path)
    for sql in ("UPDATE blocks SET actor = 'x' WHERE idx = 1", "DELETE FROM blocks WHERE idx = 1"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute(sql)
    conn.close()


def test_deleting_a_middle_block_breaks_sequence_and_link(tmp_path):
    path = tmp_path / "d.sqlite"
    _chain(path)
    _tamper(path, "DELETE FROM blocks WHERE idx = 2")
    assert _checks(verify_chain(path)) == {(3, "sequence"), (3, "link")}


def test_truncation_and_full_rewrite_pass_internal_checks_but_not_the_anchor(tmp_path):
    path = tmp_path / "r.sqlite"
    head = _chain(path, n=4)
    _tamper(path, "DELETE FROM blocks WHERE idx = 4")
    assert verify_chain(path).ok  # known limitation: a shorter chain is still consistent
    assert _checks(verify_chain(path, head)) == {(4, "anchor")}

    path2 = tmp_path / "r2.sqlite"
    head2 = _chain(path2, n=4)
    conn = sqlite3.connect(path2)
    conn.execute("DROP TRIGGER blocks_no_update")
    cols = "idx, recorded_at, operation, entity_kind, entity_id, source_id, target_id, actor, payload, prev_hash"
    conn.execute("UPDATE blocks SET actor = 'intruder' WHERE idx = 2")
    prev = conn.execute("SELECT hash FROM blocks WHERE idx = 1").fetchone()[0]
    for row in conn.execute(f"SELECT {cols} FROM blocks WHERE idx >= 2 ORDER BY idx").fetchall():
        fields = dict(zip(cols.split(", "), row), prev_hash=prev)
        prev = block_hash(**fields)
        conn.execute("UPDATE blocks SET prev_hash = ?, hash = ? WHERE idx = ?", (fields["prev_hash"], prev, fields["idx"]))
    conn.commit()
    conn.close()
    assert verify_chain(path2).ok  # every hash recomputed: only an outside anchor can tell
    assert _checks(verify_chain(path2, head2)) == {(4, "anchor")}


# ---------- Writer behaviour ----------


def test_failed_build_rolls_back_its_blocks(tmp_path):
    path = tmp_path / "rb.sqlite"
    with pytest.raises(RuntimeError):
        with AuditLog(path) as log:
            log.append("node_created", "node", "Person:p", {}, "test")
            raise RuntimeError("build failed")
    assert verify_chain(path).blocks_checked == 0


def test_a_second_writer_cannot_fork_the_chain(tmp_path):
    path = tmp_path / "f.sqlite"
    first, second = AuditLog(path), AuditLog(path)
    first.append("node_created", "node", "Person:a", {}, "one")
    first.commit()
    with pytest.raises(sqlite3.IntegrityError):  # second still believes the chain is empty, so it reuses block 1
        second.append("node_created", "node", "Person:b", {}, "two")
    first.close()
    second.close()


# ---------- Builder hooks ----------


def _small_build(log):
    b = GraphBuilder(audit=log)
    ravi = b.add_node(Person(name="Ravi Kumar", source_document_ids=["SUB-1"]))
    b.add_node(Person(name="Ravi  Kumar", source_document_ids=["SUB-1"]))  # same key, nothing new: no block
    b.add_node(Person(name="Ravi Kumar", source_document_ids=["FIR-1"]))  # new provenance: node_merged
    phone = b.add_node(Phone(number="9876543210", source_document_ids=["SUB-1"]))
    edge = UsesPhone(source_id=ravi, target_id=phone, timestamp=T0, source_document_id="SUB-1", extraction_method="structured")
    assert b.add_edge(edge) and not b.add_edge(edge)  # duplicate skipped: no block
    return b, ravi, phone, edge


def test_builder_records_each_real_write_once(tmp_path):
    with AuditLog(tmp_path / "b.sqlite", clock=fixed_clock()) as log:
        b, ravi, phone, edge = _small_build(log)
        ops = [(blk.operation, blk.entity_id) for blk in log.blocks()]
        assert ops == [("node_created", ravi), ("node_merged", ravi), ("node_created", phone), ("edge_created", edge.id)]
        merged = log.history(ravi)[1]
        assert merged.content() == {"source_document_ids_added": ["FIR-1"]}
        assert [blk.operation for blk in log.history(phone, include_edges=True)] == ["node_created", "edge_created"]
        assert log.history(edge.id)[0].source_id == ravi


def test_audit_is_written_before_the_graph_changes(tmp_path):
    log = AuditLog(tmp_path / "c.sqlite")
    log.close()  # every append now fails
    b = GraphBuilder(audit=log)
    with pytest.raises(sqlite3.ProgrammingError):
        b.add_node(Person(name="Ravi Kumar", source_document_ids=["SUB-1"]))
    assert b.nodes == {}


# ---------- The real build ----------


@pytest.fixture(scope="module")
def audited_build(tmp_path_factory):
    path = tmp_path_factory.mktemp("audit") / "audit.sqlite"
    with AuditLog(path) as log:
        builder = GraphBuilder(audit=log)
        load_structured(builder, ROOT / "data")
        load_text(builder, ROOT / "data", ROOT / "output" / "phase2" / "entities.en_core_web_md.json")
        graph = builder.finalize()
        head = log.head()
    return path, graph, head


def test_real_build_verifies_against_its_anchor(audited_build):
    path, graph, head = audited_build
    result = verify_chain(path, head)
    assert result.ok and result.blocks_checked == head.idx


def test_replaying_the_log_rebuilds_the_same_graph(audited_build):
    path, graph, _ = audited_build
    log = AuditLog(path)
    try:
        blocks = list(log.blocks())
    finally:
        log.close()
    assert graph_differences(graph, replay(blocks)) == []
    ops = [b.operation for b in blocks]
    assert ops.count("node_created") == graph.number_of_nodes() and ops.count("edge_created") == graph.number_of_edges()

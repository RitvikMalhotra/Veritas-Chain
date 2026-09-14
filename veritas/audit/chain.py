"""Append-only SHA-256 hash chain of graph writes, stored in SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64  # prev_hash of the first block
OPERATIONS = ("node_created", "node_merged", "edge_created")  # every write GraphBuilder makes

_SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    idx         INTEGER PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    operation   TEXT NOT NULL,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('node', 'edge')),
    entity_id   TEXT NOT NULL,
    source_id   TEXT,
    target_id   TEXT,
    actor       TEXT NOT NULL,
    payload     TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS blocks_entity ON blocks (entity_id);
CREATE INDEX IF NOT EXISTS blocks_source ON blocks (source_id);
CREATE INDEX IF NOT EXISTS blocks_target ON blocks (target_id);
-- Stops accidental edits through SQL. Anyone with the file can drop these, which is why the hashes exist.
CREATE TRIGGER IF NOT EXISTS blocks_no_update BEFORE UPDATE ON blocks BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS blocks_no_delete BEFORE DELETE ON blocks BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""
_COLUMNS = ("idx", "recorded_at", "operation", "entity_kind", "entity_id", "source_id", "target_id", "actor", "payload",
            "prev_hash", "hash")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Block:
    idx: int
    recorded_at: str  # UTC ISO timestamp of the write
    operation: str
    entity_kind: str  # node | edge
    entity_id: str
    source_id: str | None  # edge endpoints, so a node's history can include its edges
    target_id: str | None
    actor: str
    payload: str  # canonical JSON text, hashed exactly as stored
    prev_hash: str
    hash: str

    def content(self) -> dict[str, Any]:
        return json.loads(self.payload)


def block_hash(idx: int, recorded_at: str, operation: str, entity_kind: str, entity_id: str, source_id: str | None,
               target_id: str | None, actor: str, payload: str, prev_hash: str) -> str:
    """SHA-256 over every stored column except the hash itself."""
    material = canonical_json({
        "idx": idx, "recorded_at": recorded_at, "operation": operation, "entity_kind": entity_kind,
        "entity_id": entity_id, "source_id": source_id, "target_id": target_id, "actor": actor,
        "payload": payload, "prev_hash": prev_hash,
    })
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _recompute(block: Block) -> str:
    fields = asdict(block)
    fields.pop("hash")
    return block_hash(**fields)


@dataclass(frozen=True)
class Anchor:
    """A block index and hash kept outside the database (printed, signed or stored elsewhere)."""
    idx: int
    hash: str


@dataclass
class Verification:
    ok: bool
    blocks_checked: int
    head: Anchor | None
    problems: list[dict[str, Any]] = field(default_factory=list)  # {"idx", "check", "detail"}

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "blocks_checked": self.blocks_checked,
                "head": asdict(self.head) if self.head else None, "problems": self.problems}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog:
    """Single-writer chain. Blocks are committed with commit() or when the context manager exits cleanly."""

    def __init__(self, path: Path | str, clock: Callable[[], datetime] = _utc_now) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        self._clock = clock
        row = self._conn.execute("SELECT idx, hash FROM blocks ORDER BY idx DESC LIMIT 1").fetchone()
        self._head = Anchor(*row) if row else None

    def __enter__(self) -> AuditLog:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.commit()
        else:
            self._conn.rollback()  # a failed build leaves no partial history
        self.close()

    def append(self, operation: str, entity_kind: str, entity_id: str, payload: dict[str, Any], actor: str,
               source_id: str | None = None, target_id: str | None = None) -> Block:
        if operation not in OPERATIONS:
            raise ValueError(f"unknown operation {operation!r}")
        idx = self._head.idx + 1 if self._head else 1
        prev = self._head.hash if self._head else GENESIS_HASH
        recorded_at = self._clock().astimezone(timezone.utc).isoformat(timespec="microseconds")
        text = canonical_json(payload)
        digest = block_hash(idx, recorded_at, operation, entity_kind, entity_id, source_id, target_id, actor, text, prev)
        block = Block(idx, recorded_at, operation, entity_kind, entity_id, source_id, target_id, actor, text, prev, digest)
        # The PRIMARY KEY on idx also stops a second writer from forking the chain at the same index.
        self._conn.execute(f"INSERT INTO blocks ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                           tuple(asdict(block).values()))
        self._head = Anchor(idx, digest)
        return block

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def head(self) -> Anchor | None:
        return self._head

    def blocks(self) -> Iterator[Block]:
        for row in self._conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM blocks ORDER BY idx"):
            yield Block(*row)

    def history(self, entity_id: str, include_edges: bool = False) -> list[Block]:
        """Blocks about one node or edge; for a node, optionally also blocks about edges that touch it."""
        where = "entity_id = ?" + (" OR source_id = ? OR target_id = ?" if include_edges else "")
        args = (entity_id,) * (3 if include_edges else 1)
        rows = self._conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM blocks WHERE {where} ORDER BY idx", args)
        return [Block(*row) for row in rows]

    def verify_chain(self, anchor: Anchor | None = None) -> Verification:
        return _verify(self.blocks(), anchor)


def verify_chain(path: Path | str, anchor: Anchor | None = None) -> Verification:
    """Verifies a stored chain without writing to it."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM blocks ORDER BY idx")
        return _verify((Block(*row) for row in rows), anchor)
    finally:
        conn.close()


def _verify(blocks: Iterator[Block], anchor: Anchor | None) -> Verification:
    problems: list[dict[str, Any]] = []
    expected_idx, prev_hash, count, last, anchored = 1, GENESIS_HASH, 0, None, None
    for block in blocks:
        count += 1
        if block.idx != expected_idx:
            problems.append({"idx": block.idx, "check": "sequence",
                             "detail": f"expected block {expected_idx}; blocks are missing or reordered"})
        if block.prev_hash != prev_hash:
            problems.append({"idx": block.idx, "check": "link",
                             "detail": "prev_hash does not match the previous block's stored hash"})
        if _recompute(block) != block.hash:
            problems.append({"idx": block.idx, "check": "hash",
                             "detail": "stored hash does not match the block's contents"})
        if anchor and block.idx == anchor.idx:
            anchored = block
        expected_idx, prev_hash, last = block.idx + 1, block.hash, block
    if anchor:
        if anchored is None:
            problems.append({"idx": anchor.idx, "check": "anchor", "detail": "the anchored block no longer exists"})
        elif anchored.hash != anchor.hash:
            problems.append({"idx": anchor.idx, "check": "anchor",
                             "detail": "the anchored block's hash differs from the hash saved outside the database"})
    head = Anchor(last.idx, last.hash) if last else None
    return Verification(ok=not problems, blocks_checked=count, head=head, problems=problems)

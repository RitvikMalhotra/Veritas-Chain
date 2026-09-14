"""Tamper demo: python -m veritas.audit.tamper_demo

Works on copies of the audit log, never the original. Each attack starts from a fresh copy.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from veritas.audit.chain import Anchor, block_hash, canonical_json, verify_chain

parser = argparse.ArgumentParser(description="Tamper with a copy of the audit log and show verify_chain catching it.")
parser.add_argument("--audit", type=Path, default=Path("output/phase5/audit.sqlite"))
parser.add_argument("--anchor", type=Path, default=Path("output/phase5/anchor.json"))
parser.add_argument("--out", type=Path, default=Path("output/phase5"))
args = parser.parse_args()

COLUMNS = ("idx", "recorded_at", "operation", "entity_kind", "entity_id", "source_id", "target_id", "actor", "payload",
           "prev_hash")
copy_path = args.out / "tamper_demo.sqlite"
anchor = Anchor(**json.loads(args.anchor.read_text(encoding="utf-8")))


def fresh_copy() -> sqlite3.Connection:
    shutil.copyfile(args.audit, copy_path)
    return sqlite3.connect(copy_path)


def drop_guards(conn: sqlite3.Connection) -> None:
    # Someone with the database file can simply remove the append-only triggers.
    conn.execute("DROP TRIGGER blocks_no_update")
    conn.execute("DROP TRIGGER blocks_no_delete")


def largest_transfer(conn: sqlite3.Connection) -> tuple[int, dict[str, Any]]:
    rows = conn.execute("SELECT idx, payload FROM blocks WHERE operation = 'edge_created'").fetchall()
    transfers = [(idx, json.loads(p)) for idx, p in rows if json.loads(p)["edge"]["type"] == "TRANSFERRED_MONEY_TO"]
    return max(transfers, key=lambda t: (float(t[1]["edge"]["amount_inr"] or 0), -t[0]))


def shrink_amount(conn: sqlite3.Connection) -> tuple[int, str, str]:
    idx, payload = largest_transfer(conn)
    before = payload["edge"]["amount_inr"]
    payload["edge"]["amount_inr"] = f"{float(before) / 100:.2f}"  # hide a large transfer by dropping two digits
    conn.execute("UPDATE blocks SET payload = ? WHERE idx = ?", (canonical_json(payload), idx))
    return idx, before, payload["edge"]["amount_inr"]


def rehash_from(conn: sqlite3.Connection, start: int, stop: int | None = None) -> int:
    """Recomputes hash (and the next block's prev_hash) from `start` onward, as an attacker covering tracks would."""
    prev = conn.execute("SELECT hash FROM blocks WHERE idx = ?", (start - 1,)).fetchone()
    prev_hash = prev[0] if prev else "0" * 64
    rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM blocks WHERE idx >= ? ORDER BY idx", (start,)).fetchall()
    updates = []
    for row in rows[: None if stop is None else stop - start + 1]:
        fields = dict(zip(COLUMNS, row))
        fields["prev_hash"] = prev_hash
        prev_hash = block_hash(**fields)
        updates.append((fields["prev_hash"], prev_hash, fields["idx"]))
    conn.executemany("UPDATE blocks SET prev_hash = ?, hash = ? WHERE idx = ?", updates)
    return len(updates)


scenarios: list[dict[str, Any]] = []


def record(attack: str, expected: str, ok_without: bool, ok_with: bool, problems: set[tuple[int, str]], **extra) -> None:
    """Runs both verifications on the copy and compares them with what the scenario expects, exactly."""
    without, with_anchor = verify_chain(copy_path), verify_chain(copy_path, anchor)
    found = {(p["idx"], p["check"]) for p in without.problems + with_anchor.problems}
    scenarios.append({
        "attack": attack, "expected": expected, **extra,
        "verify_without_anchor": {"ok": without.ok, "problems": without.problems},
        "verify_with_anchor": {"ok": with_anchor.ok, "problems": with_anchor.problems},
        "as_expected": without.ok == ok_without and with_anchor.ok == ok_with and found == problems,
    })


# 0. Untouched copy.
fresh_copy().close()
record("none (untouched copy)", "verifies with and without the anchor", True, True, set())

# 1. Ordinary SQL edit, triggers still in place.
conn = fresh_copy()
try:
    conn.execute("UPDATE blocks SET actor = 'someone else' WHERE idx = 1")
    refused = None
except sqlite3.DatabaseError as exc:
    refused = str(exc)
conn.close()
record("UPDATE a block through SQL", "refused by the append-only trigger; chain still verifies",
       True, True, set(), refused_with=refused)
scenarios[-1]["as_expected"] &= refused is not None

# 2. Triggers dropped, one payload changed.
conn = fresh_copy()
drop_guards(conn)
idx, before, after = shrink_amount(conn)
conn.commit()
conn.close()
record(f"drop triggers; change transfer amount in block {idx} from {before} to {after}",
       f"hash check fails at block {idx}", False, False, {(idx, "hash")})

# 3. Same, and the tampered block's own hash recomputed.
conn = fresh_copy()
drop_guards(conn)
idx, before, after = shrink_amount(conn)
rehash_from(conn, idx, stop=idx)
conn.commit()
conn.close()
record(f"same change, and recompute block {idx}'s hash", f"link check fails at block {idx + 1}",
       False, False, {(idx + 1, "link")})

# 4. Same, and every later hash recomputed: the internal checks cannot catch this.
conn = fresh_copy()
drop_guards(conn)
idx, before, after = shrink_amount(conn)
rewritten = rehash_from(conn, idx)
conn.commit()
conn.close()
record(f"same change, and recompute all {rewritten} hashes from block {idx} to the end",
       "passes without the anchor (known limitation); the anchor check fails", True, False, {(anchor.idx, "anchor")})

# 5. A block deleted from the middle.
conn = fresh_copy()
drop_guards(conn)
middle = anchor.idx // 2
conn.execute("DELETE FROM blocks WHERE idx = ?", (middle,))
conn.commit()
conn.close()
record(f"drop triggers; delete block {middle}", f"sequence and link checks fail at block {middle + 1}",
       False, False, {(middle + 1, "sequence"), (middle + 1, "link")})

# 6. The newest blocks deleted: a shorter chain is still internally consistent.
conn = fresh_copy()
drop_guards(conn)
conn.execute("DELETE FROM blocks WHERE idx > ?", (anchor.idx - 100,))
conn.commit()
conn.close()
record("drop triggers; delete the last 100 blocks",
       "passes without the anchor (known limitation); the anchor check fails", True, False, {(anchor.idx, "anchor")})

copy_path.unlink()
result_path = args.out / "tamper_demo.json"
result_path.write_text(json.dumps({"anchor_block": anchor.idx, "scenarios": scenarios}, indent=2) + "\n",
                       encoding="utf-8", newline="\n")

for s in scenarios:
    print(f"\n> {s['attack']}\n  expected: {s['expected']}")
    if "refused_with" in s:
        print(f"  SQL refused: {s['refused_with']}")
    for key in ("verify_without_anchor", "verify_with_anchor"):
        v = s[key]
        shown = "; ".join(f"block {p['idx']} {p['check']}" for p in v["problems"][:4]) or "no problems"
        print(f"  {key.replace('_', ' ')}: {'VERIFIED' if v['ok'] else 'TAMPERING DETECTED'} ({shown})")
    print(f"  as expected: {s['as_expected']}")
print(f"\n{sum(s['as_expected'] for s in scenarios)}/{len(scenarios)} scenarios behaved as expected ->", result_path)

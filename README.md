# Veritas-Chain: Criminal Network Analysis on Synthetic Data

A solo portfolio project based on problem statement SIH26189 ("AI-Powered Criminal Network
Analysis System", Ministry of Home Affairs). It builds a link-analysis graph from call records,
bank transactions and free-text incident reports. It then ranks key individuals, detects
clusters, flags anomalies and records every graph change in a tamper-evident hash chain.

> **All data is synthetic.** Every name, phone number, account, vehicle and report is generated.
> Nothing here is, or claims to be, real law-enforcement data.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Data schema + models | **Done, signed off** |
| 1 | Synthetic data generator + ground truth | Not started |
| 2 | Entity extraction (spaCy NER + regex) | Not started |
| 3 | Graph construction + exact-match entity resolution | Not started |
| 4 | Centrality, Louvain communities, rule-based anomalies | Not started |
| 5 | SHA-256 hash-chain audit log (SQLite) + tamper demo | Not started |
| 6 | FastAPI + Cytoscape.js frontend | Not started |

## Architecture (planned)

```
data/ (synthetic CSVs + report text)
   │
   ├── structured rows ─────────────────────────────┐
   └── report text → Phase 2 extraction → mentions ─┤
                                                    ▼
                          Phase 3: NetworkX MultiDiGraph  ──► Phase 5: hash-chain audit log (SQLite)
                                                    │
                          Phase 4: analytics (centrality, communities, anomaly rules)
                                                    │
                          Phase 6: FastAPI  ──►  Cytoscape.js UI
```

## Running

```bash
pip install -r requirements.txt
python -m pytest
```

## Layout

| Path | What |
|---|---|
| [`schema.md`](schema.md) | Node types, edge types, ID and confidence rules, entity-resolution limits |
| [`veritas/models.py`](veritas/models.py) | Pydantic models that enforce the schema |
| [`veritas/normalize.py`](veritas/normalize.py) | Canonical-key functions; these are the entity-resolution rules |
| [`veritas/config.py`](veritas/config.py) | Confidence defaults, which can be overridden with env vars |
| [`tests/`](tests/) | One test per schema rule |

## Design decisions

- **NetworkX instead of Neo4j.** At a few thousand nodes, an in-process graph means no database to run and algorithms can be called directly. Neo4j would be the production choice (see below).
- **Pydantic models with a closed type set.** Invalid endpoints, naive timestamps, unknown fields and out-of-range confidence all fail validation. They are not stored silently.
- **Phones and accounts are their own nodes.** A call record links numbers, not people. The link from a person to a phone or account is a separate edge with its own source (details in `schema.md` section 1).
- **IDs are derived from content.** Node ID = type + normalized key, so exact-match entity resolution is just ID equality. Edge ID = a hash of the edge's content, so loading the same record twice is harmless.
- **Confidence is an ordinal weight, not a probability.** The defaults are configurable placeholders. The NER defaults will be replaced with precision measured in Phase 2.
- **False splits are preferred over false merges.** A wrong merge invents links between strangers and distorts centrality.

## Known limitations

- **Entity resolution is exact match only.** Common names collide (false merge). Initials, transliterations and aliases do not merge (false split). Full list in `schema.md` section 7.
- **Only Indian mobile numbers and standard or BH-series plates are accepted.** Landlines and foreign numbers are rejected.
- **Three NLP confidence defaults are guesses pending validation:** `text_pattern` = 0.7, `text_cooccurrence` = 0.4 and `mention_spacy_ner` = 0.6. They will be measured once Phase 1 ground truth exists. The regex default (0.95) is accepted as-is.
- **Two edge types beyond the brief.** `USES_PHONE` and `HOLDS_ACCOUNT` were added so structured call and bank data can reach Person nodes (`schema.md` section 6).

## What would change in production

| This project | Production |
|---|---|
| NetworkX in memory | Neo4j (or another graph DB) with indexed lookups and a query language |
| Exact-match entity resolution | Probabilistic record linkage (for example Splink or Dedupe) with human review of merges |
| Fixed confidence per method | Confidence calibrated on labelled data, per source and per extractor |
| SHA-256 hash chain in SQLite | An append-only ledger with external anchoring (for example a permissioned blockchain or signed timestamps) |
| Rule-based anomaly detection | Rules plus statistical or ML models tuned against labelled cases |

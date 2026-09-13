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
| 1 | Synthetic data generator + ground truth | **Done, signed off** |
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
python -m veritas.synth --seed 42 --out data   # regenerate the synthetic dataset (deterministic)
python -m pytest                               # schema tests + generator self-checks
```

## Layout

| Path | What |
|---|---|
| [`schema.md`](schema.md) | Node types, edge types, ID and confidence rules, entity-resolution limits |
| [`veritas/models.py`](veritas/models.py) | Pydantic models that enforce the schema |
| [`veritas/normalize.py`](veritas/normalize.py) | Canonical-key functions; these are the entity-resolution rules |
| [`veritas/config.py`](veritas/config.py) | Confidence defaults, which can be overridden with env vars |
| [`veritas/synth/`](veritas/synth/) | Synthetic data generator: population, incident scenarios, calls and money, FIR text |
| [`data/`](data/) | Generated dataset (seed 42) and `ground_truth.json`. See [`data/README.md`](data/README.md). |
| [`tests/`](tests/) | Schema rule tests (`test_models.py`) and generator self-checks (`test_synth.py`) |

## Design decisions

- **NetworkX instead of Neo4j.** At a few thousand nodes, an in-process graph means no database to run and algorithms can be called directly. Neo4j would be the production choice (see below).
- **Pydantic models with a closed type set.** Invalid endpoints, naive timestamps, unknown fields and out-of-range confidence all fail validation. They are not stored silently.
- **Phones and accounts are their own nodes.** A call record links numbers, not people. The link from a person to a phone or account is a separate edge with its own source (details in `schema.md` section 1).
- **IDs are derived from content.** Node ID = type + normalized key, so exact-match entity resolution is just ID equality. Edge ID = a hash of the edge's content, so loading the same record twice is harmless.
- **Confidence is an ordinal weight, not a probability.** The defaults are configurable placeholders. The NER defaults will be replaced with precision measured in Phase 2.
- **False splits are preferred over false merges.** A wrong merge invents links between strangers and distorts centrality.

### Phase 1: synthetic data

- **Deterministic by seed.** Each part of the generator (world, scenarios, calls, transactions, reports) uses its own string-seeded random stream. Changing FIR wording therefore doesn't change the call data, and a test checks that output is byte-identical across processes and hash seeds.
- **The ground truth is checked, not asserted.** `tests/test_synth.py` verifies the claims `ground_truth.json` makes against the generated files. It checks bridges (removing one disconnects its clusters), the planted cycle (time-ordered, amounts shrinking), the decoy (no time-respecting order), spikes (at least 2.5× baseline), the single name collision, exact mention spans, and schema conformance of every row. Deliberately breaking the generator (removing the spike multiplier, adding a direct link between clusters A and B) makes the relevant tests fail.
- **Leaders are insulated (approved design choice).** Members call lieutenants, and lieutenants call the leader, so the busiest phones are often not the leaders'. This is the realistic case and means degree centrality alone is not expected to find leaders. Measured ranks are stored in `ground_truth.json` under `signal_visibility`, and no per-metric outcome is promised in advance.
- **Structured records and report text back each other up.** When a report says a fraud caller used a number, that call exists in the CDR, and fraud victims' payments exist in the bank data. Reports only describe cash as person-to-person transfers, following the schema rule that structured data never has Person→Person edges.
- **Decoys and a planted collision.** A 3-cycle among friends has dates that run backwards around the loop, so a cycle rule has to check time order, not just topology. Two unrelated "Rahul Sharma"s test the known false-merge weakness.
- **Faker is used for names only.** Faker's `en_IN` `phone_number()` produces invalid Indian mobile numbers (for example `5868344978`), so the generator creates numbers itself and validates them against the Phase 0 rules.

## Known limitations

- **Entity resolution is exact match only.** Common names collide (false merge). Initials, transliterations and aliases do not merge (false split). Full list in `schema.md` section 7.
- **Only Indian mobile numbers and standard or BH-series plates are accepted.** Landlines and foreign numbers are rejected.
- **Three NLP confidence defaults are guesses pending validation:** `text_pattern` = 0.7, `text_cooccurrence` = 0.4 and `mention_spacy_ner` = 0.6. They will be measured once Phase 1 ground truth exists. The regex default (0.95) is accepted as-is.
- **Two edge types beyond the brief.** `USES_PHONE` and `HOLDS_ACCOUNT` were added so structured call and bank data can reach Person nodes (`schema.md` section 6).
- **The synthetic data is cleaner than reality.** FIRs are built from 15 templates, so their phrasing is repetitive. Every entity in a report is spelled exactly as in the registries: no typos, aliases or transliteration variants. Phase 2 accuracy on this data is therefore an upper bound, not an estimate for real reports.
- **Faker's `en_IN` name pool includes Western first names** (for example "Liam", "Henry"). These may make spaCy's person recognition easier than it would be on real Indian names.
- **Spikes are planted as a rate multiplier (5×), so how strong they come out is random.** Small groups can come out weak. In a 20-seed sweep, one spike in seed 9 reached only 2.35×. Measured strength is recorded per event.
- **The generator is robust across seeds but not perfectly.** In a sweep of 20 seeds, all generate successfully and 19 pass every data check. The one failure is the weak spike above. CI tests run seeds 42 and 7.
- **Header details are simplified.** FIR numbers are sequential per city, not per police station, and the acts and sections are illustrative.

## What would change in production

| This project | Production |
|---|---|
| NetworkX in memory | Neo4j (or another graph DB) with indexed lookups and a query language |
| Exact-match entity resolution | Probabilistic record linkage (for example Splink or Dedupe) with human review of merges |
| Fixed confidence per method | Confidence calibrated on labelled data, per source and per extractor |
| SHA-256 hash chain in SQLite | An append-only ledger with external anchoring (for example a permissioned blockchain or signed timestamps) |
| Rule-based anomaly detection | Rules plus statistical or ML models tuned against labelled cases |

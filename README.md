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
| 2 | Entity extraction (spaCy NER + regex) | **Done, signed off** |
| 3 | Relation extraction + graph construction + exact-match entity resolution | **Done, signed off** |
| 4 | Centrality, Louvain communities, rule-based anomalies | **Done, signed off as-is (1 expectation not met, 2 met weakly)** |
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
python -m veritas.extract --evaluate           # extract entities from FIRs, score against ground truth
python -m veritas.extract.relation_eval        # score relation rules (gold entities, end to end, challenge set)
python -m veritas.graph --evaluate             # build the graph (GraphML), entity-resolution report, graph evaluation
python -m veritas.analytics --evaluate         # centrality, communities, anomaly rules, validation vs ground truth
python -m pytest                               # all tests
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
| [`veritas/extract/`](veritas/extract/) | FIR parsing, regex extractors, spaCy NER, relation rules (`relations.py`), evaluation |
| [`veritas/graph/`](veritas/graph/) | Graph builder (single validated write path), CSV and text loaders, GraphML I/O, reports |
| [`output/phase2/`](output/phase2/) | Extracted entities and evaluation reports for both spaCy models |
| [`veritas/analytics/`](veritas/analytics/) | Actor-graph projection, centrality, Louvain, spike and money-cycle rules, validation with fixed expectations |
| [`output/phase3/`](output/phase3/) | Build report, relation and graph evaluations, evidence sentence for every text edge. `graph.graphml` is rebuilt, not committed. |
| [`output/phase4/`](output/phase4/) | Rankings, communities, anomalies (`analytics.json`) and validation (`evaluation.json`) |
| [`tests/`](tests/) | Tests for the schema, generator, extraction, relations, graph and analytics. `tests/fixtures/relation_challenge.json` is the hand-written relation probe. |

## Design decisions

- **NetworkX instead of Neo4j.** At a few thousand nodes, an in-process graph means no database to run and algorithms can be called directly. Neo4j would be the production choice (see below).
- **Pydantic models with a closed type set.** Invalid endpoints, naive timestamps, unknown fields and out-of-range confidence all fail validation. They are not stored silently.
- **Phones and accounts are their own nodes.** A call record links numbers, not people. The link from a person to a phone or account is a separate edge with its own source (details in `schema.md` section 1).
- **IDs are derived from content.** Node ID = type + normalized key, so exact-match entity resolution is just ID equality. Edge ID = a hash of the edge's content, so loading the same record twice is harmless.
- **Confidence is an ordinal weight, not a probability.** NER confidence is set per label from measured precision (Phase 2). The relation defaults were measured in Phase 3 and deliberately kept conservative.
- **False splits are preferred over false merges.** A wrong merge invents links between strangers and distorts centrality.

### Phase 1: synthetic data

- **Deterministic by seed.** Each part of the generator (world, scenarios, calls, transactions, reports) uses its own string-seeded random stream. Changing FIR wording therefore doesn't change the call data, and a test checks that output is byte-identical across processes and hash seeds.
- **The ground truth is checked, not asserted.** `tests/test_synth.py` verifies the claims `ground_truth.json` makes against the generated files. It checks bridges (removing one disconnects its clusters), the planted cycle (time-ordered, amounts shrinking), the decoy (no time-respecting order), spikes (at least 2.5× baseline), the single name collision, exact mention spans, and schema conformance of every row. Deliberately breaking the generator (removing the spike multiplier, adding a direct link between clusters A and B) makes the relevant tests fail.
- **Leaders are insulated (approved design choice).** Members call lieutenants, and lieutenants call the leader, so the busiest phones are often not the leaders'. This is the realistic case and means degree centrality alone is not expected to find leaders. Measured ranks are stored in `ground_truth.json` under `signal_visibility`, and no per-metric outcome is promised in advance.
- **Structured records and report text back each other up.** When a report says a fraud caller used a number, that call exists in the CDR, and fraud victims' payments exist in the bank data. Reports only describe cash as person-to-person transfers, following the schema rule that structured data never has Person→Person edges.
- **Decoys and a planted collision.** A 3-cycle among friends has dates that run backwards around the loop and amounts that differ widely, so a cycle rule can't rely on topology alone. (Phase 4 found that because it breaks two rules at once, it doesn't show the time check specifically is needed.) Two unrelated "Rahul Sharma"s test the known false-merge weakness.
- **Faker is used for names only.** Faker's `en_IN` `phone_number()` produces invalid Indian mobile numbers (for example `5868344978`), so the generator creates numbers itself and validates them against the Phase 0 rules.
- **Report employment claims are backed by bank data.** Background people have employers. Reports say "who works at X", and salary transfers in `transactions.csv` come from that same company. This was added at the start of Phase 2 to raise Organization mentions from 4 to 17, so ORG accuracy can actually be measured.

### Phase 2: entity extraction

- **Regex for phones and plates, not NER.** Both follow fixed national formats, so a pattern plus the Phase 0 validity check is near-deterministic and explainable. Generic NER labels them inconsistently (CARDINAL, ORG, or nothing). Where a spaCy span overlaps a regex match, the regex match wins.
- **spaCy for Person, Location and Organization.** Labels are mapped `PERSON→Person`, `ORG→Organization`, `GPE/LOC/FAC→Location`. Every other label is dropped.
- **Only the narrative is extracted.** Header fields such as the investigating officer are metadata, not network entities.
- **Confidence is fixed per method and label** (from `config.py`), because spaCy's NER gives no per-entity probability. Values are measured precision (approved). The output file says the values are not model probabilities.
- **`en_core_web_md` is the default, chosen by measurement (approved).** On both seeds, md and sm have the same overall F1 (about 76–77). md is 5–10 F1 points better on Person, the node type centrality runs on, and 10–14 points worse on Organization precision.
- **No cleanup rules were tuned on the evaluation data.** Every candidate rule (place-word lists, honorific filters) would be derived from the generator's own templates, so scoring it on this data would be circular.

Results (lenient match = overlapping span, same type; strict = exact span):

| Type | gold (per seed) | md seed 42: P / R / F1 | md seed 7: P / R / F1 | sm seed 42: P / R / F1 |
|---|---|---|---|---|
| Person | 79 | 92.1 / 88.6 / 90.3 | 91.6 / 96.2 / 93.8 | 85.9 / 84.8 / 85.4 |
| Location | 53 | 100 / 62.3 / 76.7 | 94.1 / 60.4 / 73.6 | 100 / 58.5 / 73.8 |
| Organization | 17 | 30.4 / 100 / 46.6 | 28.3 / 100 / 44.2 | 39.0 / 94.1 / 55.2 |
| Phone (regex) | 32 | 100 / 100 / 100 | 100 / 100 / 100 | same |
| Vehicle (regex) | 10 | 100 / 100 / 100 | 100 / 100 / 100 | same |

### Phase 3: relation extraction and graph construction

- **Relations come from explainable patterns, not a model.** Each sentence has its entities replaced by typed tokens (`⟦P3⟧ … who uses mobile number ⟦T4⟧`), and a small set of regexes reads the relation from the words between them. Every text edge has its rule name and evidence sentence recorded in `text_edge_evidence.json`.
- **Cue words are limited to FIR phrasing.** They come from the report templates plus inflections of the same verbs. Nothing was added for the challenge set.
- **Evaluation protocol.** The 22-sentence challenge set was written before the rules and scored once; rules were not changed to fix its misses. Two fixes were made after the first run on the synthetic reports, both because the code did not match the stated design:
  1. The business-as-place rule treated the city as optional, which turned "who works at X" into a place.
  2. "around" is used in the FIR templates but was missing from the place-preposition list.
- **FIR conventions are resolved.** "the complainant" refers to the person introduced as complainant; "the vehicle" refers to the last vehicle mentioned.
- **Businesses used as places (decision 2).** A business in a place phrase ("met … at X", "near X, City") becomes a Location, and "X, City" stores the city on the place node rather than creating a separate city node.
- **Decision 3 is enforced in text too.** A Person→Person `CALLED` edge is only emitted when the sentence gives no number. A Person→Person cash transfer is only emitted when no bank channel (UPI, account, NEFT…) is named.
- **Junk nodes are left in the graph (approved).** No filter was fitted to this data. Phase 4 reports centrality with and without same-sentence edges so their effect is visible instead of hidden.
- **Text edge confidence** = min(method default, confidence of each entity). A membership in an NER-tagged organisation is therefore capped at 0.29. Event-like edges are stamped with the incident time, and state-like edges with the report time.
- **Same-sentence edges (`ASSOCIATED_WITH`, 0.4)** only link people who have no pattern relation between them in that report.
- **One write path.** Every node and edge goes through `GraphBuilder`: Pydantic validation, exact-match merge (first-seen fields, combined provenance), a check that both endpoints exist, and duplicate-edge skipping. Phase 5's audit chain will hook in there.

Relation results, micro-averaged over 7 relation types (103 annotated relations per seed):

| | seed 42: P / R / F1 | seed 7: P / R / F1 |
|---|---|---|
| Gold entities → rules | 100 / 82.5 / 90.4 | 100 / 82.5 / 90.4 |
| spaCy md entities → rules (end to end) | 98.5 / 63.1 / 76.9 | 100 / 75.7 / 86.2 |
| Challenge set (different phrasing, gold entities) | 75.0 / 12.5 / 21.4 | (same set) |

Same-sentence edges that join people with a real tie (defined before scoring): 94.9% / 92.3% with gold entities, 74.4% / 69.4% end to end.

Graph at seed 42: 530 nodes and 8,117 edges (8,012 structured, 105 from text).

| Check | Result |
|---|---|
| True people present | 135/135 IDs (136 people; the planted pair shares one) |
| Planted collision | merged into `Person:rahul_sharma` with both phones, as predicted |
| Report mentions linked to the right node | Person 71/79, Location 50/53 (22 of them as a place's city), Organization, Phone and Vehicle all linked |
| Junk nodes from NER errors | 10 Organization, 5 Person; 10 isolated, 2 with one edge, 3 with 2–4 weak same-sentence edges |

### Phase 4: analytics (validation protocol, written before the first run)

- **Actor graph.** Centrality and communities run on people and companies, not the raw graph, which would rank busy phones and accounts. Two actors are linked when their phones called each other, their accounts transacted, a report relates them, or they were present at the same incident or meeting. Each underlying record adds its confidence to the link weight.
- **Three variants of every analysis:** all evidence, without same-sentence edges, and structured data only (approved sensitivity check).
- **Metrics.** Degree (distinct contacts), betweenness (distance = 1/weight), PageRank (directed and weighted) and Louvain communities (seeded, plus a 10-seed stability check).
- **Call spikes.** For each incident, the rule counts calls on the phones of everyone named in its report inside a 72h-before to 24h-after window, and compares that with the same phones' normal rate. It flags when there are at least 5 calls, at least 2× the expected number, and a Poisson tail probability ≤ 0.001. The generator planted spikes 48h before to 12h after, and the detector **deliberately does not reuse that window**.
- **Circular money flow.** A loop of 3–6 accounts is flagged only if one pass through it is time-ordered, with each hop within 7 days and keeping at least 85% of the previous amount. These thresholds are looser than the planted pattern (≤ 2 days, 2–4% cut). Loops found by topology alone are reported for comparison.
- **Expectations, fixed before running** (reported as met or not met, never edited to fit):
  1. Both bridges rank in the top 10% of people by betweenness (structured only).
  2. For each planted cluster, one community holds ≥ 80% of its members (structured only; the merged Rahul Sharma node is excluded).
  3. Every incident with a planted spike is flagged.
  4. No incident without a planted spike is flagged.
  5. Both laundering rounds are flagged with exactly their transactions.
  6. The decoy loop is not flagged, even though topology finds it.
- **Not expected:** leaders are insulated by design, so no metric is expected to rank them first. Their ranks are reported but not judged.

**Results (seed 42, replicated on seed 7):**

| # | Expectation | Result | Detail |
|---|---|---|---|
| 1 | Bridges in top 10% by betweenness | **Met** | ranks 3 and 6 of 140 (seed 7: 3 and 6) |
| 2 | Each cluster ≥ 80% in one community | **Met, but hollow** | recall 100% for all 4, but communities are city-sized (30–34 actors) with **purity 19–33%** (seed 7: 23–33%). Louvain recovered geography, not the criminal groups. The expectation was badly specified because it had no purity requirement; it has not been rewritten. |
| 3 | All planted spikes flagged | **Not met** | 4 of 6 (seed 42 missed A1 and D2; seed 7 missed A2 and D2). The misses were significant (p ≈ 1e-4) but came out at 1.88–1.99× against the 2× rule, because a 96h window and all calls on the named phones dilute a 60h spike. |
| 4 | No false spike alarms | **Met** | 0 of 18 (both seeds) |
| 5 | Both laundering rounds flagged exactly | **Met** | both rounds, with exactly their 4 transactions each |
| 6 | Decoy loop not flagged | **Met, but weaker than it looks** | The decoy has reversed dates *and* amounts that differ by more than 5×, so the amount check alone rejects it. It does not show the time check is needed. The time check does matter on the real data: without it, 3 extra loops stitched from both rounds out of time order are flagged. |

**Key individuals (4 leaders, 6 lieutenants, 2 bridges) in each metric's top 12:**

| | Degree | Betweenness | PageRank |
|---|---|---|---|
| Structured only | 0 | 6 | 8 |
| All evidence | 0 | 7 | 8 |

- **Degree finds nobody.** Its top 10 are all background people, such as merchants who receive payments from most residents of a city.
- **Betweenness finds brokers.** It puts the bridges, cluster A's lieutenant and cluster B's leader near the top.
- **PageRank finds lieutenants.** Five of its top six people are lieutenants or leaders.
- **Insulated leaders stay hidden, as designed.** Cluster A's leader ranks 22nd on betweenness and 41st on PageRank; cluster D's leader ranks 51st and 23rd.
- **The planted false merge shows up exactly as predicted.** `Person:rahul_sharma` ranks **5th on betweenness** on both seeds: merging two strangers created a fake broker between cluster A and Delhi.
- **Text evidence has little effect.** It moves key individuals by at most 3 places on betweenness and 9 on PageRank, and no junk node from NER errors appears in any top 20.

## Known limitations

- **Entity resolution is exact match only.** Common names collide (false merge). Initials, transliterations and aliases do not merge (false split). Full list in `schema.md` section 7.
- **Only Indian mobile numbers and standard or BH-series plates are accepted.** Landlines and foreign numbers are rejected.
- **NER confidence is measured, but on easy text.** The per-label values (Person 0.92, Location 0.97, Organization 0.29) are `en_core_web_md` precision on clean, templated synthetic reports, so they are upper bounds. They replaced a single unvalidated 0.6 after Phase 2. The regex default (0.95) is accepted as-is.
- **Relation confidence defaults are conservative on purpose:** `text_pattern` = 0.7 and `text_cooccurrence` = 0.4. Phase 3 measured them (see below) and kept them (approved), because template text can't justify higher trust.
- **Relation rules are brittle outside the template phrasing.** They recall 12.5% on the hand-written challenge set. They miss passive and reversed forms ("received … from"), other verbs ("arrested", "belongs to", "partner in"), and nominal phrases ("the meeting between"). They are also fooled by negation: "Neither X nor Y was present" produced a false presence edge. On the synthetic reports, 100% precision only shows the rules fit the template language.
- **Pooled relation precision (seeds 42 and 7).** Pattern relations: 170/170 with gold entities, 143/144 end to end. Same-sentence edges: 73/78 with gold entities, 63/88 end to end.
- **NER errors leak into the graph.** spaCy tagged cluster A's leader as ORG, which created a false `MEMBER_OF` edge to an organisation called "Daksh Bakshi". Junk Person nodes such as `Person:kyc` and `Person:royal_enfield_classic_350` picked up weak same-sentence edges to cluster members (up to 4 edges, confidence ≤ 0.4). These could slightly affect centrality in Phase 4.
- **Entity resolution cannot separate "one person with two SIMs" from "two people sharing a name".** The build report lists both cases (cluster A's leader and the planted Rahul Sharma pair) under the same diagnostic.
- **Community detection finds cities, not gangs.** Almost all calls and payments stay within one city, so Louvain at its default resolution groups each cluster with its city's ordinary residents (purity 19–33%). A resolution sweep (exploratory, not adopted) raises purity only by splitting clusters. No setting recovers all four clusters well, and modularity, the label-free way to choose a setting, prefers the city-level split.
- **The spike rule misses a third of planted spikes.** Its window and "all calls on the named phones" dilute the signal. The Poisson test alone does not fix this: on seed 7, a planted spike (p = 0.006) and a non-planted incident (p = 0.007) overlap. Phase 4 thresholds are unvalidated analyst choices.
- **The Phase 1 decoy loop fails two rules at once** (reversed dates and very different amounts), so it can't show that the time-order check is necessary. The unit tests now isolate each rule separately.
- **Some text context is approximated.** "met … two days before" is stamped with the incident time, and FIR references like "the complainant" are resolved by convention, not general coreference.
- **Businesses used as meeting places are the largest NER error.** The schema labels "Sharma Tea Stall" or "Balan Warehouse" as Location, while spaCy (trained on OntoNotes) calls businesses ORG. This drives Location recall down to about 60% and Organization precision down to about 30%. It is a disagreement over label definitions, not missed text, and the ground truth has not been relabelled to hide it.
- **spaCy sometimes tags people as ORG, including key people.** In the md run, cluster A's leader was tagged ORG in all 3 mentions. Vehicle models ("Maruti Suzuki Swift"), acronyms (KYC, CCTV, IMEI, UPI) and a bare "Smt" also come through as false Organization entities.
- **Regex scores of 100% only show consistency.** The regexes and the generator's surface formats were written together. A bare `91` prefix (`919876543210`) is deliberately not matched in text, because it can't be told apart from a 12-digit account number.
- **Seed 7 is not a real held-out set.** It has new names, numbers and places but the same 15 templates, so it tests stability, not generalisation. Mention counts per type are identical across seeds for that reason.
- **Two edge types beyond the brief.** `USES_PHONE` and `HOLDS_ACCOUNT` were added so structured call and bank data can reach Person nodes (`schema.md` section 6).
- **The synthetic data is cleaner than reality.** FIRs are built from 15 templates, so their phrasing is repetitive. Every entity in a report is spelled exactly as in the registries: no typos, aliases or transliteration variants. Phase 2 accuracy on this data is therefore an upper bound, not an estimate for real reports.
- **Faker's `en_IN` name pool includes Western first names** (for example "Liam", "Henry"). These may make spaCy's person recognition easier than it would be on real Indian names.
- **Spikes are planted as a rate multiplier (5×), so how strong they come out is random.** Small groups can come out weak. In a 20-seed sweep, one spike in seed 9 reached only 2.35×. Measured strength is recorded per event.
- **The generator is robust across seeds but not perfectly.** In a sweep of 20 seeds, all generate successfully and 19 pass every data check. The one failure is the weak spike above. CI tests run seeds 42 and 7.
- **Header details are simplified.** FIR numbers are sequential per city, not per police station, and the acts and sections are illustrative.

## Future work (not implemented)

- **Correcting NER types with the registries.** If a report span tagged ORG or LOC normalizes to the exact key of a Person in the subscriber, KYC or vehicle registry, it could be relabelled as that Person. This would have recovered the cluster A leader, whose ORG tag cost his phone link and three meeting edges in one report.
  - **Circularity caveat:** in this synthetic dataset, every person named in a report also exists in a registry, so this correction would score close to perfectly by construction. Any accuracy measured here would be circular. It could only be evaluated honestly on reports that name people who are absent from the registries.
  - **Risk:** it turns the name-collision weakness into a typing error. A company named after a person ("Sharma Traders" vs. a registered "Sharma") is safe only because keys must match exactly.
- **Relation extraction that generalises** beyond template phrasing, for example dependency-parse rules or a trained relation classifier, with negation handling. The challenge set shows current recall of 12.5% on new phrasing.

## What would change in production

| This project | Production |
|---|---|
| NetworkX in memory | Neo4j (or another graph DB) with indexed lookups and a query language |
| Exact-match entity resolution | Probabilistic record linkage (for example Splink or Dedupe) with human review of merges |
| Fixed confidence per method | Confidence calibrated on labelled data, per source and per extractor |
| SHA-256 hash chain in SQLite | An append-only ledger with external anchoring (for example a permissioned blockchain or signed timestamps) |
| Rule-based anomaly detection | Rules plus statistical or ML models tuned against labelled cases |

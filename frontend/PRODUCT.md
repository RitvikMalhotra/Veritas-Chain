# Product

<!-- impeccable:product-schema 1 -->

Inferred from the user's Phase 6 frontend brief and the repo docs (README, docs/methodology.md). The audience and the five mockup decisions were confirmed by the user at the mockup review.

## Platform

web

## Users

- **Primary:** people evaluating a solo portfolio project: engineers, hiring managers, reviewers with a security or law-enforcement-tech background. On a laptop, usually for a few minutes, after reading the README. Their job: understand what the system does and see proof that it works.
- **Role frame:** the interface speaks in the working register of an analyst doing link analysis on a case graph, because that is the problem statement (SIH26189, criminal network analysis).

## Product Purpose

A read-only explorer over a link-analysis graph built from synthetic call records, bank transactions and free-text incident reports (FIRs). It shows who brokers between clusters, where every node and edge came from, and whether the audit hash chain still verifies against the graph being served.

Success: within a minute a first-time visitor knows the data is synthetic and what the graph represents, has jumped to a top-ranked broker, has read an edge's provenance, and has run Verify and seen an unmistakable verified or tampered result.

## Positioning

Every node and edge traces to a source record and to a SHA-256 hash-chain block, and tampering is demonstrable: Verify re-checks 24,338 blocks against an external anchor and replays the log against the served graph. The project is also candid about its limits (a low rank is not innocence; exact-match entity resolution creates false merges).

## Operating Context

- Started locally with `npm run dev` (FastAPI on 127.0.0.1:8000, Vite on 127.0.0.1:5173).
- Viewed on laptop and desktop screens; screenshots of it appear in the README and docs.
- The tampered state only appears when the API is started against a tampered copy of the audit log.

## Capabilities and Constraints

- Seven existing read-only endpoints: meta, full graph, node detail, node subgraph (depth 1–3), centrality rankings (3 metrics × 3 evidence variants), audit history (paged), audit verify. No new endpoints, no writes, no new analytics.
- Graph (seed 42): 529 nodes of 7 types (Person 140, Phone 152, BankAccount 119, Vehicle 44, Location 28, Event 24, Organization 22) and 8,120 edge records of 9 types, drawn as 1,633 merged edges. Positions are computed by the server (seeded spring layout); the layout algorithm and edge merging must not change.
- Extraction methods: `structured`, `text_pattern`, `text_cooccurrence`. Confidence is an ordinal weight, not a probability.
- Not available from the API: evidence sentences for text edges, communities, anomaly flags, ground truth. The UI must not imply them.
- Verify takes about 1.6–1.8 s. The API takes about 5 s to start.
- Laptop-first; mobile is not a target. No HTML injection from data (`dangerouslySetInnerHTML`, `innerHTML` are banned by a test).

## Brand Commitments

- Name: Veritas-Chain.
- The synthetic-data notice is always visible.
- User-pinned: the UI must match a cybersecurity and investigative theme.
- Cytoscape.js stays the graph renderer.

## Evidence on Hand

All real pipeline output on synthetic data (seed 42): the graph, rankings, and audit log served by the API; a tampered-copy demo reproducible from `tests/test_api.py` (block 23103, a ₹505,000 transfer altered). No real people, cases, testimonials or deployments exist, and none may be implied.

## Product Principles

1. **Provenance over assertion.** Show where a fact came from before what it means.
2. **Verification is the headline.** The chain check is the most differentiating thing the project does.
3. **Honest uncertainty.** Confidence, extraction method and known limits are shown, never smoothed away.
4. **Synthetic, always labelled.**
5. **Read-only by design.** Nothing in the UI suggests editing evidence.

## Accessibility & Inclusion

*(inferred)* WCAG AA text contrast, every control keyboard-reachable with a visible focus ring, and reduced motion respected.

# Veritas-Chain: project summary

I built this project with Claude Code, under my direction, in seven phases (0–6) with a sign-off gate at each one. Claude Code wrote the code, tests and documentation. At every gate it reported results and open questions, and I approved, changed or rejected them before anything was committed. The ground rules were mine from the start:
- use synthetic data only;
- make every claim defensible in a technical interview;
- use ground truth for evaluation only;
- make one commit per phase, stating what was built and what was checked.

> **All data is synthetic.** Every person, phone number, account and report was generated. Nothing here is, or claims to be, real law-enforcement data.

Veritas-Chain is a link-analysis pipeline for investigating criminal networks, based on problem statement SIH26189. It works in four stages:
1. It turns call records, bank transactions and free-text incident reports into one graph.
2. It ranks key people, detects communities and flags suspicious patterns.
3. It records every graph change in a SHA-256 hash chain.
4. A small web page lets you explore the graph and check that chain.

It is built with Python, spaCy, NetworkX, SQLite and FastAPI, with a React + Vite explorer using Cytoscape.js, and has 211 Python tests and 10 frontend tests.

On clean, templated synthetic data, the accuracy numbers are best-case figures. The better evidence is how each claim was checked, so this summary starts with what went wrong.

## Mistakes caught, and what caught them

Each item says who or what caught it:
- **me**, at a sign-off gate or in review;
- **Claude Code**, usually in its own work before I saw it;
- **an automated check**.

Most items are recorded in the [README](../README.md) or the commit messages. Five are marked because they appear only in a phase report or were fixed before reaching me.

### Wrong claims in the documentation

1. **A results table stated one seed's numbers as true for both.** The Phase 4 table said the missed call spikes were "significant (p ≈ 1e-4) at 1.88–1.99×" on seeds 42 and 7. That is true only for seed 42. On seed 7, one miss came out at 1.56× with p = 0.006, and the limitations section quoted that, contradicting the table. The Phase 4 commit message had the right range; the README table did not. The error survived three phases.
   *What caught it:* before publishing, I asked Claude Code to read the whole README end to end rather than phase by phase, because individual mistakes had turned up at nearly every phase. It found this by re-checking every number against the output files.
   *What changed:* the table now gives the figures for each seed.
2. **Wrong node count.** The Phase 3 README and commit message said the graph had 530 nodes, a count left over from an earlier build. The committed build report says 529.
   *What caught it:* Claude Code noticed the mismatch with the build report during Phase 5.
   *What changed:* the README was corrected. The Phase 3 commit message can't be changed and still says 530.
3. **A README edit deleted the "Known limitations" heading,** so every limitation read as a Phase 5 note.
   *What caught it:* Claude Code made the edit in Phase 5, then noticed and reported it in Phase 6.
   *What changed:* restored.
4. **Two overstatements in a draft write-up** (fixed before it reached me, so not in the history):
   - "1 call on seed 42" was really 16 calls in 90 days, 1 of them inside the spike window.
   - "All eight clusters split cleanly between crews" was really 5 of 8.

   *What caught it:* Claude Code, re-reading its own draft before reporting.
   *What changed:* it corrected both from the raw call records and community memberships.
5. **Smaller errors**:
   - PageRank's top six were described as "five of six" key people; on structured data it is six of six.
   - A precision gap was given as "10–14 points"; it is 9–14.
   - Two Phase 6 figures (page size and verification time) were measured before later changes.
   - The README mentioned "CI tests"; there is no CI.

   *What caught it:* Claude Code, in the end-to-end README read I asked for.
   *What changed:* corrected, and listed in the README.
6. **The ground truth predicted results nobody had checked** (in the Phase 1 report, not the repo). Claude Code wrote a note into `ground_truth.json` saying the planted leaders would rank near the top on degree and PageRank.
   *What caught it:* Claude Code, before reporting Phase 1. It ranked everyone by call volume and distinct contacts, to check that the planted signal wasn't too obvious, and the leaders of clusters A and D were nowhere near the top. Its first replacement note, "the busiest caller in each cluster is a lieutenant", was then caught by the test it wrote for that note: on seed 42, cluster B's leader made more calls than both lieutenants.
   *What changed:* the notes now state only what holds by construction, each checked by a test. Measured call-volume ranks are recorded separately, and no Phase 4 result is predicted. Claude Code put the design choice (leaders who stay out of the busiest call paths) to me as a decision, and I approved it.

### Bugs

7. **A relation rule made a business's city optional.** As a result, "who works at X" was read as a place, and 8 membership edges were lost.
   *What caught it:* Claude Code, in the errors from the first scoring run. It reported the fix to me as a mismatch between the code and the stated design, not as tuning to the evaluation data.
   *What changed:* the rule was fixed. Claude Code then put the bug back on purpose to confirm a test fails (a mutation check).
8. **"around" was missing from the list of place words,** although the report templates use it.
   *What caught it:* Claude Code, in the same first run. The list broke its own stated rule.
   *What changed:* added.
9. **Nested community detection gave different answers from run to run.** `graph.subgraph(set)` iterates in hash order.
   *What caught it:* Claude Code noticed that two runs on the same graph disagreed.
   *What changed:* fixed, with a regression test that runs it under 3 hash seeds; the old code gives 3 different answers. The revision still failed under all 6 hash seeds tried, so its verdict didn't depend on the bug.
10. **A committed results file started each money loop at a different account depending on hash order.**
    *What caught it:* after fixing item 9, Claude Code compared the analytics output files across two hash seeds.
    *What changed:* each loop now starts at its smallest account ID.
11. **An evaluation file listed its items in a different order on every run.** When Claude Code first saw the reordering, it assumed the regenerated data caused it, and its Phase 4 follow-up report gave no cause. The real cause was a scorer iterating over a set.
    *What caught it:* Claude Code's determinism check in Phase 5, which rebuilt everything under two hash seeds and compared the outputs. Its Phase 5 report told me the first assumption had been wrong.
    *What changed:* the output is sorted, with a regression test. Every committed output is now byte-identical across hash seeds.
12. **Verifying the audit log could quietly repair a tampered copy.** Verification opened the log through the writer, which re-runs its setup script. On a copy whose protective triggers had been dropped, that would recreate them.
    *What caught it:* Claude Code, while designing the verification endpoint.
    *What changed:* verification uses a read-only connection, and a test checks that a dropped trigger stays dropped.
13. **Faker's Indian phone generator produces invalid mobile numbers** (for example `5868344978`).
    *What caught it:* Claude Code sampled Faker's output before relying on it.
    *What changed:* the generator creates its own numbers and validates them.
14. **Choosing a merchant as a fraud victim created 3 unplanted money loops in the generated data** (in the Phase 1 report, not the repo).
    *What caught it:* an existing test, the generator check that no loops exist except the planted ones.
    *What changed:* fixed before Phase 1 was committed.
15. **Switching to per-label NER confidence made an invalid mention crash** instead of being rejected (in the Phase 3 report, not the repo).
    *What caught it:* an existing test.
    *What changed:* invalid combinations are rejected before the confidence is looked up.
16. **The generator crashed on seeds other than the two the tests use** (in the Phase 1 report, not the repo). With every test passing on seeds 42 and 7, Claude Code ran five more seeds, and four of them crashed: a city had no merchant left to receive a payment, or no unassigned person left for a role. The Phase 1 report summarised this as "4 of 20 seeds"; it was 4 of the 5 extra seeds tried.
    *What caught it:* Claude Code's spot check on extra seeds, run after all the tests passed.
    *What changed:* Claude Code fixed the causes rather than avoiding those seeds: more merchants per city, and guaranteed vehicle and account owners in each city. A 20-seed sweep then generated every seed, and 19 pass every data check. The one failure is a spike that came out weak by chance, left visible rather than hidden by loosening the test.

### Weak expectations, tests and evidence

17. **An expectation passed without showing anything.** "Each planted cluster is ≥ 80% inside one community" was met, but the communities were whole cities: only 19–33% of each community belonged to the cluster (purity). Claude Code wrote the expectation without a purity condition.
    *What caught it:* Claude Code flagged it in its Phase 4 report.
    *What changed:* I chose to commit Phase 4 with the result as it stood, labelled "met, but hollow". Claude Code proposed a revised method with a purity condition. I approved it as a separately declared expectation, with one attempt on a seed nothing had touched. It failed, so the city-level result stands.
18. **"Decoy loop not flagged" passed, but proved nothing about the time check.** The decoy broke two rules at once, so the amount check alone rejected it.
    *What caught it:* Claude Code flagged it in the same report.
    *What changed:* Claude Code proposed a second decoy that only the time check can reject. I approved it as its own declared expectation. It was met on the unseen seed.
19. **The NLP confidence defaults were guesses,** including 0.6 for all NER.
    *What caught it:* Claude Code called them guesses when proposing them in Phase 0. I required each to be marked in the code as an unvalidated prior, and listed as a known limitation until measured.
    *What changed:* Claude Code measured precision per label in Phase 2 and recommended per-label values, which I approved. Organization precision is 0.29.
20. **The generated reports had only 4 Organization mentions,** too few to measure accuracy.
    *What caught it:* Claude Code flagged it in the Phase 1 report.
    *What changed:* I approved its fix and had it done first in Phase 2, before extraction was scored. The generator now adds employer mentions (17), each backed by salary payments in the bank data.
21. **A proposed fix would have looked perfect for the wrong reason.** Claude Code proposed relabelling spans tagged as organizations when they exactly match a registered person, and noted that it would look perfect here because every person in this data is in a registry.
    *What caught it:* I rejected it because it only looks right when the registry is complete. This synthetic data guarantees that; real data doesn't.
    *What changed:* it was kept out of the pipeline and documented as future work, with the circularity caveat stated explicitly.
22. **A spike rule fitted to the results.** After two revisions failed, Claude Code noticed that flagging an incident when *either* spike rule fires would catch 4, 5 and 6 of 6 planted spikes on the three seeds. It pointed out that it found this only after seeing all three.
    *What caught it:* I rejected adopting it, or opening another seed to test it, because it was derived from looking at test results.
    *What changed:* it is recorded as unvalidated future work.
23. **Two edit methods had tests but no caller.** Claude Code built `update_node` and `update_edge` for future analyst edits, flagged that only their own tests used them, and recommended keeping them.
    *What caught it:* I required them to be removed, or wired to a real caller, before Phase 5 could be committed, rather than kept speculatively.
    *What changed:* removed, along with the tests that tested nothing else.

### Problems only a real browser showed

*What caught them:* Claude Code's Playwright check of the page, one of the Phase 6 checks it wrote down before building. All four were found after the API tests were already passing.

24. **The page froze for 6.6 seconds** while the browser computed the graph layout.
    *What changed:* the server computes a seeded layout once, and the browser draws in 136 ms.
25. **The browser kept running an old `app.js`** after it had changed.
    *What changed:* a `no-cache` header, now covered by a test.
26. **Selecting a person left 5 of the 8 nodes in their neighbourhood off-screen.**
    *What changed:* the view fits the whole neighbourhood.
27. **A missing favicon logged a console error.**
    *What changed:* an inline icon.

## How claims were kept honest

- **I kept control of each step.**
  - Each phase stopped for my sign-off.
  - Each commit had to state what was checked, not just what was built.
  - If Claude Code was ever tempted to bend the schema rule that structured records never link two people directly, it had to stop and flag it to me rather than special-case it.
- **Expectations came before results.** Claude Code wrote each phase's expectations before the first run and reported them as met or not met, never edited afterwards. Passes that showed little were labelled as such.
- **One attempt on unseen data.** Claude Code proposed testing revisions on a seed never run through analysis. I required each revision to be declared and reported separately. I also ruled out trying more seeds if the second attempt at community detection failed too, and Claude Code applied the same one-attempt rule to all three revisions. Two of three failed and were not retried.
- **The known flaw was planted on purpose.** Claude Code pointed out that my same-name matching rule would merge different people who share a name. I had one such pair planted in the data, with the wrong merge predicted in the ground truth in advance. The merged node ranks 5th on betweenness: it looks like a broker because two strangers became one person.
- **No tuning to the test data.** Claude Code wrote the 22-sentence challenge set before the relation rules and scored it once. It also declined to fit cleanup rules to the evaluation data.
- **Mutation checks in Phases 1, 3, 5 and 6.** Claude Code broke the code on purpose to confirm a test fails. Examples:
  - removing the spike multiplier from the generator;
  - putting the "works at" bug back;
  - leaving a column out of the block hash;
  - not recording merges in the audit log;
  - writing to the audit log after the graph changes;
  - making neighbourhoods directed;
  - skipping the replay step in verification.
- **Determinism.** The generator and every committed output are byte-identical across runs and hash seeds.
- **The audit design goes beyond my brief.** My brief asked for a hash chain with a function that detects tampering. Claude Code added two things:
  - a replay that rebuilds the graph from the log alone, to prove the log is complete;
  - a tamper demo that compares exact failures and also shows the chain's known weakness: rewriting every later hash passes the internal checks, and only an anchor saved outside the database catches it.
- **Ground truth stays out of the pipeline.** My brief reserved it for evaluation, and a test fails if the API code ever refers to it.

## Results (seed 42 unless noted)

| Area | Result |
|---|---|
| Graph | 529 nodes, 8,120 edges (8,015 from structured records, 105 from report text) |
| Entity extraction (spaCy `en_core_web_md`) | F1: Person 90.3, Location 76.7, Organization 46.6 (precision 30.4) |
| Relation extraction | Precision 100 / recall 82.5 with perfect entities; 98.5 / 63.1 end to end; recall 12.5% on unfamiliar, hand-written phrasing |
| Bridge people by betweenness | **Met:** ranks 3 and 6 of 140 (same on seed 7) |
| Planted clusters as communities | **Met, but hollow:** purity 19–33%. The revised method was **not met** on the unseen seed |
| Planted call spikes | **Not met:** 4 of 6 on seeds 42 and 7, 2 of 6 on the unseen seed; 0 false alarms |
| Laundering loops | Both flagged with exactly their transactions; both decoys rejected; the time check shown to be necessary |
| Planted false merge | The two merged "Rahul Sharma"s rank 5th on betweenness on all three seeds, a fake broker as predicted |
| Audit chain | 24,338 blocks verify; replay rebuilds the graph exactly; 7 of 7 tamper scenarios behave as expected |

## Limits

- **The data is easier than real data.** Reports come from 15 templates, with every name spelled exactly, so extraction scores are best cases. Seed 7 uses the same templates, so it tests stability, not generalisation.
- **Entity resolution is exact match only.** Common names wrongly merge; aliases and spelling variants wrongly stay separate.
- **Community detection finds cities, not gangs.**
- **The hash chain detects tampering but can't prevent it.** The demo anchor sits next to the database.
- **The API has no authentication** and serves localhost only.

## Where to look

- [README](../README.md): the protocol, results, limitations and production changes for each phase
- The commit history: one commit per phase, each stating what was built and what was checked
- `output/`: the JSON reports behind every number
- [`docs/`](.): screenshots of the graph explorer, verified and tampered

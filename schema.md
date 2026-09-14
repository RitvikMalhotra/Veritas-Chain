# Graph Schema

This defines every node type and edge type the system can store, and the rules that
decide when two records are the same entity. The code version of this document is
[`veritas/models.py`](veritas/models.py). The key functions are in
[`veritas/normalize.py`](veritas/normalize.py), and tests for each rule are in
[`tests/test_models.py`](tests/test_models.py).

All data in this project is **synthetic**: generated names, numbers, places and reports.
None of it comes from real people or real law-enforcement records.

---

## 1. Design principles

| Principle | Why |
|---|---|
| **A fixed, closed set of types.** Unknown node types, edge types or fields fail validation. | Analytics code can rely on the types. A typo like `CALLLED` fails loudly instead of creating a type nobody queries. |
| **Instruments are separate from people.** A call links two *phones*, and a transfer links two *accounts*. A separate edge says who uses the phone or holds the account. | A call record proves that one number called another. It does not prove who was holding the phone. Keeping "who uses this number" as its own edge, with its own source and confidence, means a wrong subscriber record cannot corrupt the call data. |
| **Every edge has provenance.** Each edge carries `timestamp`, `source_document_id`, `extraction_method` and `confidence`. | Any link in the graph can be traced back to the record that produced it, and weak links can be filtered out. |
| **IDs come from content.** Node IDs are built from normalized keys. Edge IDs are hashes of the edge's content. IDs are never taken from input. | Exact-match entity resolution is simply "same ID". Loading the same record twice produces the same ID, so duplicates collapse. A stale or tampered `id` in the input cannot point a record at the wrong entity. |
| **A false split is better than a false merge.** | Wrongly merging two people invents a link between strangers, and that link feeds straight into centrality scores. Wrongly splitting one person only loses a link. Where a key rule is ambiguous, it leans towards splitting. |

---

## 2. IDs

**Node ID** = `"<NodeType>:<canonical_key>"`, for example `Person:rajesh_kumar` or `Phone:+919876543210`.
Because the type is a prefix, an edge's endpoint types can be checked without looking up the nodes.

**Edge ID** = `"edge:" + sha256(type | source_id | target_id | timestamp_in_UTC | source_document_id)[:16]`.
The timestamp is converted to UTC before hashing, so the same moment written in IST or UTC gives the same ID.
64 bits is far more than enough to avoid collisions at this project's scale (thousands of edges).

---

## 3. Node types

Every node has `type`, `source_document_ids` (at least one; it grows when records merge) and a computed `id`.

| Type | Fields | Canonical key (the entity-resolution rule) | Example ID |
|---|---|---|---|
| **Person** | `name` (display form) | Unicode-folded, lowercase, punctuation removed, leading titles removed (`mr, mrs, ms, miss, dr, shri, sri, smt`), words joined with `_` | `Person:rajesh_kumar` |
| **Phone** | `number` (stored as E.164) | Indian mobile number: `+91` followed by 10 digits starting 6–9. Accepts `+91`, `0091`, `0` prefixes, spaces and dashes. | `Phone:+919876543210` |
| **Location** | `name`, `city?` | `key(name)`, plus `:key(city)` when the city is known | `Location:hotel_sai_palace:mumbai` |
| **Organization** | `name`, `org_type?` | Same as the generic key, but `private`→`pvt` and `limited`→`ltd` | `Organization:sai_logistics_pvt_ltd` |
| **Vehicle** | `registration_number` (normalized), `make_model?`, `color?` | Uppercase with separators removed. Must match the standard format `AA00AAA0000` (the RTO code is 1–2 digits and the series is 0–3 letters) or the BH-series format `00BH0000AA`. | `Vehicle:MH12AB1234` |
| **Event** | `event_ref`, `event_type`, `occurred_at`, `description?` | `key(event_ref)`. Events are **never** merged by description. Only the same reference is the same event. | `Event:evt_0003` |
| **BankAccount** | `ifsc`, `account_number`, `bank_name?` | `IFSC:account_number`. The IFSC is part of the key because account numbers are only unique within a bank. | `BankAccount:SBIN0001234:123456789012` |

`?` means the field is optional. Optional fields are for display only and are never part of the key.

---

## 4. Edge types

### Fields on every edge

| Field | Meaning |
|---|---|
| `source_id`, `target_id` | Node IDs. The pair of endpoint types must be allowed for this edge type (see table below). Self-loops are rejected. |
| `timestamp` | Must include a timezone; naive datetimes are rejected. For **event-like** edges (`CALLED`, `TRANSFERRED_MONEY_TO`, `MET_AT`, `PRESENT_AT_EVENT`) it is **when the thing happened**. For **state-like** edges (`MEMBER_OF`, `OWNS_VEHICLE`, `USES_PHONE`, `HOLDS_ACCOUNT`, `ASSOCIATED_WITH`) it is **when the source recorded the fact** (registration, KYC or report date). |
| `source_document_id` | The record the edge came from, such as `CDR-000481`, `TXN-000042` or `FIR-0007`. |
| `extraction_method` | `structured` (a row in a CDR, bank or registry file), `text_pattern` (an explicit phrase in a report, like "X called Y"), or `text_cooccurrence` (two entities in the same sentence with no relation phrase). |
| `confidence` | A number from 0 to 1. If omitted, it is filled from config based on `extraction_method` (see section 5). |

### Edge types, direction and extra fields

| Edge | Allowed endpoints (source → target) | Direction means | Extra fields |
|---|---|---|---|
| **CALLED** | Phone→Phone; Person→Person | caller → receiver | `duration_seconds?`, `call_type` (`voice`/`sms`) |
| **MET_AT** | Person→Location | person → place | — |
| **TRANSFERRED_MONEY_TO** | BankAccount→BankAccount; Person→Person | payer → payee | `amount_inr?` (Decimal > 0), `transaction_ref?`, `mode?` (`NEFT/IMPS/RTGS/UPI/CASH`) |
| **MEMBER_OF** | Person→Organization | member → org | `role?` |
| **PRESENT_AT_EVENT** | Person→Event; Vehicle→Event | participant → event | — |
| **OWNS_VEHICLE** | Person→Vehicle; Organization→Vehicle | owner → vehicle | — |
| **USES_PHONE** † | Person→Phone | user → number | — |
| **HOLDS_ACCOUNT** † | Person→BankAccount; Organization→BankAccount | holder → account | — |
| **ASSOCIATED_WITH** | any → any | none (store in either direction; treat as undirected) | `context` (**required**: why the link exists) |

† Not in the original brief. Added because otherwise nothing links a person to a phone or account (see section 6).

Notes on specific choices:

- **Person→Person on `CALLED` and `TRANSFERRED_MONEY_TO`.** This is only for text-derived edges where the report names people but gives no number or account ("Ravi paid Suresh ₹50,000 in cash"). Structured data always uses the Phone and BankAccount nodes, with no exceptions. The model enforces this: a `structured` Person→Person edge of either type fails validation. Any case that seems to need an exception gets raised as a schema question, not special-cased.
- **`MET_AT` is Person→Location, not Person→Person.** A meeting between A, B and C at location L is stored as three `MET_AT` edges that share the same `source_document_id` and `timestamp`. Storing it Person→Person would need 3 edges for 3 people and 6 for 4, and would lose the place. The analytics layer builds person-to-person links from people who were at the same place.
- **Event location.** There is no `OCCURRED_AT` edge type. For now, an event's location is `ASSOCIATED_WITH(Event→Location, context="event location")`.
- **`MultiDiGraph`.** Every call and transfer is its own edge, because spike detection needs each timestamp. Direction is kept because circular-flow detection (A→B→C→A) depends on it.
- **Validation only checks endpoint *types*, not that the nodes exist.** Checking that nodes exist is the graph builder's job (Phase 3).

---

## 5. Confidence

Confidence is an **ordinal trust weight**: 0.9 is trusted more than 0.4. It is **not a calibrated
probability**, and the defaults are starting values, not measured ones.

All defaults are in [`veritas/config.py`](veritas/config.py). You can override any of them with
an environment variable, for example `VERITAS_CONF_TEXT_PATTERN=0.8`.

| Setting | Default | Status | Applies to | Reasoning |
|---|---|---|---|---|
| `structured` | 1.0 | fixed by design | edges from CDR, bank and registry rows | The record exists exactly as stated. This does not mean the *person attribution* is true; that is what the separate `USES_PHONE`/`HOLDS_ACCOUNT` edges are for. |
| `mention_regex` | 0.95 | accepted, no measurement planned | phone and plate mentions | A deterministic format match. A valid format still doesn't prove the number is real. |
| `text_pattern` | 0.7 | checked, kept conservative | edges from an explicit relation phrase | The text states the relationship, but parsing can be wrong. |
| `text_cooccurrence` | 0.4 | checked, kept conservative | `ASSOCIATED_WITH` from being in the same sentence | Being mentioned together is weak evidence. |
| `mention_spacy_ner_person` | 0.92 | measured (upper bound) | Person mentions | spaCy `en_core_web_md` precision, 146/159 |
| `mention_spacy_ner_location` | 0.97 | measured (upper bound) | Location mentions | 65/67 |
| `mention_spacy_ner_organization` | 0.29 | measured (upper bound) | Organization mentions | 34/116: businesses, acronyms and vehicle models tagged ORG |

The two relation defaults were **checked in Phase 3 and deliberately kept at 0.7 and 0.4 (approved)**.
The measurements below come from template text, so they are circular evidence and can't justify higher values. The one probe with different phrasing already dropped to 3/4.
The measurements do confirm the ordering: pattern relations are more reliable than same-sentence edges.

**Phase 3 measurement (pooled over seeds 42 and 7):**

| | Gold entities | End to end |
|---|---|---|
| `text_pattern` precision | 170/170 | 143/144 |
| `text_cooccurrence` (a real tie between the people) | 73/78 | 63/88 |

The hand-written challenge set gave 3/4 pattern precision: the negation "Neither X nor Y was present" produced a false edge.
Text edge confidence also applies the min rule below, so these method defaults act on top of the entity confidences.

The three NER values replaced a single unvalidated 0.6 (approved after Phase 2). They are lenient precision pooled over seeds 42 and 7.
They come from clean, templated text, so they are **upper bounds**. They were measured for `en_core_web_md` and would need re-measuring for any other model.

**Caveat on NER confidence.** spaCy's standard NER pipeline does **not** give a probability for
each entity. The Phase 2 "confidence scores" will therefore be a fixed value per method (and possibly
per label). The honest way to set that value is to measure precision per label against the entities
planted in Phase 1, then use the measured precision as the default. This is planned for Phase 2.

**Planned rule for text-derived edges (Phase 3):**
`edge.confidence = min(method_default, confidence of the source mention, confidence of the target mention)`.
A relation can't be more trustworthy than the weaker of the two entities it connects.

---

## 6. Decision record: two edge types added to the brief

**Status: approved.** `USES_PHONE` and `HOLDS_ACCOUNT` are first-class edge types. Their allowed endpoints are:

| Edge | Allowed endpoints | Typical structured source | Timestamp means |
|---|---|---|---|
| `USES_PHONE` | Person→Phone | SIM subscriber registry | activation / registration date |
| `HOLDS_ACCOUNT` | Person→BankAccount; Organization→BankAccount | bank KYC records | account opening date |

**Problem.** The brief's edge list has no way to connect a Person to a Phone or to a BankAccount.
Without that connection, CDR and bank data never reach Person nodes, so centrality over
*individuals* (Phase 4) would be impossible.

**Alternative that was rejected.** Store both links as `ASSOCIATED_WITH` with a `context` string.
That would put the most important structural links in the fallback type. Analytics would have to
parse `context` strings, and "registered subscriber" would look the same as "mentioned in the same sentence".

---

## 7. Entity resolution: exact match only, with known limitations

The rule is: **same canonical key → same node.** Nothing else is merged. Fuzzy or probabilistic
matching is future work and is not implemented.

Known failure modes, which will not be hidden:

| Failure | Example | Direction |
|---|---|---|
| Common names collide | Two different people both called "Rahul Sharma" become one node | **False merge**. The brief's name-based rule causes this, and it is the most damaging failure. |
| Initials and short forms | "R. Sharma" ≠ "Rahul Sharma" | False split |
| Transliteration variants | "Mohd. Irfan" ≠ "Mohammed Irfan" | False split |
| Aliases (a common FIR style) | "Ramesh alias Pappu" is not linked to "Pappu" | False split |
| Location written without a city | "Hotel Sai Palace" ≠ "Hotel Sai Palace, Mumbai" | False split, chosen deliberately (section 1) |
| Plate with an unpadded number | "MH12AB123" is rejected instead of being padded to 0123 | Rejected, because without separators the split between RTO code, series and number is ambiguous |
| Landlines and non-Indian numbers | "022-2345-6789", "+1 415…" | Rejected. The schema only covers Indian mobiles. |
| Names in non-Latin scripts | Names written in Devanagari | Not supported. Names are assumed to be romanized. |

**Planted test of the false-merge case.** The Phase 1 data deliberately includes two different
people with the same name. `ground_truth.json` records that they are separate people *and* that
this rule is expected to merge them wrongly, so the effect can be measured in Phases 3–4 instead of
turning up as an unexplained bug.

**Merge policy (implemented in Phase 3, `veritas/graph/builder.py`):** the display attributes seen first are kept, and `source_document_ids` becomes the union of both.
Structured data is loaded before text, so registry spellings win over report spellings. The build report lists every node that received more than one display-name variant.

**Places in report text (Phase 3):**
- In "X, City", the city is stored on X's Location node, so "Balan Warehouse, Mumbai" resolves to the same node as the registry place. The city is not created as a separate node.
- A business in a place phrase ("met … at X", "near X, City") is a Location even if NER labelled it ORG.
- A place mentioned without a city still splits from the registry place, as listed in the table above.

---

## 8. Entity mentions: what Phase 2 hands to Phase 3

`EntityMention` records one span extracted from one document:
`document_id, node_type, text, start_char, end_char, method, confidence`.

- `end_char - start_char` must equal `len(text)`, so a span can always be checked against the source text.
- Each extraction method can only produce certain types: `regex` → Phone, Vehicle; `spacy_ner` → Person, Location, Organization.
  Bank accounts and events are **not** extracted from report text. They come from structured data only.

---

## 9. How the analytics layer will use this (preview, not built yet)

The graph mixes several node types. Running betweenness on it directly would rank busy phone
numbers and popular locations as "key individuals". Phase 4 will therefore compute person-level
centrality on a **Person projection**. Two people are connected if any of these hold:

- their phones called each other (via `USES_PHONE`)
- their accounts transacted (via `HOLDS_ACCOUNT`)
- they were at the same place or event
- they have a direct text-derived edge

Edge weights will take confidence into account. The exact weighting will be decided and documented in Phase 4.

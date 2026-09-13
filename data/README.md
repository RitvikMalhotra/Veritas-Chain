# Synthetic dataset

**Everything in this folder is generated.** The people, phone numbers, bank accounts, vehicles,
companies and incident reports are all fictional. Bank names and IFSC prefixes (`ZARV`, `ZKVR`,
`ZNMD`, `ZGDV`) are invented. Phone numbers and plates are random but valid-format, so they could
coincidentally match real ones. Do not use them to contact anyone.

Regenerate (deterministic for a given seed):

```bash
python -m veritas.synth --seed 42 --out data
```

## What the pipeline may read

| Path | Source it imitates | Rows (seed 42) |
|---|---|---|
| `structured/subscribers.csv` | SIM subscriber registry | one row per SIM |
| `structured/cdr.csv` | Call detail records | calls and SMS, Jan–Mar 2025 |
| `structured/bank_accounts.csv` | Bank KYC records | one row per account |
| `structured/transactions.csv` | Bank transfers | NEFT / IMPS / RTGS / UPI |
| `structured/vehicle_registry.csv` | Vehicle registration records | one row per vehicle |
| `structured/company_registry.csv` | Company director filings | one row per director |
| `structured/incident_register.csv` | Incident register | one row per FIR |
| `firs/FIR-<CITY>-2025-<NNNN>.txt` | First Information Reports | 24 reports |

## What the pipeline must not read

`ground_truth.json` is for **evaluation only**. It records what was planted, so pipeline output can be scored against it.

## Conventions

- **Timestamps** are ISO 8601 with a `+05:30` (IST) offset.
- **Phone formats differ between sources on purpose.** Subscriber rows use 10 digits, CDR rows use `91` + 10 digits, and FIR text mixes `98765 43210`, `+91-9876543210`, `09876543210` and similar. Exact-match entity resolution only works if normalization works.
- **Plates** are hyphenated in the registry (`MH-12-AB-1234`) and appear in FIR text with hyphens, with spaces, or with no separator.
- **FIR files** have a metadata header, a blank line, a line reading `NARRATIVE`, and then the narrative on a single line. Entity offsets in `ground_truth.json` are Python string indices into that narrative line. Files are LF-only (enforced by `.gitattributes`), so offsets stay stable on Windows checkouts.
- **Acts and sections** in FIR headers (BNS 2023, NDPS Act, IT Act) are illustrative and chosen to fit each incident type. They are not legal advice.

## `ground_truth.json` sections

| Key | Contents |
|---|---|
| `clusters` | the 4 planted clusters: leader, lieutenants, members, meeting places, front company |
| `key_individuals` | leaders, lieutenants and bridges, each with the reason they matter |
| `planted_structure_notes` | how calls and money were structured. Each note is checked by `tests/test_synth.py`. |
| `signal_visibility` | measured call-volume and contact ranks of key people. Computed from true identities. |
| `bridges` | the 2 bridge people, plus the scoring rule for their community assignment |
| `planted_collisions` | the two different "Rahul Sharma"s, and the expected false merge |
| `money_cycles` | the planted laundering cycle (2 rounds), a decoy cycle, and any incidental cycles (expected: none) |
| `events` | every incident, whether a call spike was planted, and how strong it came out |
| `persons` | every person, with their true id, role, phones, account and vehicles |
| `fir_annotations` | every entity mention (text, span, type, expected node id) and every relation stated in each report |

# Claim-quality benchmark

The benchmark measures whether Jevy Graph preserves supported atomic claims and
their boundaries, qualifiers, and scope. It does not treat accepted claim count
as accuracy.

## Suite layout

- `corpus/` contains frozen source documents and their source metadata.
- `fixtures/` contains annotated claims and instructions.
- `test-manifest.json` hash-locks the held-out test fixtures.
- `audits/` preserves source reviews and diagnostic evidence.
- `RESULTS.md` contains the current aggregate snapshot.

The frozen Constitution combines the National Archives Constitution,
Bill of Rights, and Amendments 11–27 transcripts. Development examples also
include selected Re-DocRED, BioRED, BC4GO, biomedical literature, and structured
table sources. External labels are reviewed before use because relation corpora
can omit valid claims present in their text.

## Annotation schema

Each expected atomic claim records:

- subject, relation, and object;
- exact supporting evidence;
- polarity and modality;
- conditions, measurements, comparison, and attribution when present;
- source unit and locator when available;
- whether the claim is in scope for the fixture's instruction; and
- equivalent graph forms in `alternatives` when needed.

A fixture is `exhaustive` only after the reviewer checks the entire frozen
passage for omitted claims and reviews every emitted claim. `codex_reviewed`
fixtures support development and regression. Only independently
`human_reviewed` test fixtures satisfy the final release gate.

## Split and adjudication rules

The evaluator scores only hash-locked `test` fixtures for release. A source
moves to development once its failures inform extraction rules or thresholds.
An unmatched output is a review item because an incomplete gold set can label a
valid claim as false. For an exhaustive fixture, every unmatched output must be
added to gold or recorded in `adjudicated_unmatched` with one of:

- `unsupported`;
- `wrong_boundary`;
- `wrong_qualifier`; or
- `out_of_scope`.

The release gate requires:

- at least 95% precision and recall in every domain;
- at least 95% precision and recall for every instruction profile;
- zero unsupported critical claims;
- at least two held-out fixtures and 30 in-scope claims per domain;
- at least 20 held-out claims per instruction profile; and
- exhaustive independent human review.

## Run

No-cost deterministic candidate audit:

```bash
PYTHONPATH=src python3 scripts/evaluate.py \
  --output out/quality-offline.json
```

Verified audit with paid Jev calls:

```bash
PYTHONPATH=src python3 scripts/evaluate.py --live \
  --output out/quality-live.json
```

Target one or more fixtures with repeated `--id FIXTURE_ID`. Use
`--allow-reject` only for an explicit comparison of Jev's experimental
`none of these` selection policy.

Full Constitution inventory:

```bash
PYTHONPATH=src python3 scripts/constitution_audit.py
```

Five-paper local dependency-parser check:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dependency_unseen.py
```

Reports record conversion, extraction, selection, and verification time; Jev
requests, bytes, and reported tokens; rejected claims and reasons; unmatched
outputs; excluded gold claims; and the first pipeline stage where each expected
claim was lost. Offline reports intentionally leave final precision and recall
unset because no Jev selection or output adjudication occurred.

# Current claim-quality results

Snapshot date: September 27, 2026.

## Offline candidate audit

The current no-cost run evaluates 104 active fixtures and 1,267 in-scope
reviewed claims.

| Domain | Fixtures | Gold claims | Matched candidates | Known-claim coverage | Emitted first choices |
| --- | ---: | ---: | ---: | ---: | ---: |
| Biomedical | 20 | 240 | 240 | 100% | 287 |
| Legal | 76 | 919 | 919 | 100% | 928 |
| General prose | 4 | 62 | 62 | 100% | 67 |
| Structured data | 4 | 46 | 46 | 100% | 46 |
| **Total** | **104** | **1,267** | **1,267** | **100%** | **1,328** |

This is candidate coverage: each reviewed claim has a complete option available
to Jev. The 1,328 deterministic first choices include unmatched outputs awaiting
review, so this table does not report output precision.

The Constitution audit covers all 74 substantive units in the frozen source.
All units have exhaustive Codex-reviewed development annotations.

## Held-out inventory

The hash-locked test manifest currently contains five fixtures:

| Domain | Fixtures | In-scope claims | Offline matched |
| --- | ---: | ---: | ---: |
| Biomedical | 1 | 3 | 3 |
| Legal | 1 | 3 | 3 |
| General prose | 1 | 3 | 3 |
| Structured data | 2 | 42 | 42 |

The release gate remains closed. Biomedical, legal, and general prose do not yet
meet the required held-out sample size, and the fixtures are not independently
human reviewed. Precision and recall therefore remain unset in the current
offline report.

## Separate unseen scientific check

The untouched five-paper dependency-parser audit emits 57 structured claims for
66 audited targets, with 10 exact raw label matches. This separate check is kept
visible because it measures generalization beyond the tuned fixture suite. It
is not combined with the candidate-coverage table above.

## Reproduce

```bash
PYTHONPATH=src python3 scripts/evaluate.py \
  --output out/quality-offline.json
PYTHONPATH=src .venv/bin/python scripts/audit_dependency_unseen.py
```

The release target is at least 95% precision and recall in every domain and
instruction profile, with zero unsupported critical claims on sufficient,
independently human-reviewed held-out data.

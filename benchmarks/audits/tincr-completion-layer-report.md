# Routed completion-layer experiment

This experiment starts from the cached Jev-only TINCR Results graph. It does
not rerun source conversion, deterministic extraction, candidate selection, or
the original verifier.

One document-wide Luna Low call reviews the 130 accepted Results claims against
the complete Results section and proposes at most 24 repairs. Jev then handles
replacement choice, ordinary verification, and four independent completion
questions: exact support, graph boundaries, qualifier coverage, and atomicity.
Only repairs clearing every calibrated dimension enter the final graph.

## Result

| Measure | Cached Jev baseline | Completion layer |
| --- | ---: | ---: |
| Complete claim precision | 81/130 (62.3%) | **84/124 (67.7%)** |
| Complete Results recall | 43/88 (48.9%) | **45/88 (51.1%)** |
| Unsupported accepted claims | 3 | **0** |
| Accepted Results claims | 130 | 124 |

The completion call proposed 16 records. The dimension gate admitted four:

- complete inverse TINCR–EpICD correlation with the 44-pair statistic;
- complete TOP-Flash increase, duplicating an already complete finding;
- complete predicted Sp1 binding site with one-site/JARSPAR/PROMO context;
- complete EpICD increase in CRC tissues, duplicating an already complete finding.

Thus, two partial gold findings became complete. Ten weak baseline records were
removed. One removed record was a valid standalone TINCR re-expression claim,
so the net complete-output increase was three.

## Cost

A fresh run requires:

- one Luna Low request: 11,499 input / 1,894 output tokens, 13.16 seconds;
- four Jev requests including repair decisions and the dimension gate: about
  30,003 input / 2,649 output tokens, under one second in the cached replay;
- no base-extraction rerun.

## Findings

The routing idea improves precision and removes unsupported accepted claims, but
the recall gain is small. The proposal layer still bundled distinct outcomes,
experimental arms, and cell-line findings. Jev's dimension scores were useful
for rejecting those bundles, but did not turn them into atomic replacements.

The gate thresholds were calibrated on these 16 TINCR proposals. They are not a
held-out result and must remain experimental until evaluated on untouched text.

The next useful change is to require the proposal schema itself to emit one
claim per outcome and per material experimental arm, with reusable context IDs.
That addresses the source of most rejected repairs rather than relaxing the
gate.

Artifacts:

- `out/tincr-completion-layer-live.json`
- `benchmarks/audits/tincr-completion-layer-review.json`
- `scripts/probe_completion_layer.py`
- `JevClient.assess_completeness` in `src/jevy_graph/jev.py`

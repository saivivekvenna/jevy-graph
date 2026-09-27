# Full Results phrase-menu benchmark

The frozen phrase-menu prototype was run over the complete TINCR Results
section after its 12-sentence development pilot. No phrase or threshold changes
were made after inspecting this scale-run output.

## Strict result

| Measure | Phrase-menu scale run | Prior Jev pipeline |
| --- | ---: | ---: |
| Complete Results recall | **10/88 (11.4%)** | 43/88 (48.9%) |
| Related record present (complete or partial) | 61/88 (69.3%) | 82/88 (93.2%) |
| Complete claim precision | **30/99 (30.3%)** | 81/130 (62.3%) |
| Missing gold findings | 27 | 6 |
| Accepted Results claims | 99 | 130 |

The prior-pipeline comparison uses the frozen Jev-only audit. The phrase result
is a Codex-reviewed development measurement, not independent human review.

## Runtime

- 119 exact source passages
- 109 proposed records; 99 passed the existing Jev verifier
- 49 Jev requests
- 175,174 input and 38,611 output tokens
- 8.50 seconds measured wall time
- zero Luna/OpenAI generation calls

## What generalized

The pipeline often located the right relation. It preserved several difficult
sentence-local structures, including negation, passive repression, partial
suppression, TOP-Flash magnitude, a method condition, and some coordinated
outcomes. Sixty-one of 88 gold findings had at least a related graph record.

## What failed

The small pilot hid four document-scale requirements:

1. **One choice is not exhaustive.** A predicate with serosal invasion, lymph
   metastasis, and TNM classification yielded only one object. The algorithm
   needs repeated selection or independent decisions for every plausible object.
2. **Paragraph context is material.** Phrases such as “opposite effects,” “all
   these effects,” and pronouns require entities and intervention arms from
   preceding sentences. Sentence-only menus cannot recover them.
3. **Conditions must be attached structurally.** Measurements, comparators,
   cell lines, attribution, and hedging were commonly left in evidence or
   attached to the wrong slot. The broad verifier still accepted these records.
4. **Surface grammar is not a canonical graph.** Passive wording and clause
   fragments remained in subject/predicate/object fields. Exact source spans are
   valuable provenance, but graph fields need deterministic normalization after
   selection.

The verifier acceptance rate was 99/109. It is not an accuracy measurement:
only 30 accepted records were complete under the benchmark rubric.

## Conclusion

The concept works as a relation locator, but this implementation is not a viable
replacement for the current extractor. The 12-sentence 100% result did not
generalize. The useful next version should retain phrase menus while changing
the unit from an isolated sentence to a paragraph context record, enumerate all
subject–predicate–object bindings, and verify completeness dimensions separately.
It should be evaluated on an untouched sample before another full Results run.

Artifacts:

- `out/tincr-phrase-scale-live.json`
- `benchmarks/audits/tincr-phrase-scale-review.json`
- `scripts/benchmark_phrase_scale.py`
- `src/jevy_graph/phrase_pilot.py`

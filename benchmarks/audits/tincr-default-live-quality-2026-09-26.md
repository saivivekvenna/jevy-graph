# Full-paper JevyGraph quality check: TINCR/EpCAM

## Input and run

The default, unfocused Jev-only pipeline processed the complete article text for *Loss of TINCR expression promotes proliferation, metastasis through activating EpCAM cleavage in colorectal cancer* (PMCID: PMC5008388). The local JATS conversion includes the title, abstract, body, and figure captions; it excludes references and publisher metadata. The source is `benchmarks/corpus/tincr-epcam-full.txt`, SHA-256 `1d964bd20973ac7f57bd36ec6128640d37c2a7d3c884740e4808919b1313b00c`.

Run command:

```sh
PYTHONPATH=src python3 scripts/benchmark.py benchmarks/corpus/tincr-epcam-full.txt --live --workers 8 --batch-size 32 --output out/full-tincr-default-live-2026-09-26.json
```

The run generated 437 frames and 7,003 candidate options, accepted 270 claims, and rejected 137. It made 28 Jev requests with 390,093 input tokens and 81,240 output tokens. Pipeline-reported compute time was 1.624 seconds for the already converted text; this is not a PDF upload or annotation time measurement. No OpenAI API model was used in this run.

## Codex claim review

| Measure | Result | Scope |
| --- | ---: | --- |
| Complete, supported accepted claims | 144/270 (53.3%) | All accepted claims in the article, including valid background and procedure claims |
| Definitely flawed accepted claims | 121/270 (44.8%) | 39 missing material qualifiers, 79 wrong boundaries or relations, 3 unsupported |
| Source-ambiguous accepted claims | 5/270 (1.9%) | Kept separate from both correct and incorrect |
| Complete Results claim precision | 81/130 (62.3%) | Accepted claims from Results text and captions |
| Complete Results claim recall | 43/88 (48.9%) | Reviewed, unambiguous Results gold claims |
| Partial or missing Results gold | 39 partial; 6 missing | Same 88-claim denominator |

Precision requires the complete proposition to be supported, including actor, relation, direction, comparator, condition, modality, and attribution. Recall requires one accepted claim to represent the complete reviewed atomic fact. These are Codex-reviewed **development** annotations, not independently adjudicated held-out scores. The 88-claim gold covers Results, so this run does not establish complete whole-paper recall.

Examples of important errors:

- The graph says **EpCAM disrupted genes**; the source says EpCAM was among the genes disrupted after TINCR depletion (accepted output 133).
- It makes the **G0/G1 proportion** the actor of an S-phase increase; the source attributes that increase to TINCR downregulation (output 119).
- Three accepted claims turn a **proposed TINCR–EpCAM reciprocal model** in a caption into standalone assertions that EpCAM regulates proliferation, invasion, and metastasis (outputs 225–227).
- It misses complete Results assertions that **c-Myc represses TINCR** and partially suppresses Sp1-induced TINCR expression (gold R079–R080).
- Introductory and discussion claims frequently lose citation or prior-study attribution. The non-Results audit flags 19 materially misleading claims; the Results audit marks three standalone EpCAM effects unsupported.

## Assessment

The pipeline is fast and finds many of the paper's main concepts, but this article is well below the intended 95% precision and recall bar. The main limit is claim construction: thousands of deterministic options still fail to preserve complete actors, directions, comparisons, and conditions; Jev can select a plausible but wrong option. The 270 accepted count is a volume measure, not an accuracy measure.

Artifacts: `out/full-tincr-default-live-2026-09-26.json`, `benchmarks/audits/tincr-default-live-results-precision-2026-09-26.json`, `benchmarks/audits/tincr-default-live-other-precision-2026-09-26.json`, and `benchmarks/audits/tincr-default-live-results-recall-2026-09-26.json`. Every accepted output and every reviewed Results gold claim has an individual audit verdict.

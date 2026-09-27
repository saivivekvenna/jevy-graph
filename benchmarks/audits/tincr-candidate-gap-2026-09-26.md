# TINCR full-paper candidate-generation gaps

Local-only inspection of [`tincr-epcam-full.txt`](../corpus/tincr-epcam-full.txt), the [default Jev-only graph](../../out/full-tincr-live-2026-09-25.json), and the [model-discovery diagnostic](../../out/full-tincr-model-discovery-2026-09-26.json). Indices below are zero-based within each output's `claims` or `rejected_claims` list. The source text matches the diagnostic's SHA-256 (`1d964b…`); the older default run reports a different document hash (`e8d100…`). These examples therefore diagnose candidate behavior on matching *passages*, not a controlled same-input benchmark. The model graph is a locator for plausible missing edges, not ground truth.

## 1. Coordinated correlations lose their shared biological subject — P0

**Results source:** “The TINCR expression level was reversely correlated to serosal invasion (p = 0.001), lymph metastasis (p = 0.037), and tumour node metastasis (TNM) classification (p = 0.016), while positively correlated with differentiation degree (p = 0.017).”

**Intended triples:** `TINCR expression level → inversely_correlated_with → serosal invasion / lymph metastasis / TNM classification`; `TINCR expression level → positively_correlated_with → differentiation degree`. Each p-value qualifies its matching relation.

**Default output:** Accepted claims 0–3 are only `p → equals → [number]`. Accepted 143 is `positively → correlated_with → differentiation degree`, losing TINCR as subject. Rejected 103 uses `next` as subject; rejected 104 attaches TNM classification as subject of the positive differentiation correlation. Diagnostic claims 137, 139, 141, and 143 recover the four biological edges.

**Candidate-generation fix:** In `extract.py`'s clause/relation-frame construction, expand coordinated objects under one relation and carry the explicit subject across `while` into the second relation. Parse parenthetical p-values as relation qualifiers after edge construction so they do not displace the biological candidate.

## 2. Perturbation contrasts and “opposite effects” leave no usable functional edges — P0

**Results source:** “Stable ectopic expression of TINCR decreased not only proliferation ... but also the migration ... of RKO and LoVo cells. In contrast, knockdown of TINCR in HCT116 and SW480 cells had the opposite effects.”

**Intended triples:** `TINCR ectopic expression → decreases → proliferation / migration` in RKO and LoVo cells; `TINCR knockdown → increases → proliferation / migration` in HCT116 and SW480 cells. The cell lines are conditions or scoped outcome entities.

**Default output:** No accepted candidate from either sentence. Rejected 111–113 turn the first object into “not only proliferation (p < 0.001”, `Figure 2A`, or `Supplementary Figure S2C` and label factual *decrease* as negative polarity. Rejected 114–115 capture `SW480 cells → has → opposite` and `opposite → effects → p = 0.001`. Diagnostic 174–177 and 181–184 recover the eight scoped findings.

**Candidate-generation fix:** Strip figure and p-value parentheticals before argument boundaries, distribute the paired outcomes and cell-line list, and resolve “opposite effects” against the preceding intervention/outcome pair. Keep a positive assertion polarity for “decreased”; negative polarity should mark negated assertions, not directional biology.

## 3. Negation scope and intervention identity are lost across “but” — P0

**Results source:** “Knockdown of TINCR did not change the EpCAM mRNA but downregulated the EpCAM protein levels in CRC cells (Figure 4C and 4D).”

**Intended triples:** `TINCR knockdown → changed → EpCAM mRNA` with **negative polarity**; `TINCR knockdown → downregulated → EpCAM protein levels` with **positive polarity**, both in CRC cells.

**Default output:** Accepted 100 is `TINCR → downregulated → EpCAM protein levels in CRC cells`, dropping the knockdown intervention. There is no candidate for the unchanged mRNA result. Diagnostic 273–274 retains both the intervention and separate polarity scopes.

**Candidate-generation fix:** Split coordinated predicates at `but` while inheriting the complete nominalized intervention subject. Apply `did not` only to `change EpCAM mRNA`, then emit the positive protein decrease separately. Represent an observed decrease as a positive fact about direction.

## 4. Rescue experiments are dropped when the effect is anaphoric — P1

**Results source:** “The overexpression of psen2 ... upregulated the expression of EpICD and reduced the expression of EpCAM ... However, all these effects disappeared when TINCR was re-expressed in HCT116 NC or sh-TINCR cells.”

**Intended triples:** `TINCR re-expression → abolishes → the EpICD increase`; `TINCR re-expression → abolishes → the EpCAM decrease`, scoped to the stated HCT116 groups. These edges capture the rescue of the preceding mechanistic phenotype.

**Default output:** No accepted candidate for the rescue sentence. Rejected 76–78 instead say `EpICD → re_expressed_in → HCT116 NC or sh-TINCR cells / figure-line fragments`, assigning re-expression to the wrong entity. Diagnostic 284–287 reconstruct the two rescued outcomes for both groups.

**Candidate-generation fix:** For `these effects disappeared when ...` patterns, resolve the anaphor to immediately preceding changed outcomes, make the `when` intervention the causal subject, and produce one reversal edge per outcome. Preserve the experimental group as condition, not as the object of re-expression.

## 5. Reporting verbs and nested passive mechanisms hide the Sp1–c-Myc chain — P1

**Results source:** “We confirmed that sp1 bound to the promoter of TINCR and slightly positively regulated the promoter activity.” Later: “the increasing expression of TINCR by Sp1 was partly suppressed by c-Myc.”

**Intended triples:** `Sp1 → binds → TINCR promoter`; `Sp1 → positively_regulates → TINCR promoter activity`; `c-Myc → partly_suppresses → Sp1-induced TINCR expression`.

**Default output:** Neither quoted sentence yields an accepted claim. Rejected 147 makes `genes that → confirmed → [whole subordinate clause]`; rejected 89–90 make `Moreover → increas → TINCR expression` and reverse the passive suppression into `TINCR expression by Sp1 → suppresses → c-Myc`. The default graph does contain a Sp1-promoter binding edge from a *different* sentence (accepted 122), so the missing functions here are promoter regulation and c-Myc suppression of the Sp1-induced increase. Diagnostic 455–456 and 362 capture all three quoted relations.

**Candidate-generation fix:** Unwrap reporting complements (`we confirmed that ...`) before relation parsing; split the two coordinated biological predicates; and normalize event nominals/passives (`increase ... by Sp1 was suppressed by c-Myc`) into agent → action → affected event, retaining “partly.”

## Recommended order

1. **P0 — Repair clause argument boundaries and coordinated expansion** in candidate generation, with figure citations/statistics removed from entity spans but retained as qualifiers. This addresses gaps 1–3 and the repeated figure-reference objects.
2. **P0 — Separate assertion polarity from biological direction**, and scope negation per predicate. This prevents the decrease/knockdown errors in gaps 2–3.
3. **P1 — Add short-range event and intervention coreference**, including “opposite effects” and “these effects,” then normalize passive event phrases. This addresses gaps 2, 4, and 5.

Use the source sentences above as focused regression fixtures. Assert the intended edges, intervention identity, polarity, and conditions; also assert that p-values, figure labels, discourse markers, and reporting verbs do not become biological entities.

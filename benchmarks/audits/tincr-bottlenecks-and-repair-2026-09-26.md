# TINCR: missing findings and bounded repair

The last whole-paper measurement remains **54.3% complete-claim precision**
(150/276) and **51.1% complete Results recall** (45/88). These are development
scores on one paper. The diagnostic below is not a replacement full-paper score.

## What is missing

- The original Jev-only Results audit had 39 partial findings and six wholly
  missing findings. Most losses involve cell/organism identity, experimental arm,
  comparator, mechanism, hedging, attribution, or incorrect actor boundaries.
- The one-call Luna repair inspected 2,378 characters of the paper, roughly 9%,
  and could propose at most 24 claims. This cannot repair coverage across the
  entire paper.
- Production selection still defaults to forced choice (`allow_reject=False`).
  Generating more permutations does not supply missing experimental context.
- Support verification alone is permissive toward incomplete graph records.
  Merely moving evidence into each question or strengthening a broad support
  prompt did not produce a decisive gain on the 26-case diagnostic.

## Two implementation faults corrected

1. **Effect direction confused with logical negation.** Four cached Luna claims
   used inhibitory predicates with `polarity=negative`. That negates the entire
   proposition: `represses` + negative means *does not repress*. The earlier
   report incorrectly blamed Jev for rejecting the c-Myc claims. The generator
   prompt now defines this explicitly. A small Jev Choice pass checks generated
   negative labels against source evidence before regular verification. Its
   choices mean asserted, explicitly denied, or neither; generic positive/negative
   labels alone failed this diagnostic. Decisions are saved in benchmark output.
2. **Independent findings suppressed by replacement selection.** Every proposal
   overlapping a flagged baseline was marked consumed; only one chosen replacement
   survived. Four of 15 cached proposals never reached verification. All distinct
   proposals now reach verification. Replacement choice still controls whether
   the old baseline is removed. This preserves candidate availability, and does
   not establish that every proposal is accurate.

The generator prompt also now explicitly requires material experimental context
in claim fields. Its effect has not been measured with a fresh Luna generation.

## Bounded live evidence

Cached proposals only; no new Luna/OpenAI generation.

- Dedicated polarity decision: **4/4 inhibitory assertions corrected**.
- Synthetic explicit-denial controls: **2/2 retained as negative**.
- All four corrected inhibitory assertions passed ordinary Jev verification;
  c-Myc repression scored 0.93 support and partial suppression scored 0.92.
- Successful replay: two Jev requests, 6,501 input / 807 output tokens.
- Entire investigation including failed request-layout and generic-choice probes:
  seven Jev requests, 47,371 input / 4,514 output tokens; zero Luna calls.
- Seven focused offline repair checks, response validation, compilation and diff
  whitespace checks passed.

The polarity repair does **not** supply missing conditions. For example, the
rescued c-Myc repression record still lacks the CRC-cell condition required by
R079. No full-paper precision/recall improvement is claimed from this replay.
New proposal admission can admit additional incomplete claims through the
existing permissive verifier; those need the same completeness audit.

## Next substantive experiment

Use one bounded Luna pass across the full Results section to produce compact
finding records with explicitly attached cell/organism, intervention, comparator,
outcome, modality, negation, and evidence IDs. Reuse context records to reduce
output tokens, then deterministically attach their fields to each graph claim.
Jev should judge narrowly scoped assertion, actor, target, and context decisions.
Track every source passage as covered, excluded with a reason, or unresolved.
Compare this alternative with the unchanged full-paper score before changing
extraction defaults. More random triple combinations alone cannot fix these losses.

Artifacts: `out/tincr-verifier-layout-probe.json`,
`out/tincr-luna-polarity-replay-generic-choice.json`,
`out/tincr-luna-polarity-replay.json`. The first artifact includes a label correction:
its two c-Myc controls initially overlooked their erroneous negative polarity;
recorded model responses were not changed.

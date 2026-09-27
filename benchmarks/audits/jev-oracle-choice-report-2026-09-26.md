# Jev complete-interpretation Choice diagnostic

This is **oracle-assisted development evidence**, not production accuracy or a
held-out release score. The audited complete interpretation was supplied in
10 of 12 packets; two packets contained no complete option. JevyGraph still
has to generate complete alternatives on its own.

The [packet file](jev-oracle-choice-packets-2026-09-26.json) was source- and
span-checked before the request (SHA-256
`3e40da6ffdbd8849546e94e597ffb45aa3eb10a5cae7f04a6598e9cea041fab4`).
An independent Codex packet review found one initially invalid rejection
label and four excerpts missing needed context; those were corrected before
this run. The [representation and conflict policy](jev-oracle-choice-policy-2026-09-26.md)
was frozen before scoring. Jev received only source excerpts and shuffled
eight-field alternatives. Labels, rationales, error types, and packet IDs
were absent from the model payload. The prompt was not tuned after the run.

One Jev Choice request selected **12/12 audited answers**: 10 complete
interpretations and both `reject` cases. Usage was **7,124 input tokens**,
**663 output tokens**, and **18,855 request bytes**. The exact result is
`out/jev-oracle-choice-live-2026-09-26.json`; the reproducible runner is
`scripts/probe_oracle_choice.py` and requires `--live` for a paid call.

| Packet | Error tested | Result | Chosen probability |
| --- | --- | --- | ---: |
| Group versus pairwise comparison | Unasserted cell-line pair | Correct | 1.00 |
| Control actor and negation | Wrong organ/group/polarity | Correct | 0.92 |
| mRNA negation | Protein versus mRNA and polarity | Correct | 0.89 |
| Hedged cleavage | `may` versus observed fact | Correct | 0.99 |
| PSEN2 arms | Separate versus required joint intervention | Correct | 0.97 |
| Prior-study attribution | Cited result versus this study | Correct | 0.99 |
| Tissue comparator | Wrong comparator and target | Correct | 0.99 |
| Correlation, no correct option | Wrong direction, cohort, or target | Rejected | 0.90 |
| RKO perturbation | Wrong intervention, cell line, or statistic | Correct | 0.93 |
| Presidential term | Wrong date or term-year anchor | Correct | 0.99 |
| Double vacancy | Wrong actor, modality, or same-cause restriction | Correct | 0.89 |
| Joint declaration, no correct option | Wrong actor, recipient, or assertion | Rejected | 0.75 |

## Comparison with standalone verification

The [cached full-paper precision audit](tincr-discovery-precision-2026-09-26.json)
found that standalone Jev verification accepted all 302 Results proposals,
including 15 materially unsupported ones. Its unsupported
LoVo-versus-HCT116 pairwise proposal received support 0.80 and was accepted;
a later whole-claim support question scored it 0.73. In this Choice packet,
Jev chose the complete **group-level** comparison over a similarly framed
pairwise alternative. The exact option text and source context differed, so
this is an architectural clue, not a controlled paired improvement estimate.
Most other cached proposal indices attached to packets were previously
complete-supported claims; they are not evidence that Choice repaired a
previously failed verification decision. The existing 19-deficient/19-control
whole-claim probe still shows high support for some split causal and rescue-arm
errors. No new standalone verification request was made here.

## Decision

On these selected passages, Jev **can** distinguish a complete, qualified
interpretation when it is explicitly supplied alongside plausible wrong ones,
including two cases requiring rejection. This warrants testing an upstream
proposer that assembles complete alternatives for a finding. It does **not**
justify promoting the current parser, merging partial records without explicit
event/context links, trusting standalone support scores, or changing defaults.
The next engineering task should be bounded around complete alternative
generation and explicit qualifier attachment, then tested on untouched
documents. Source-local conflicts remain a separate flag, not automatic
extraction errors. The 95% precision/recall release requirement is unproven.

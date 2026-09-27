# TAp73 untouched pipeline trace

## Stage totals

| Stage | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Frozen source claims present | 37 | 37 | 37 |
| Deterministic frames | 90 | 90 | 90 |
| Candidate options | 1,680 | 1,680 | 1,680 |
| Exact complete gold options | 0 | 0 | 0 |
| Jev abstentions | 35 | 35 | 36 |
| Jev resolved | 55 | 55 | 54 |
| Final accepted | 10 | 9 | 9 |
| Reviewed complete gold | 6 | 5 | 6 |

All 37 expected claims are present in the converted source. Every claim first
becomes unrecoverable during deterministic candidate generation. Jev cannot
select a complete claim that was never offered.

Eighty-nine of 90 frame evidence strings occur exactly in the source; the IC50
sentence normalizes the micro sign from `µ` to `μ`. Stored character offsets
also drift by 1–9 characters because blank-line cleanup does not preserve an
offset map. These did not cause the recall loss, but they are separate
provenance defects.

## Root cause

The scientific event assembler emitted **zero event frames**. The document fell
through to 77 generic `open_verb`, 7 `modal`, and 6 `pattern` frames. That parser
treated reporting phrases, nominalized results, anaphora, parenthetical figure
references, and coordinated genes as ordinary local subject–verb–object syntax.

Jev correctly abstained on about 39% of frames. Of the remaining selections,
the deterministic filter rejected 45–46 per run, mainly for low support. The
filter prevented many malformed frames from leaking but could not reconstruct
the missing actors, conditions, comparisons, or coordinated outcomes.

## Final precision errors

Each run retained the incorrect heading claim `BMECs → induce → ferroptosis`,
although the Results prose says BMECs *undergo* ferroptosis. Each run also kept
`BMECs → undergo → ferroptosis` without its material RSL3 induction condition.

## Claim-by-claim first loss

| Gold | Primary cause | Closest offered option | Final runs | Trace |
|---|---|---|---|---|
| P001 | relation_schema | To investigate whether TAp73 → regulates → BMECs | missing/missing/missing | The canonical-target apposition was parsed as a quantify action; target direction was never offered. |
| P002 | reporting_wrapper | Our findings → revealed → significantly | missing/missing/missing | The parser kept ‘Our findings’ as the actor instead of TAp73 ectopic expression. |
| P003 | nominalized_result | results → decreases_activity_of → cell growth | missing/missing/missing | The decrease was kept as a noun phrase and the TAp73 intervention was not promoted to subject. |
| P004 | inference_attachment | results → inhibits → cell growth | missing/missing/missing | The inferred growth effect was attached to ‘results’ rather than TAp73 overexpression. |
| P005 | nominalized_result | Similarly, the EdU assay, which measures DNA synthesis as an indicator of cell proliferation → showed → significant reduction in the number | missing/missing/missing | The reduction and its cause were split into malformed reduction/proliferate frames. |
| P006 | qualifier_boundary | significant reduction in the number → supports → role of TAp73 | complete/missing/complete | A role-of-TAp73 frame existed, but BMEC context and canonical predicate boundaries were absent. |
| P007 | coordination | significant reduction in the number → supports → role of TAp73 | complete/complete/complete | The coordinated cell-cycle/proliferation conclusion was not emitted as two complete TAp73 claims. |
| P008 | anaphora | significant reduction in the number → supports → role of TAp73 | missing/missing/missing | The pronoun ‘its’ was not resolved to TAp73 and potential modality was not preserved. |
| P009 | parenthetical_interruption | Figure 2A → reduces → p21 expression (p < 0.05 | missing/missing/missing | Figure and p-value parentheses displaced TAp73 silencing; Figure 2A became the subject. |
| P010 | inherited_subject | significant increase in the number → modulate → cell cycle progression | missing/missing/missing | The participial consequence inherited Figure 2B rather than TAp73 silencing as its actor. |
| P011 | nominalized_result | colony formation assay → showed → substantial increase in colony numbers in TAp73 knockdown cells | missing/missing/missing | The increase and comparison remained noun/comparison fragments without the knockdown actor. |
| P012 | inference_attachment | colony formation assay → promotes → cell growth | missing/missing/missing | Promoted growth was attributed to the assay instead of TAp73 knockdown. |
| P013 | nominalized_result | Similarly → demonstrated → significant increase in the number | complete/complete/complete | The increase in proliferating cells was split at ‘proliferating’ and lost the intervention actor. |
| P014 | apposition | To explore the potential for ferroptosis in BMECs → treated → inducer | missing/missing/missing | RSL3’s appositive inducer type was treated as part of a treatment procedure. |
| P015 | reporting_wrapper | Our results → demonstrated → dose-dependent increase in cell death following RSL3 treatment | missing/missing/missing | ‘Our results’ remained the actor of a nominal increase instead of RSL3 treatment. |
| P016 | qualifier_boundary | Notably → led_to → significant | complete/complete/complete | A useful LDH frame survived, but the canonical increase relation and BMEC condition were absent. |
| P017 | quantity_relation | IC50 value for RSL3 in BMECs → correspond → dose-dependent accumulation of reactive oxygen species (ROS) within the cells | missing/missing/missing | The whole IC50 noun phrase became the subject and ‘calculated to’ became the predicate. |
| P018 | cross_sentence_attachment | IC50 value for RSL3 in BMECs → correspond → dose-dependent accumulation of reactive oxygen species (ROS) within the cells | missing/missing/missing | ‘Corresponding’ inherited the preceding IC50 subject instead of RSL3 treatment. |
| P019 | condition_attachment | IC50 value for RSL3 in BMECs → correspond → dose-dependent accumulation of reactive oxygen species (ROS) within the cells | missing/missing/missing | The RSL3 inducer was separated from the undergo-ferroptosis assertion. |
| P020 | coordination_anaphora | Additionally → assessed → expression | missing/missing/missing | The shared phrase ‘their expression’ was not expanded to PTGS2 with the RSL3 actor. |
| P021 | coordination_anaphora | Additionally → assessed → expression | missing/missing/missing | The shared phrase ‘their expression’ was not expanded to TRFC with the RSL3 actor. |
| P022 | cross_sentence_antecedent | TRFC → undergo → ferroptosis | missing/missing/missing | The previous gene TRFC was incorrectly carried forward as the ferroptosis actor. |
| P023 | reporting_coordination | Our findings → revealed → significantly | missing/missing/missing | ‘Our findings’ remained the actor and PTGS2/TRFC stayed in one compound object. |
| P024 | reporting_coordination | Our findings → revealed → significantly | missing/missing/missing | ‘Our findings’ remained the actor and PTGS2/TRFC stayed in one compound object. |
| P025 | relative_clause_coordination | Our findings → revealed → significantly | missing/missing/missing | The relative clause resolved only to TRFC; PTGS2 was dropped. |
| P026 | relative_clause_boundary | Our findings → revealed → significantly | complete/complete/complete | Jev recovered a usable TRFC reading, but the deterministic option retained extra relative-clause text. |
| P027 | discourse_anaphora | To explore whether TAp73 → regulates → ferroptosis in BMECs | missing/missing/missing | Sentence-initial ‘This’ was not resolved to TAp73 and ‘might’ was lost. |
| P028 | converse_anaphora | Conversely → marked → decrease in the expression levels of PTGS2 | missing/missing/missing | ‘Conversely’ did not inherit TAp73 knockdown and the coordinated genes were fragmented. |
| P029 | converse_anaphora | Conversely → marked → decrease in the expression levels of PTGS2 | missing/missing/missing | ‘Conversely’ did not inherit TAp73 knockdown and the coordinated genes were fragmented. |
| P030 | inference_attachment | Conversely → marked → decrease in the expression levels of PTGS2 | missing/missing/missing | The indicating clause inherited a figure fragment instead of TAp73 knockdown. |
| P031 | reporting_wrapper | results → demonstrated → significantly | missing/missing/missing | ‘The results’ remained the actor of attenuated ferroptosis. |
| P032 | reporting_wrapper | results → reduces → cell death | missing/missing/missing | ‘The results’ remained the actor of reduced cell death. |
| P033 | reporting_coordination | results → demonstrated → significantly | missing/missing/missing | ‘The results’ remained the actor and ROS was split from its decrease relation. |
| P034 | discourse_anaphora | BMECs with the ferroptosis inducer RSL3 while simultaneously → indicates → knockdown | missing/missing/missing | ‘This’ resolved to a treatment phrase instead of TAp73 knockdown. |
| P035 | coordination | BMECs with the ferroptosis inducer RSL3 while simultaneously → indicates → knockdown | missing/missing/missing | Oxidative stress and cellular damage were not split under the same knockdown actor. |
| P036 | attachment | cellular damage typically → decreased → lipid peroxidation | missing/missing/missing | Decreased lipid peroxidation inherited ‘cellular damage’ rather than TAp73 knockdown. |
| P037 | nominal_subject_boundary | Further → supports → role of TAp73 | complete/complete/complete | A role-of-TAp73 frame was semantically recoverable, but its canonical actor, predicate, and BMEC condition were not a complete option. |

The complete machine-readable frame, option, Jev decision, verification-score,
filter, and final-output lineage is saved in `out/tap73-pipeline-lineage.json`.

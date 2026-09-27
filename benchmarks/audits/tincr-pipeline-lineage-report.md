# TINCR Results: end-to-end information lineage

This audit replays no models. It joins the exact deterministic frames and options from the frozen run to Jev's selections, verification scores, final filter decisions, human reviews, and the completion experiment.

## Stage totals

- Gold claims: **88**
- Results frames: **185**; offered options: **2702**
- Deterministic complete options: **47**; partial options: **41**
- Baseline complete recall: **43/88 (48.9%)**
- Completion-gated recall: **45/88 (51.1%)**
- Baseline complete precision: **81/130 (62.3%)**
- Completion-gated precision: **84/124 (67.7%)**

## Where information changed

### Deterministic candidate status → baseline recall status

| Transition | Claims |
|---|---:|
| complete -> complete | 43 |
| complete -> partial | 4 |
| partial -> missing | 6 |
| partial -> partial | 35 |

### Baseline recall status → completion-gated status

| Transition | Claims |
|---|---:|
| complete -> complete | 43 |
| missing -> missing | 6 |
| partial -> complete | 2 |
| partial -> partial | 37 |

### Jev selection on each gold claim's audited candidate frame

| Selection result | Claims |
|---|---:|
| different_option_selected | 14 |
| gold_ledger_option_selected | 73 |
| no_resolved_selection_for_ledger_frame | 1 |

### First still-unrecovered loss

| Stage | Claims |
|---|---:|
| deterministic_claim_assembly | 39 |
| deterministic_ledger_overcredit_or_gold_granularity | 4 |
| none_finally_complete | 45 |

### Baseline human verdict → completion action

| Transition | Outputs |
|---|---:|
| complete_supported -> dropped_or_replaced | 1 |
| complete_supported -> retained | 80 |
| incomplete_or_wrong_qualifier -> dropped_or_replaced | 4 |
| incomplete_or_wrong_qualifier -> retained | 10 |
| unsupported -> dropped_or_replaced | 3 |
| wrong_boundary_or_relation -> dropped_or_replaced | 2 |
| wrong_boundary_or_relation -> retained | 30 |

## What the trace says

- Candidate assembly is labeled partial for **41/88** gold claims before Jev chooses anything. The consistency join found another **4** overcredited as complete, because their offered condition omits a qualifier required by the gold record.
- Those overcredits are **R015, R016, R017, R018**. After applying the recall audit consistently, only **43/88** deterministic candidates are complete.
- Jev chose the audited gold option for **73/88** claims and chose a different option on that frame for **14/88**.
- No strict complete-candidate recall loss was caused by Jev choosing a different option. The one complete record with a different choice, R063, remained complete. R092 had no resolved output from the ledger frame but was recovered completely by another frame.
- The baseline verifier accepted **32** wrong-boundary/relation outputs, **14** qualifier errors, and **3** unsupported outputs. All 45 rejected Results candidates were rejected for low support.
- Verifier support does not cleanly separate valid and invalid claims: the unsupported accepted outputs scored **0.72–0.77** support, while complete outputs ranged from **0.46–0.96**.
- The completion layer proposed **16** claims; **4** passed every Jev completeness dimension, and only **2** previously incomplete gold claims became complete.
- The recovered gold claims were: **R058, R071**.

## Every gold claim

| Gold | Candidate | Jev selection | Baseline | Final | First unrecovered loss | Gap |
|---|---|---|---|---|---|---|
| R001 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R002 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | qRT-PCR is made the actor; the accepted claim omits the paired non-tumour comparator … |
| R003 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | CRC cohort qualifier is absent from the tumour-sample condition. |
| R004 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | CRC cohort qualifier is absent from the tumour-sample condition. |
| R005 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | CRC cohort qualifier is absent from the tumour-sample condition. |
| R006 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | CRC cohort qualifier is absent from the tumour-sample condition. |
| R007 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R008 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | Mainly qualifier is lost and HCT116 is embedded in the location object rather than re… |
| R009 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | SW480 location is absent; the accepted claim names HCT116 only. |
| R010 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | Correlation with broad CRC progression does not preserve the suggested association wi… |
| R011 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R012 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R013 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R014 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R015 | complete | gold_ledger_option_selected | partial | partial | deterministic_ledger_overcredit_or_gold_granularity | The HCT116 increase is retained, but the comparison with the opposite overexpression … |
| R016 | complete | gold_ledger_option_selected | partial | partial | deterministic_ledger_overcredit_or_gold_granularity | The SW480 increase is retained, but the comparison with the opposite overexpression e… |
| R017 | complete | gold_ledger_option_selected | partial | partial | deterministic_ledger_overcredit_or_gold_granularity | The HCT116 increase is retained, but the comparison with the opposite overexpression … |
| R018 | complete | gold_ledger_option_selected | partial | partial | deterministic_ledger_overcredit_or_gold_granularity | The SW480 increase is retained, but the comparison with the opposite overexpression e… |
| R019 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R020 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R021 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | The accepted actor is only “from sh-TINCR cells”; xenograft tumours and the control c… |
| R022 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R023 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The actor “these mice” does not identify the HCT116-shTINCR group in claim fields. |
| R024 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R025 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | A positive liver-foci claim for 4/5 study mice cannot express the negative 0/5 contro… |
| R026 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R027 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R028 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | The accepted actor includes prefatory text and the adverb “profoundly”; it is not a c… |
| R029 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The accepted actor includes the adverb “profoundly”; it is not a clean TINCR-loss ent… |
| R030 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The actor includes “significantly” and the measured fraction has an unclosed parenthe… |
| R031 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | The accepted actor is the preceding G0/G1 fraction, not TINCR downregulation in HCT11… |
| R032 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R033 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R034 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R035 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R036 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R037 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R038 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R039 | partial | gold_ledger_option_selected | missing | missing | deterministic_claim_assembly | No accepted claim links TINCR-induced arrest and apoptosis to growth inhibition. |
| R040 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | EpCAM is made the actor and “genes” the target; TINCR depletion, gene expression, and… |
| R042 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R043 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R044 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R045 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R046 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R047 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The EpICD increase is present, but the CRC-cell condition is missing. |
| R048 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R049 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R050 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R051 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R052 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | TINCR re-expression is recorded, but its reversal of the PSEN2-associated EpICD incre… |
| R053 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R054 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R055 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | Generic TINCR regulation of proteolysis lacks inhibition, accelerated EpCAM cleavage,… |
| R056 | partial | different_option_selected | missing | missing | deterministic_claim_assembly | No accepted claim represents tentative EpICD release after TINCR inhibition; the EpIC… |
| R057 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R058 | partial | different_option_selected | partial | complete |  | Malformed “EpICD related_in expression” does not encode an inverse TINCR–EpICD correl… |
| R059 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R060 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R061 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R062 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R063 | complete | different_option_selected | complete | complete |  |  |
| R064 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R065 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R066 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The target increase is retained, but CRC identity of the TINCR-knockdown cells is abs… |
| R067 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The target increase is retained, but CRC identity of the TINCR-knockdown cells is abs… |
| R068 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The target increase is retained, but CRC identity of the TINCR-knockdown cells is abs… |
| R069 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R070 | partial | different_option_selected | partial | partial | deterministic_claim_assembly | EpICD–β-catenin complex formation is present, but no TINCR-knockdown promotion or Co-… |
| R071 | partial | different_option_selected | partial | complete |  | A predicted TINCR-promoter site is alluded to, but Sp1, one-site scope, and combined … |
| R072 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | Malformed actor “obvious” and target “Sp1-binding activity” do not cleanly encode Sp1… |
| R073 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R074 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R075 | complete | gold_ledger_option_selected | complete | complete |  |  |
| R076 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | Binding direction is reversible, but c-Myc central-region mechanism and prior-report … |
| R077 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | The inhibition is present, but c-Myc–Sp1 binding mechanism and prior-report attributi… |
| R078 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | Passive transcription relation is present, but CRC-cell condition is absent. |
| R079 | partial | gold_ledger_option_selected | missing | missing | deterministic_claim_assembly | No accepted claim asserts c-Myc repression of TINCR expression. |
| R080 | partial | different_option_selected | missing | missing | deterministic_claim_assembly | No accepted claim asserts partial c-Myc suppression of Sp1-induced TINCR expression. |
| R081 | partial | different_option_selected | missing | missing | deterministic_claim_assembly | No accepted claim represents the tentative mediation of TINCR-induced cell-cycle arre… |
| R082 | partial | gold_ledger_option_selected | missing | missing | deterministic_claim_assembly | No accepted claim represents the tentative mediation of TINCR-induced proliferation i… |
| R083 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | Generic positive feedback loop omits the TINCR–c-Myc participants, reciprocal mechani… |
| R084 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | Generic positive feedback loop omits the TINCR–c-Myc participants, reciprocal mechani… |
| R087 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | EpCAM regulation is present, but the proposed reciprocal TINCR–EpCAM model and propos… |
| R088 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | EpCAM regulation is present, but the proposed reciprocal TINCR–EpCAM model and propos… |
| R089 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | EpCAM regulation is present, but the proposed reciprocal TINCR–EpCAM model and propos… |
| R090 | partial | gold_ledger_option_selected | partial | partial | deterministic_claim_assembly | TINCR re-expression is recorded, but its reversal of the PSEN2-associated EpCAM decre… |
| R092 | complete | no_resolved_selection_for_ledger_frame | complete | complete |  |  |

## Detailed artifacts

- Machine-readable frames, every offered option, Jev selections, verification scores, filters, completion actions, and gold flows: `out/tincr-pipeline-lineage.json`
- One row per gold claim: `out/tincr-gold-lineage.csv`
- One row per selected and verified Results output: `out/tincr-output-lineage.csv`

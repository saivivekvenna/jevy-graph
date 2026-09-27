# Candidate coverage: original Constitution, Article I §§4–9

Local-only audit of the six 2026-09-27 reviewed fixtures. I ran `extract_frames(fixture["text"])` and enumerated every `_triple_options(frame)` with `PYTHONPATH=src`. No Jev or external API call was made. Frame/option indices below are zero-based within each section.

**Decision rule.** `M` means one offered option preserves the gold actor, relation, object, polarity, modality, and every material condition or exception. Equivalent wording counts. An unambiguous deictic term may be resolved from frame context (for example, “thereof” in §8 coin value). Evidence text alone does not repair a missing qualifier, wrong actor, or copied condition. A conjunction that only *contains* an atomic gold assertion is not an equivalent atomic triple. `G` means no complete offered option.

| Unit | Gold | Frames | Offered options | M | G | Coverage |
|---|---:|---:|---:|---:|---:|---:|
| Article I §4 | 9 | 5 | 56 | **0** | 9 | 0.0% |
| Article I §5 | 18 | 13 | 180 | **3** | 15 | 16.7% |
| Article I §6 | 18 | 10 | 233 | **1** | 17 | 5.6% |
| Article I §7 | 33 | 38 | 603 | **1** | 32 | 3.0% |
| Article I §8 | 76 | 42 | 160 | **19** | 57 | 25.0% |
| Article I §9 | 40 | 14 | 290 | **0** | 40 | 0.0% |
| **Total** | **194** | **122** | **1,522** | **24** | **170** | **12.4%** |

## Main failure patterns

1. **Wrong actor or relation:** §4 has no Legislature-prescribes edge; §5 substitutes `type` or `determines` for judgment, punishment, and expulsion; §6 gives arrest privilege to “Breach of the Peace”; §7 gives veto and override actions to the Bill or Objections; §9 loses the regulated actor in vessel and tax rules.
2. **Missing legal limits:** §8 tax options omit the debts/defence/welfare purpose, militia government loses federal-service scope, and the district power loses cession, acceptance, area, and seat requirements. §6 appointment options omit created/increased-office timing. §7 options omit most veto thresholds and ten-day conditions.
3. **Cross-clause condition leakage:** §4 annual assembly carries the meeting-date exception; §6 speech/debate carries the arrest exception; §9 nobility carries the separate foreign-emoluments consent exception.
4. **Joined alternatives and clipped objects:** §8 combines Weights/Measures, domestic/foreign coin value, piracy/felony actions, land/water captures, and land/naval-force rules. The available options do not provide each separate gold relation. §7 Senate amendment options omit the revenue-Bill target.
5. **Absent frames:** no complete §9 Habeas, bill-of-attainder, ex-post-facto, Treasury-appropriation, or foreign-emoluments claim; no §8 uniform-duty, army-appropriation, State militia-reservation, enclave, or necessary/proper claim.

## Decision ledger

Each row records one gold ID. `f/o` cites an actually offered option for a match; gap notes identify the decisive defect.

### Article I §4 — 0/9

| Gold ID | Result | Option or decisive defect |
|---|---|---|
| `i4-states-prescribe-election-times` | G | f0–1 misassign subject to Manner/Representatives; State Legislature prescription absent. |
| `i4-states-prescribe-election-places` | G | f0–1 misassign subject to Manner/Representatives; State Legislature prescription absent. |
| `i4-states-prescribe-election-manner` | G | f0–1 misassign subject to Manner/Representatives; State Legislature prescription absent. |
| `i4-congress-make-regulations` | G | f2 has Representatives choosing Senators; Congress make/alter power and exception absent. |
| `i4-congress-alter-regulations` | G | f2 has Representatives choosing Senators; Congress make/alter power and exception absent. |
| `i4-congress-senate-places-exception` | G | f2 has Representatives choosing Senators; Congress make/alter power and exception absent. |
| `i4-annual-assembly` | G | f3/o3 has annual frequency but wrongly inherits different-day exception. |
| `i4-default-meeting-day` | G | f3 only says assemble_at; no meeting-on-date edge. |
| `i4-alternative-meeting-day` | G | f4/o0 lacks may/by Law and carries self-referential exception. |

### Article I §5 — 3/18

| Gold ID | Result | Option or decisive defect |
|---|---|---|
| `i5-judge-elections` | G | f0–2 offer House/type/Judge fragments; own-Members object missing. |
| `i5-judge-returns` | G | f0–2 offer House/type/Judge fragments; own-Members object missing. |
| `i5-judge-qualifications` | G | f0–2 offer House/type/Judge fragments; own-Members object missing. |
| `i5-majority-quorum` | M | f5/o0 |
| `i5-small-number-adjourn` | G | f6 has no smaller-number adjournment edge. |
| `i5-small-number-compel` | G | f6 makes Majority the actor; smaller number and authorization absent. |
| `i5-house-compulsion-manner` | G | f6 omits each House providing manner or penalties. |
| `i5-house-compulsion-penalties` | G | f6 omits each House providing manner or penalties. |
| `i5-proceeding-rules` | M | f7/o2 |
| `i5-disorderly-punishment` | G | f7 only determines Rules; punishment/expulsion action and threshold absent. |
| `i5-expulsion` | G | f7 only determines Rules; punishment/expulsion action and threshold absent. |
| `i5-keep-journal` | M | f8/o0 |
| `i5-publish-journal` | G | f9 uses keep rather than publish; timing and secrecy exception absent. |
| `i5-journal-secrecy` | G | f10/o0 clips “require Secrecy”; f11 changes actor. |
| `i5-yeas-journal` | G | f12 makes House entered_on Journal; yeas/nays and one-fifth request absent. |
| `i5-nays-journal` | G | f12 makes House entered_on Journal; yeas/nays and one-fifth request absent. |
| `i5-no-long-adjourn` | G | No frame for either House’s consent-limited adjournment prohibition. |
| `i5-no-other-place-adjourn` | G | No frame for either House’s consent-limited adjournment prohibition. |

### Article I §6 — 1/18

| Gold ID | Result | Option or decisive defect |
|---|---|---|
| `i6-senators-compensation` | G | f0 offers Representatives only; Senators absent. |
| `i6-representatives-compensation` | M | f0/o0 |
| `i6-compensation-law` | G | f1 makes Representatives, not Compensation, ascertained by Law. |
| `i6-compensation-treasury` | G | f1 has ascertained_by relation; no paid-out-of-Treasury edge. |
| `i6-senators-arrest-attendance` | G | f2 makes Breach of the Peace the protected actor; member and trip scope absent. |
| `i6-senators-arrest-travel-to` | G | f2 makes Breach of the Peace the protected actor; member and trip scope absent. |
| `i6-senators-arrest-travel-from` | G | f2 makes Breach of the Peace the protected actor; member and trip scope absent. |
| `i6-senators-speech-debate` | G | f4 makes Compensation the actor and copies arrest exception. |
| `i6-senators-created-office` | G | f5 has appointment ban but lacks created/increased-during-elected-term condition. |
| `i6-senators-emoluments-office` | G | f5 has appointment ban but lacks created/increased-during-elected-term condition. |
| `i6-representatives-arrest-attendance` | G | f2 makes Breach of the Peace the protected actor; member and trip scope absent. |
| `i6-representatives-arrest-travel-to` | G | f2 makes Breach of the Peace the protected actor; member and trip scope absent. |
| `i6-representatives-arrest-travel-from` | G | f2 makes Breach of the Peace the protected actor; member and trip scope absent. |
| `i6-representatives-speech-debate` | G | f4 makes Compensation the actor and copies arrest exception. |
| `i6-representatives-created-office` | G | f5 has appointment ban but lacks created/increased-during-elected-term condition. |
| `i6-representatives-emoluments-office` | G | f5 has appointment ban but lacks created/increased-during-elected-term condition. |
| `i6-officeholder-no-senate` | G | f8–9 lack negative Office-holder membership edge and tenure condition. |
| `i6-officeholder-no-house` | G | f8–9 lack negative Office-holder membership edge and tenure condition. |

### Article I §7 — 1/33

| Gold ID | Result | Option or decisive defect |
|---|---|---|
| `i7-revenue-origin` | M | f0/o0 |
| `i7-senate-amend-propose` | G | f1–2 have Senate/Amendments, but omit revenue-Bill target. |
| `i7-senate-amend-concur` | G | f1–2 have Senate/Amendments, but omit revenue-Bill target. |
| `i7-bicameral-pass-house` | G | f3 has Bill/passed/House or Senate, but omits before-presentation/law condition. |
| `i7-bicameral-pass-senate` | G | f3 has Bill/passed/House or Senate, but omits before-presentation/law condition. |
| `i7-present-bill` | G | f4 makes Senate, not passed Bill, presented to President. |
| `i7-president-sign` | G | No President/signs/Bill option. |
| `i7-president-return` | G | f5 makes Bill, not President, return; approval branch/originating House missing. |
| `i7-president-objections` | G | f5 makes Bill, not President, return; approval branch/originating House missing. |
| `i7-origin-house-record-objections` | G | f8 makes Bill enter Objections; originating House absent. |
| `i7-origin-house-reconsider` | G | f7/f9 make Bill the actor; no originating-House reconsideration. |
| `i7-origin-house-two-thirds` | G | f10 makes Objections agree to pass; two-thirds House actor absent. |
| `i7-send-other-house` | G | f11 makes Objections the sender; conditional House sending absent. |
| `i7-send-objections` | G | f11 makes Objections the sender; conditional House sending absent. |
| `i7-other-house-reconsider` | G | f12 makes Objections, not other House, reconsidered. |
| `i7-other-house-two-thirds` | G | f13 makes Objections approved; Bill and second two-thirds gate absent. |
| `i7-override-law` | G | f14 makes Objections become Law; both two-thirds votes absent. |
| `i7-override-yeas-house` | G | f15–16 have wrong direction/object and do not encode both yeas and Nays. |
| `i7-override-yeas-senate` | G | f15–16 have wrong direction/object and do not encode both yeas and Nays. |
| `i7-override-names-for` | G | f19 makes Bill/against Bill entered; names and each-House actor absent. |
| `i7-override-names-against` | G | f19 makes Bill/against Bill entered; names and each-House actor absent. |
| `i7-ten-day-law` | G | f20–27 have no correct Bill→Law edge with ten-day/Sunday/adjournment qualifiers. |
| `i7-pocket-veto` | G | f29 has no options; adjournment-preventing-return branch absent. |
| `i7-order-present` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-order-approval` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-order-repass` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-resolution-present` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-resolution-approval` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-resolution-repass` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-vote-present` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-vote-approval` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-vote-repass` | G | f30–37 misassign House/Effect as actor; category, adjournment exception, approval/repass gates lost. |
| `i7-adjournment-exception` | G | f30–37 offer no negative non-presentation edge for adjournment question. |

### Article I §8 — 19/76

| Gold ID | Result | Option or decisive defect |
|---|---|---|
| `i8-lay-taxes` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-collect-taxes` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-lay-duties` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-collect-duties` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-lay-imposts` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-collect-imposts` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-lay-excises` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-collect-excises` | G | f0–7 encode act and tax kind but omit debts/defence/welfare purpose qualifier. |
| `i8-pay-debts` | G | f8–9 authorize pay/provide directly; omit link to taxing power. |
| `i8-common-defence` | G | f8–9 authorize pay/provide directly; omit link to taxing power. |
| `i8-general-welfare` | G | f8–9 authorize pay/provide directly; omit link to taxing power. |
| `i8-uniform-duties` | G | No uniform-throughout-United-States frame. |
| `i8-uniform-imposts` | G | No uniform-throughout-United-States frame. |
| `i8-uniform-excises` | G | No uniform-throughout-United-States frame. |
| `i8-borrow` | M | f10/o0 |
| `i8-commerce-foreign` | M | f11/o0 |
| `i8-commerce-interstate` | G | f12 says “regulate among/with” but drops Commerce as regulated object. |
| `i8-commerce-tribes` | G | f12 says “regulate among/with” but drops Commerce as regulated object. |
| `i8-naturalization` | M | f13/o0 |
| `i8-bankruptcy` | M | f14/o0 |
| `i8-coin-money` | M | f15/o0 |
| `i8-regulate-us-coin-value` | M | f16/o3 |
| `i8-regulate-foreign-coin-value` | G | f16/o0 joins domestic and foreign value; no atomic foreign-Coin option. |
| `i8-weights-standard` | M | f17/o3 |
| `i8-measures-standard` | G | f17/o0 joins Weights and Measures; no atomic Measures option. |
| `i8-securities-counterfeiting` | G | f18 joins Securities and current Coin; no separate qualified punishment object. |
| `i8-coin-counterfeiting` | G | f18 joins Securities and current Coin; no separate qualified punishment object. |
| `i8-post-offices` | M | f19/o0 |
| `i8-post-roads` | M | f20/o0 |
| `i8-science-progress` | G | f21 drops limited-time exclusive-rights means; Arts is only in joined object. |
| `i8-arts-progress` | G | f21 drops limited-time exclusive-rights means; Arts is only in joined object. |
| `i8-authors-rights` | G | f21 has promote only; no secure-rights relation or duration. |
| `i8-inventors-rights` | G | f21 has promote only; no secure-rights relation or duration. |
| `i8-inferior-tribunals` | M | f22/o0 |
| `i8-define-piracies` | G | f23 joins define/punish and Piracies/Felonies; no atomic scoped option. |
| `i8-punish-piracies` | G | f23 joins define/punish and Piracies/Felonies; no atomic scoped option. |
| `i8-define-felonies-seas` | G | f23 joins define/punish and Piracies/Felonies; no atomic scoped option. |
| `i8-punish-felonies-seas` | G | f23 joins define/punish and Piracies/Felonies; no atomic scoped option. |
| `i8-define-nations-offences` | M | f24/o0 |
| `i8-punish-nations-offences` | G | f24 offers define only; punishment absent. |
| `i8-declare-war` | M | f25/o0 |
| `i8-marque-reprisal` | M | f26/o0 |
| `i8-captures-land` | M | f27/o5 |
| `i8-captures-water` | G | f27 joins Land and Water; no atomic Water option. |
| `i8-raise-armies` | M | f28/o0 |
| `i8-support-armies` | M | f29/o0 |
| `i8-army-appropriation-limit` | G | No frame for two-year appropriation ceiling. |
| `i8-provide-navy` | M | f30/o0 |
| `i8-maintain-navy` | M | f31/o0 |
| `i8-rules-land-forces` | G | f32 combines land and naval forces; no separate force option. |
| `i8-rules-naval-forces` | G | f32 combines land and naval forces; no separate force option. |
| `i8-militia-call-execute-laws` | M | f33/o0 |
| `i8-militia-call-suppress-insurrections` | G | f34–35 say Congress directly suppresses/repels; militia-calling means missing. |
| `i8-militia-call-repel-invasions` | G | f34–35 say Congress directly suppresses/repels; militia-calling means missing. |
| `i8-militia-organize` | G | f36–38 authorize direct action; “provide for” legislative relation missing. |
| `i8-militia-arm` | G | f36–38 authorize direct action; “provide for” legislative relation missing. |
| `i8-militia-discipline` | G | f36–38 authorize direct action; “provide for” legislative relation missing. |
| `i8-militia-govern-federal` | G | f39 omits employed-in-US-service limitation. |
| `i8-states-militia-officers` | G | No State reservation/training or Congress-prescribed-discipline edge. |
| `i8-states-militia-training` | G | No State reservation/training or Congress-prescribed-discipline edge. |
| `i8-congress-militia-discipline` | G | No State reservation/training or Congress-prescribed-discipline edge. |
| `i8-district-legislation` | G | f40 omits size, State cession, Congress acceptance, and federal-seat qualifiers. |
| `i8-district-size` | G | f40 does not separately offer district size, cession, or acceptance. |
| `i8-district-state-cession` | G | f40 does not separately offer district size, cession, or acceptance. |
| `i8-district-congress-accept` | G | f40 does not separately offer district size, cession, or acceptance. |
| `i8-enclave-authority` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-enclave-purchase-consent` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-enclave-purpose-forts` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-enclave-purpose-magazines` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-enclave-purpose-arsenals` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-enclave-purpose-dockyards` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-enclave-purpose-other-buildings` | G | f40 omits purchased-place authority and State-consent/purpose edges. |
| `i8-necessary-proper-foregoing` | G | f41 offers generic make-Laws; necessary/proper and vested-power target absent. |
| `i8-necessary-proper-other-gov` | G | f41 offers generic make-Laws; necessary/proper and vested-power target absent. |
| `i8-necessary-proper-department` | G | f41 offers generic make-Laws; necessary/proper and vested-power target absent. |
| `i8-necessary-proper-officer` | G | f41 offers generic make-Laws; necessary/proper and vested-power target absent. |

### Article I §9 — 0/40

| Gold ID | Result | Option or decisive defect |
|---|---|---|
| `i9-migration-before-1808` | G | f1 subject is “proper to admit,” not Migration/Importation; qualifying persons absent. |
| `i9-importation-before-1808` | G | f1 subject is “proper to admit,” not Migration/Importation; qualifying persons absent. |
| `i9-importation-tax` | G | f2 omits such-Persons scope and ten-dollar-per-person cap. |
| `i9-importation-duty` | G | f2 omits such-Persons scope and ten-dollar-per-person cap. |
| `i9-habeas-suspension` | G | No Habeas Corpus frame/options. |
| `i9-habeas-rebellion-exception` | G | No Habeas Corpus frame/options. |
| `i9-habeas-invasion-exception` | G | No Habeas Corpus frame/options. |
| `i9-bill-attainder` | G | No prohibition frame/options for this sentence. |
| `i9-ex-post-facto` | G | No prohibition frame/options for this sentence. |
| `i9-capitation-proportion` | G | f4 has Census/direct fragments; no tax-laying edge or proportion rule. |
| `i9-other-direct-tax-proportion` | G | f4 has Census/direct fragments; no tax-laying edge or proportion rule. |
| `i9-export-tax` | G | f5 says Tax/Duty exported_from State; actor and no-laying prohibition missing. |
| `i9-export-duty` | G | f5 says Tax/Duty exported_from State; actor and no-laying prohibition missing. |
| `i9-commerce-port-preference` | G | f6 has Preference given_by Regulation; port comparison and separate Commerce/Revenue rule absent. |
| `i9-revenue-port-preference` | G | f6 has Preference given_by Regulation; port comparison and separate Commerce/Revenue rule absent. |
| `i9-vessel-to-enter` | G | f7–10 misbind Vessels, lose negation and to/from-State direction. |
| `i9-vessel-to-clear` | G | f7–10 misbind Vessels, lose negation and to/from-State direction. |
| `i9-vessel-to-pay-duties` | G | f7–10 misbind Vessels, lose negation and to/from-State direction. |
| `i9-vessel-from-enter` | G | f7–10 misbind Vessels, lose negation and to/from-State direction. |
| `i9-vessel-from-clear` | G | f7–10 misbind Vessels, lose negation and to/from-State direction. |
| `i9-vessel-from-pay-duties` | G | f7–10 misbind Vessels, lose negation and to/from-State direction. |
| `i9-treasury-appropriation` | G | No Treasury-draw/appropriations-by-Law frame. |
| `i9-receipts-statement` | G | f11 makes Expenditures published_from time; Statement/Account actor and content absent. |
| `i9-expenditures-statement` | G | f11 makes Expenditures published_from time; Statement/Account actor and content absent. |
| `i9-statement-published` | G | f11 makes Expenditures published_from time; Statement/Account actor and content absent. |
| `i9-federal-nobility` | G | f12 has inverse edge but loses shall and copies emoluments-consent exception. |
| `i9-emoluments-king-present` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-king-emolument` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-king-office` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-king-title` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-prince-present` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-prince-emolument` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-prince-office` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-prince-title` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-foreign-state-present` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-foreign-state-emolument` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-foreign-state-office` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-emoluments-foreign-state-title` | G | f13 only has Person holding Office; no negative accepts/gift-source/consent option. |
| `i9-capitation-exception` | G | f4 has Census/direct fragments; no tax-laying edge or proportion rule. |
| `i9-direct-tax-exception` | G | f4 has Census/direct fragments; no tax-laying edge or proportion rule. |

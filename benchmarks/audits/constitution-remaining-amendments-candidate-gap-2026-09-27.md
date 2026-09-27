# Candidate gaps in ten reviewed Constitution amendment units

Local-only audit of the ten `constitution-amendment-*-codex-reviewed-2026-09-27.json` fixtures. I ran `extract_frames(fixture["text"])` and enumerated offered `_triple_options(frame)` with `PYTHONPATH=src`. No model/API or paid call. Frame (`f`) and option (`o`) indices are zero-based within each fixture. The ten runs produced 128 frames and 2,674 offered options in total.

**Match rule:** One offered option must preserve actor, relation, object, modality, polarity, and every material condition or exception. Inflection and genuinely equivalent wording count. A deictic phrase such as “this purpose” counts only when retained in the option and unambiguously resolved by that frame’s context. Evidence alone does not repair omitted qualifications; options from different frames are not assembled into one claim.

| Unit | Gold | Semantic candidate matches | Gaps |
|---|---:|---:|---:|
| `AMENDMENT_12` | 32 | **3** | 29 |
| `AMENDMENT_14_SECTION_1` | 12 | **0** | 12 |
| `AMENDMENT_14_SECTION_2` | 15 | **1** | 14 |
| `AMENDMENT_14_SECTION_3` | 25 | **0** | 25 |
| `AMENDMENT_14_SECTION_4` | 35 | **0** | 35 |
| `AMENDMENT_17` | 12 | **4** | 8 |
| `AMENDMENT_20_SECTION_3` | 9 | **1** | 8 |
| `AMENDMENT_20_SECTION_4` | 2 | **0** | 2 |
| `AMENDMENT_23_SECTION_1` | 9 | **0** | 9 |
| `AMENDMENT_25_SECTION_4` | 25 | **0** | 25 |
| **Total** | **176** | **9 (5.1%)** | **167** |

## Highest-impact gaps

1. **Conditional branches are flattened.** Amendment XII loses presidential/vice-presidential ballot separation, majority thresholds, top-three House selection, and top-two Senate selection. Amendment XX §3 loses the death and failure-to-qualify alternatives; only the no-President-chosen acting branch survives.
2. **Long-clause actor drift corrupts legal duties.** Amendment XIV §1 produces no citizenship, due-process, or equal-protection edge; Amendment XXIII §1 attributes District-elector actions to Representatives or the seat of Government.
3. **Negation and exception scope fail.** Amendment XIV §4 emits `United States nor any State / assume / or pay...` with **positive** polarity although the text forbids both. Amendment XIV §2 marks whole-person counting negative because of the nearby “excluding Indians not taxed.”
4. **Nested eligibility prerequisites disappear.** Amendment XIV §3 has a near option `person / type / Senator` with negative polarity, but lacks the prior oath plus insurrection/rebellion/aid-or-comfort conditions and seven other barred office classes.
5. **Emergency succession conditions are not carried through.** Amendment XXV §4 offers Vice President assumption and continuation words, but omits written inability declarations, both recipients, four-day counter-declaration, two-thirds vote of both Houses, and the correct 21-day clock. The 48-hour assembly option has negative polarity merely because Congress is “not in session.”

## What counted despite string differences

- Amendment XII `Electors / meets_in / their respective states` appears at `f0/o2`. Its House and Senate contingent-election quorum thresholds appear at `f33/o8` and `f45/o8`; each option retains “this purpose” or “the purpose,” resolved by its frame context.
- Amendment XIV §2 `Representatives / apportioned / among the several States according to their respective numbers` at `f0/o0` preserves the State-numbers qualifier inside the object.
- Amendment XVII has `Senate / composed_of / two Senators from each State` (`f0/o0`), `Senator / has / one vote` (`f3/o0`), State elector qualifications (`f4/o0`), and vacancy writs with the vacancy condition (`f5/o0`).
- Amendment XX §3 `Vice President elect / act / President until a President shall have qualified` at `f10/o0` preserves the **not chosen before term starts** trigger. Its failed-to-qualify trigger is absent from that frame’s condition.

## All-claim M/G ledger

`M` = semantic option match; `G` = genuine gap. The reason names the decisive failure.

### `AMENDMENT_12` — 3/32

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a12-electors-meet` | M | f0/o2 |
| `a12-president-ballot` | G | No separate vote/name-in-ballot edge; f0/f4–7 embed action or wrong actor/polarity. |
| `a12-vice-president-ballot` | G | No separate vote/name-in-ballot edge; f0/f4–7 embed action or wrong actor/polarity. |
| `a12-out-of-state-person` | G | f2 says one of whom is not same-State inhabitant but drops the at-least-one quantifier and ballot-choice boundary. |
| `a12-presidential-name-on-ballot` | G | No separate vote/name-in-ballot edge; f0/f4–7 embed action or wrong actor/polarity. |
| `a12-vice-presidential-name-distinct-ballot` | G | No separate vote/name-in-ballot edge; f0/f4–7 embed action or wrong actor/polarity. |
| `a12-presidential-list-persons` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-vice-presidential-list-persons` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-presidential-list-count` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-vice-presidential-list-count` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-sign-lists` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-certify-lists` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-transmit-lists` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-lists-sealed` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-lists-destination` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-lists-addressed` | G | f8–13 give list/sign/transmit acts negative polarity or wrong actor/list boundary. |
| `a12-certificates-open` | G | f14–15 misparse certificates; no opening/counting edge with joint-chamber presence. |
| `a12-votes-counted` | G | f14–15 misparse certificates; no opening/counting edge with joint-chamber presence. |
| `a12-president-majority-winner` | G | f17/f41 make vote tally, not person, President/VP; appointed-elector majority buried in object. |
| `a12-house-chooses-president` | G | f23–25 attach House choice to Electors with negative polarity; top-three/no-majority branch lost. |
| `a12-house-votes-by-states` | G | f30 Votes taken_by states lacks House presidential-choice scope. |
| `a12-house-state-one-vote` | G | f32 gives one vote to President, not State representation. |
| `a12-house-quorum` | M | f33/o8 |
| `a12-house-majority-states` | G | No majority-of-all-States/Senators requirement edge. |
| `a12-bracketed-house-deadline` | G | f39 VP act President omits House-failure/March-4 condition; analogy edges absent. |
| `a12-vice-president-majority-winner` | G | f17/f41 make vote tally, not person, President/VP; appointed-elector majority buried in object. |
| `a12-senate-chooses-vp` | G | f44 loses Senate actor and no-majority/top-two branch. |
| `a12-senate-vp-quorum` | M | f45/o8 |
| `a12-senate-vp-majority` | G | No majority-of-all-States/Senators requirement edge. |
| `a12-vp-eligibility` | G | No VP ineligibility edge. |
| `a12-bracketed-acting-analogy-death` | G | f39 VP act President omits House-failure/March-4 condition; analogy edges absent. |
| `a12-bracketed-acting-analogy-other-disability` | G | f39 VP act President omits House-failure/March-4 condition; analogy edges absent. |

### `AMENDMENT_14_SECTION_1` — 0/12

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a14s1-born-united-states` | G | f0 extracts naturalization location, no citizenship edge or jurisdiction/residence conditions. |
| `a14s1-born-state-wherein-the-person-resides` | G | f0 extracts naturalization location, no citizenship edge or jurisdiction/residence conditions. |
| `a14s1-naturalized-united-states` | G | f0 extracts naturalization location, no citizenship edge or jurisdiction/residence conditions. |
| `a14s1-naturalized-state-wherein-the-person-resides` | G | f0 extracts naturalization location, no citizenship edge or jurisdiction/residence conditions. |
| `a14s1-no-make-privileges` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-no-make-immunities` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-no-enforce-privileges` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-no-enforce-immunities` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-due-process-life` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-due-process-liberty` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-due-process-property` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |
| `a14s1-equal-protection` | G | f1–2 misparse make/enforce and use wrong polarity/condition; due-process/equal-protection edges absent. |

### `AMENDMENT_14_SECTION_2` — 1/15

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a14s2-apportionment` | M | f0/o0 |
| `a14s2-whole-person-count` | G | f1–2 use Representatives as count actor and mark both counting clauses negative. |
| `a14s2-indians-not-taxed` | G | f1–2 use Representatives as count actor and mark both counting clauses negative. |
| `a14s2-reduction-electors-for-president-denied` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-electors-for-president-abridged` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-electors-for-vice-president-denied` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-electors-for-vice-president-abridged` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-representatives-in-congress-denied` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-representatives-in-congress-abridged` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-executive-officers-of-a-state-denied` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-executive-officers-of-a-state-abridged` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-judicial-officers-of-a-state-denied` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-judicial-officers-of-a-state-abridged` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-members-of-the-state-legislature-denied` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |
| `a14s2-reduction-members-of-the-state-legislature-abridged` | G | f7 reduction frame lacks election category, denied/abridged branch, qualified population, and correct exception scope. |

### `AMENDMENT_14_SECTION_3` — 0/25

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a14s3-senator-in-congress-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-senator-in-congress-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-senator-in-congress-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-representative-in-congress-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-representative-in-congress-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-representative-in-congress-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-elector-of-president-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-elector-of-president-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-elector-of-president-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-elector-of-vice-president-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-elector-of-vice-president-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-elector-of-vice-president-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-civil-office-under-the-united-states-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-civil-office-under-the-united-states-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-civil-office-under-the-united-states-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-military-office-under-the-united-states-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-military-office-under-the-united-states-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-military-office-under-the-united-states-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-civil-office-under-a-state-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-civil-office-under-a-state-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-civil-office-under-a-state-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-military-office-under-a-state-insurrection` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-military-office-under-a-state-rebellion` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-military-office-under-a-state-aid-or-comfort` | G | f0 person type Senator lacks prior-oath capacity plus misconduct trigger; other office branches absent. |
| `a14s3-congress-removes-disability` | G | No Congress/removal/two-thirds-of-each-House option. |

### `AMENDMENT_14_SECTION_4` — 0/35

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a14s4-public-debt-validity` | G | No shall-not-question debt-validity relation; f0–4 extract authorization/payment fragments. |
| `a14s4-pensions-debt-insurrection` | G | No shall-not-question debt-validity relation; f0–4 extract authorization/payment fragments. |
| `a14s4-pensions-debt-rebellion` | G | No shall-not-question debt-validity relation; f0–4 extract authorization/payment fragments. |
| `a14s4-bounties-debt-insurrection` | G | No shall-not-question debt-validity relation; f0–4 extract authorization/payment fragments. |
| `a14s4-bounties-debt-rebellion` | G | No shall-not-question debt-validity relation; f0–4 extract authorization/payment fragments. |
| `a14s4-united-states-assume-debt-incurred-in-a-0-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-assume-debt-incurred-in-a-0-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-assume-obligation-incurre-1-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-assume-obligation-incurre-1-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-assume-claim-for-loss-of--2` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-assume-claim-for-emancipa-3` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-pay-debt-incurred-in-a-0-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-pay-debt-incurred-in-a-0-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-pay-obligation-incurre-1-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-pay-obligation-incurre-1-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-pay-claim-for-loss-of--2` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-united-states-pay-claim-for-emancipa-3` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-assume-debt-incurred-in-a-0-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-assume-debt-incurred-in-a-0-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-assume-obligation-incurre-1-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-assume-obligation-incurre-1-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-assume-claim-for-loss-of--2` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-assume-claim-for-emancipa-3` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-pay-debt-incurred-in-a-0-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-pay-debt-incurred-in-a-0-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-pay-obligation-incurre-1-insurrection` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-pay-obligation-incurre-1-rebellion` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-pay-claim-for-loss-of--2` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-state-pay-claim-for-emancipa-3` | G | f5 makes United States nor any State assume/pay positive; negative polarity and each debt/claim object lost. |
| `a14s4-0-void-insurrection` | G | f7–8 say generic claims holds illegal/void separately; specific debt/obligation/claim and combined status absent. |
| `a14s4-0-void-rebellion` | G | f7–8 say generic claims holds illegal/void separately; specific debt/obligation/claim and combined status absent. |
| `a14s4-1-void-insurrection` | G | f7–8 say generic claims holds illegal/void separately; specific debt/obligation/claim and combined status absent. |
| `a14s4-1-void-rebellion` | G | f7–8 say generic claims holds illegal/void separately; specific debt/obligation/claim and combined status absent. |
| `a14s4-2-void` | G | f7–8 say generic claims holds illegal/void separately; specific debt/obligation/claim and combined status absent. |
| `a14s4-3-void` | G | f7–8 say generic claims holds illegal/void separately; specific debt/obligation/claim and combined status absent. |

### `AMENDMENT_17` — 4/12

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a17-senate-composition` | M | f0/o0 |
| `a17-election-by-people` | G | f1–2 give elected_by/term to Senate, not Senators. |
| `a17-term` | G | f1–2 give elected_by/term to Senate, not Senators. |
| `a17-senator-vote` | M | f3/o0 |
| `a17-state-elector-qualifications` | M | f4/o0 |
| `a17-vacancy-writs` | M | f5/o0 |
| `a17-legislature-empowers-executive` | G | No legislature-authorization, temporary appointment, people-fill, or legislature-directed election edge. |
| `a17-executive-temporary-appointments` | G | No legislature-authorization, temporary appointment, people-fill, or legislature-directed election edge. |
| `a17-people-fill-vacancy` | G | No legislature-authorization, temporary appointment, people-fill, or legislature-directed election edge. |
| `a17-legislature-directs-vacancy-election` | G | No legislature-authorization, temporary appointment, people-fill, or legislature-directed election edge. |
| `a17-prior-senator-election` | G | f8 has State affects election positive; amendment grandfathering negative rule missing. |
| `a17-prior-senator-term` | G | f8 has State affects election positive; amendment grandfathering negative rule missing. |

### `AMENDMENT_20_SECTION_3` — 1/9

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a20s3-vp-elect-becomes-president` | G | f4 VP elect becomes President, but condition omits death of President elect. |
| `a20s3-vp-elect-acts-not-chosen` | M | f10/o0 |
| `a20s3-vp-elect-acts-failed-to-qualify` | G | f10 VP elect acts has only no-President-chosen condition, not failed-to-qualify branch. |
| `a20s3-congress-provision` | G | f11–15 omit may/by-law, neither-elect-qualified trigger, or Congress as declarant. |
| `a20s3-congress-declare-officer` | G | f11–15 omit may/by-law, neither-elect-qualified trigger, or Congress as declarant. |
| `a20s3-congress-select-manner` | G | f11–15 omit may/by-law, neither-elect-qualified trigger, or Congress as declarant. |
| `a20s3-designated-person-acts` | G | f16 person acts accordingly lacks designation and neither-elect-qualified condition/endpoints. |
| `a20s3-acting-until-president` | G | f16 person acts accordingly lacks designation and neither-elect-qualified condition/endpoints. |
| `a20s3-acting-until-vice-president` | G | f16 person acts accordingly lacks designation and neither-elect-qualified condition/endpoints. |

### `AMENDMENT_20_SECTION_4` — 0/2

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a20s4-house-candidate-death` | G | f0 Congress provides for death fragment has no may/by-law modality, candidate class, or House/Senate devolved-choice condition. |
| `a20s4-senate-candidate-death` | G | f0 Congress provides for death fragment has no may/by-law modality, candidate class, or House/Senate devolved-choice condition. |

### `AMENDMENT_23_SECTION_1` — 0/9

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a23s1-district-appoints` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-congress-manner` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-elector-number` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-cap` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-additional` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-considered-state-president` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-considered-state-vice-president` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-meet` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |
| `a23s1-twelfth-amendment-duties` | G | f1–7 misbind District electors to seat of Government/Representatives; f6 meets_in is negative; no qualified District-elector edge. |

### `AMENDMENT_25_SECTION_4` — 0/25

| Gold ID | M/G | Option or decisive reason |
|---|---|---|
| `a25s4-congress-other-body` | G | No Congress may provide alternative body edge. |
| `a25s4-initial-principal-officers-to-senate-president-pro-tempore` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-initial-principal-officers-to-house-speaker` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-initial-principal-officers-vp-assumes-powers` | G | f2–3 VP assumes powers/duties but condition stops before written inability declaration and two recipients. |
| `a25s4-initial-principal-officers-vp-assumes-duties` | G | f2–3 VP assumes powers/duties but condition stops before written inability declaration and two recipients. |
| `a25s4-initial-principal-officers-acting-president` | G | f2–3 VP assumes powers/duties but condition stops before written inability declaration and two recipients. |
| `a25s4-initial-other-body-to-senate-president-pro-tempore` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-initial-other-body-to-house-speaker` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-initial-other-body-vp-assumes-powers` | G | f2–3 VP assumes powers/duties but condition stops before written inability declaration and two recipients. |
| `a25s4-initial-other-body-vp-assumes-duties` | G | f2–3 VP assumes powers/duties but condition stops before written inability declaration and two recipients. |
| `a25s4-initial-other-body-acting-president` | G | f2–3 VP assumes powers/duties but condition stops before written inability declaration and two recipients. |
| `a25s4-president-no-inability-to-senate-president-pro-tempore` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-president-no-inability-to-house-speaker` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-president-resumes-uncontested` | G | f4–5 use Vice President as actor; no no-inability declaration or four-day objection scope. |
| `a25s4-counter-principal-officers-to-senate-president-pro-tempore` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-counter-principal-officers-to-house-speaker` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-counter-other-body-to-senate-president-pro-tempore` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-counter-other-body-to-house-speaker` | G | No transmission-to-recipient edge for the specified writer/body, written declaration, timing, and content. |
| `a25s4-congress-decides` | G | f7 Congress decides issue lacks timely counter-declaration antecedent. |
| `a25s4-congress-assembles-48h` | G | f8 has 48 hours but negative polarity from not in session. |
| `a25s4-congress-inability-vote-in-session` | G | f10 subject is to assemble; no Congress/two-thirds/both-Houses/21-day determination. |
| `a25s4-vp-continues-in-session` | G | f12 VP continues but condition is only If Congress, losing supermajority and 21-day branch. |
| `a25s4-congress-inability-vote-out-of-session` | G | f10 subject is to assemble; no Congress/two-thirds/both-Houses/21-day determination. |
| `a25s4-vp-continues-out-of-session` | G | f12 VP continues but condition is only If Congress, losing supermajority and 21-day branch. |
| `a25s4-president-resumes-otherwise` | G | f15–16 President resumes powers/duties separately; otherwise/timely-vote condition absent. |

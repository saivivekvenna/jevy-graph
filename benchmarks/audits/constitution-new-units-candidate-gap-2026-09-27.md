# Candidate coverage of two newly reviewed Constitution units

Local-only audit of the two 2026-09-26 fixtures. I called `extract_frames(fixture["text"])` and enumerated `_triple_options(frame)` with `PYTHONPATH=src`; **no Jev/API request or paid call**. Article I §10 produced **20 frames / 134 offered options**; Article II §1 produced **62 frames / 1,268 offered options**. The offline evaluator reported exact-schema candidate matches of 2/33 and 1/59.

## Match rule and result

An offered option counts if its subject, relation, object, polarity, modality, and all material legal conditions/exception scopes preserve a gold claim. Equivalent wording counts. A deictic qualifier may be resolved from frame context only when the option retains it unambiguously (`this Purpose`, `that Period`, `any of them`). Evidence alone cannot repair a missing condition, wrong actor, or a `condition` field that copies another clause's exception.

| Unit | Exact-schema probe | Semantic option coverage | Genuine gaps |
|---|---:|---:|---:|
| Article I §10 | 2/33 | **8/33 (24.2%)** | 25 |
| Article II §1 | 1/59 | **7/59 (11.9%)** | 52 |
| Both | 3/92 | **15/92 (16.3%)** | 77 |

The II.1 quorum match (`f29/o13`) requires resolving “this Purpose” through frame context. Excluding that contextual equivalence gives **6/59** for II.1 and **14/92** overall.

## Exact versus semantic examples

- I.10 `State / enter_into / Treaty` is semantically present as `State / enter / Treaty` (`f0/o3`, negative, shall). Alliance and Confederation likewise appear in `f1/o0` and `f2/o0`.
- I.10 `State / coin / Money` is present as `State / coins / Money` (`f4/o0`, negative, shall).
- II.1 `each State / appoints / Electors` is present as `State / appoints / Electors` (`f3/o16`, positive, shall).
- II.1 the oath/affirmation before office is `President / takes / Oath or Affirmation` (`f60/o9`) with the pre-office condition.
- II.1 the negative federal-emolument rule is `President / receives / within that Period any other Emolument from the United States` (`f59/o13`); `f59/o0` also retains “or any of them” for the State branch.

## Highest-impact genuine gaps

1. **P0 — Scope exceptions per act.** I.10 customs consent plus inspection necessity is absent. The last-paragraph options `State / lays / Duty of Tonnage`, `State / keep / Troops`, and `State / keep / Ships of War` look plausible but their `condition` contains the entire list **and the war-only invasion exception**. They cannot express correctly scoped tonnage, troop, or peacetime-ship rules.
2. **P0 — Preserve actors and complete objects across long clauses.** II.1 turns “He” into `executive Power`, “Day” into `Electors`, the electoral List into `Ballot` or `Persons`, and Congress's declaration into an act of `Duties`. Ranked options often clip the full qualifier.
3. **P0 — Emit separate conditional election branches.** No usable candidate encodes majority of **all appointed electors**, the tied-majority House choice, the no-majority top-five choice, the House vote by State with one vote per State, or the Senate tie trigger. Words in evidence do not make these conditions part of a triple.
4. **P1 — Bind negation and quantified alternatives.** I.10's gold/silver tender carveout, elector ineligibility, presidential citizenship/age/residence, and fixed-pay rules are missing or malformed despite nearby matches.
5. **P1 — Resolve short anaphora and succession scope.** “which List,” “the Same,” “such Officer,” and “this Purpose” need correct antecedents; the four presidential triggers and dual-office contingency must remain separate.

## All 92 gold claims: semantic decision ledger

`M` = offered semantic match; `G` = genuine candidate gap. Frame/option numbers are zero-based within each section. Each gap note identifies the decisive defect.


### Article I §10 — 8/33

| Gold ID | Result | Decisive evidence |
|---|---|---|
| `i10-treaty` | M | f0/o3 |
| `i10-alliance` | M | f1/o0 |
| `i10-confederation` | M | f2/o0 |
| `i10-marque-reprisal` | M | f3/o0 |
| `i10-coin-money` | M | f4/o0 |
| `i10-bills-credit` | M | f5/o0 |
| `i10-non-specie-tender` | G | f6 loses the gold/silver exception from the tender object. |
| `i10-bill-attainder` | M | f7/o0 |
| `i10-ex-post-facto` | M | f8/o0 |
| `i10-contract-impairment` | G | f9 passes generic Law; f10 directly impairs Contracts rather than passing an impairing Law. |
| `i10-nobility` | G | f11 has State impairing a grant/title; no grant of nobility edge. |
| `i10-imposts-imports-consent` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-imposts-imports-inspection-exception` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-imposts-exports-consent` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-imposts-exports-inspection-exception` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-duties-imports-consent` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-duties-imports-inspection-exception` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-duties-exports-consent` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-duties-exports-inspection-exception` | G | f12–13 miss State tax × trade-flow and consent/inspection exception. |
| `i10-duties-imports-net-produce` | G | f13 makes Imposts use Treasury; net proceeds of the specified State levy are missing. |
| `i10-duties-exports-net-produce` | G | f13 makes Imposts use Treasury; net proceeds of the specified State levy are missing. |
| `i10-imposts-imports-net-produce` | G | f13 makes Imposts use Treasury; net proceeds of the specified State levy are missing. |
| `i10-imposts-exports-net-produce` | G | f13 makes Imposts use Treasury; net proceeds of the specified State levy are missing. |
| `i10-customs-laws-revision` | G | No State-law revision/control edge. |
| `i10-customs-laws-control` | G | No State-law revision/control edge. |
| `i10-tonnage` | G | f14–16 contain act/object but overcopy the whole list and war-only invasion exception into condition. |
| `i10-troops-peace` | G | f14–16 contain act/object but overcopy the whole list and war-only invasion exception into condition. |
| `i10-warships-peace` | G | f14–16 contain act/object but overcopy the whole list and war-only invasion exception into condition. |
| `i10-agreement-another-State` | G | f17 combines Agreement/Compact × State/foreign Power and overcopies war exception. |
| `i10-agreement-a-foreign-Power` | G | f17 combines Agreement/Compact × State/foreign Power and overcopies war exception. |
| `i10-compact-another-State` | G | f17 combines Agreement/Compact × State/foreign Power and overcopies war exception. |
| `i10-compact-a-foreign-Power` | G | f17 combines Agreement/Compact × State/foreign Power and overcopies war exception. |
| `i10-war` | G | No State-engages-in-War edge; f18–19 extract invaded/admit-delay fragments. |

### Article II §1 — 7/59

| Gold ID | Result | Decisive evidence |
|---|---|---|
| `ii1-executive-power` | M | f0/o0 |
| `ii1-president-term` | G | f1–2 misbind He to executive Power or emit Vice President elected→follows. |
| `ii1-vice-president-term` | G | f1–2 misbind He to executive Power or emit Vice President elected→follows. |
| `ii1-president-elected` | G | f1–2 misbind He to executive Power or emit Vice President elected→follows. |
| `ii1-vice-president-elected` | G | f1–2 misbind He to executive Power or emit Vice President elected→follows. |
| `ii1-state-appoint-electors` | M | f3/o16 |
| `ii1-legislature-directs-manner` | G | f4 makes Legislature direct Congress, not elector appointment manner. |
| `ii1-elector-number` | G | f3 lacks complete equality to State congressional entitlement. |
| `ii1-elector-ineligible-senator` | G | f6–7 lose ineligible person and/or negative appointed-as relation. |
| `ii1-elector-ineligible-representative` | G | f6–7 lose ineligible person and/or negative appointed-as relation. |
| `ii1-elector-ineligible-federal-office-of-trust` | G | f6–7 lose ineligible person and/or negative appointed-as relation. |
| `ii1-elector-ineligible-federal-office-of-profit` | G | f6–7 lose ineligible person and/or negative appointed-as relation. |
| `ii1-electors-meet` | M | f8/o2 |
| `ii1-electors-vote-two` | G | f8 embeds voting inside meet_in object; no vote edge. |
| `ii1-elector-out-of-state-choice` | G | f9 one at least/type/Inhabitant lacks selected-person and same-State boundary. |
| `ii1-electors-list-persons` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-electors-list-tallies` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-electors-sign-list` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-electors-certify-list` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-electors-transmit-list` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-list-sealed` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-list-destination` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-list-addressed` | G | f10–14 bind list/sign/transmit/address to Ballot, Persons, or a prior clause. |
| `ii1-certificates-opened` | G | No certificate-opening/vote-counting frame. |
| `ii1-votes-counted` | G | No certificate-opening/vote-counting frame. |
| `ii1-president-majority-winner` | G | f16 makes vote count President; majority of all appointed electors not scoped. |
| `ii1-house-tied-majority` | G | f21 House/ballot option loses tied-majority trigger and timing. |
| `ii1-house-no-majority` | G | No top-five/no-majority House-choice frame. |
| `ii1-house-votes-by-state` | G | f26 Votes taken_by States lacks House presidential-choice scope. |
| `ii1-each-state-one-vote` | G | f28 gives one Vote to President rather than State representation. |
| `ii1-house-choice-quorum` | M | f29/o13 |
| `ii1-house-choice-majority` | G | No majority-of-all-States choice requirement. |
| `ii1-vice-president-highest-remaining` | G | f31 makes vote count, not Person, Vice President; after-choice scope lost. |
| `ii1-senate-vp-tie` | G | f36 lacks equal remaining-vote trigger. |
| `ii1-congress-elector-choice-time` | G | f37 Congress determines Time, missing of chusing Electors. |
| `ii1-congress-elector-vote-day` | G | No Congress-determines-voting-Day edge. |
| `ii1-uniform-vote-day` | G | f41 makes Electors same throughout, not voting Day. |
| `ii1-citizenship-eligibility` | G | Citizenship absent; f42 assigns age attainment to Day; eligibility conditions lost. |
| `ii1-age-eligibility` | G | Citizenship absent; f42 assigns age attainment to Day; eligibility conditions lost. |
| `ii1-residency-eligibility` | G | Citizenship absent; f42 assigns age attainment to Day; eligibility conditions lost. |
| `ii1-vp-devolution-removal` | G | f43 includes Duties only and Removal only; Powers/other triggers lost. |
| `ii1-vp-devolution-death` | G | f43 includes Duties only and Removal only; Powers/other triggers lost. |
| `ii1-vp-devolution-resignation` | G | f43 includes Duties only and Removal only; Powers/other triggers lost. |
| `ii1-vp-devolution-inability` | G | f43 includes Duties only and Removal only; Powers/other triggers lost. |
| `ii1-congress-double-vacancy-law` | G | f45–49 lose may/by Law and both-office condition. |
| `ii1-congress-declares-acting-officer` | G | f50 makes Duties of Office declare Officer. |
| `ii1-designated-officer-acts` | G | f51–54 lose designation, both-office trigger, or service endpoint. |
| `ii1-acting-until-disability-removed` | G | f51–54 lose designation, both-office trigger, or service endpoint. |
| `ii1-acting-until-president-elected` | G | f51–54 lose designation, both-office trigger, or service endpoint. |
| `ii1-compensation` | G | f55 says President stated Compensation, not receives. |
| `ii1-compensation-not-increased` | G | f56–57 clip pay rule and elected-period boundary. |
| `ii1-compensation-not-diminished` | G | f56–57 clip pay rule and elected-period boundary. |
| `ii1-no-other-federal-emolument` | M | f59/o13 |
| `ii1-no-other-state-emolument` | M | f59/o0 |
| `ii1-oath-or-affirmation` | M | f60/o9 |
| `ii1-oath-faithful-execution` | G | f61 lacks correct oath speaker/pledge and preserve/protect/defend edges. |
| `ii1-oath-preserve` | G | f61 lacks correct oath speaker/pledge and preserve/protect/defend edges. |
| `ii1-oath-protect` | G | f61 lacks correct oath speaker/pledge and preserve/protect/defend edges. |
| `ii1-oath-defend` | G | f61 lacks correct oath speaker/pledge and preserve/protect/defend edges. |

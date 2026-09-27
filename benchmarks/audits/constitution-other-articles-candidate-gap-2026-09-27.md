# Candidate coverage of seven newly reviewed Constitution units

Local-only audit of the 2026-09-27 fixtures listed below. I ran `extract_frames(fixture["text"])` and enumerated every `_triple_options(frame)` using the current local `src` code. No Jev/API call was made. Frame and option indices are zero-based **within each fixture**.

An `M` requires one offered option to preserve the gold claim's actor, relation, object, polarity, modality, and material condition or exception. Equivalent wording counts; a joined object does not count for a separate atomic gold relation unless another offered option isolates it with all required scope. Source evidence cannot restore a missing qualifier. A deictic term counts only when its antecedent is unambiguous in the same source provision. `G` means a genuine offered-candidate gap under this rule, even if the evidence includes the gold wording. IV §2 Privileges and Immunities now have separate atomic gold entries, each matched by one offered option.

| Unit | Gold | Frames | Offered options | Semantic matches | Gaps |
|---|---:|---:|---:|---:|---:|
| `article-2-section-2` | 29 | 12 | 249 | **2** | 27 |
| `article-2-section-3` | 9 | 7 | 87 | **0** | 9 |
| `article-3-section-2` | 36 | 24 | 449 | **4** | 32 |
| `article-4-section-2` | 9 | 16 | 267 | **2** | 7 |
| `article-4-section-3` | 12 | 9 | 136 | **0** | 12 |
| `article-5` | 13 | 10 | 173 | **0** | 13 |
| `article-6` | 18 | 11 | 218 | **1** | 17 |
| **Total** | **126** | **89** | **1579** | **9 (7.1%)** | **117** |

The offline literal `_option_has_gold` matcher finds **2/126**, both in II §2. Semantic review adds two Article IV Privileges/Immunities options, four Article III jurisdiction options, and the Article VI `thereby` option. The joined reprieve/pardon and admiralty/maritime objects are not counted for split atomic gold claims.

## Main failure patterns

1. **Joined objects lack atomic candidates.** II §2's reprieve/pardon option joins two grant objects; its isolated Reprieves option loses the United States-offences scope. III §2 has an atomic admiralty-cases option, but its maritime option drops Cases.
2. **Condition leakage changes legal scope.** II §2 commander frames carry the pardon-only impeachment exception. IV §3 admission carries the intra-State formation consent rule. Article V frames carry both provisos into unrelated amendment steps. III §2 venue inherits the jury/impeachment clause. These are gaps even when an action and object appear in a triple.
3. **Conjunctive or enumerated objects break apart.** II §2 appointment candidates omit Senate consent, office titles, or legal limits. III §2 Cases in Law/Equity lose their arising-under source, and party pairings beyond the first few vanish. IV §3 territory/property powers clip their federal ownership. Article VI separates oath holders from the oath's support object.
4. **Actors and polarity are lost.** II §3 converts the President into `Time` or `Congress Information`. IV §2 misses the charged person and required executive demand. IV §3, V, and VI turn negative prohibitions into positive fragments with the wrong actor.
5. **The IV §2 annotation boundary is corrected.** Separate Privileges and Immunities gold entries now map to `f0/o0` and `f1/o0` respectively.

## Complete gold-ID decision ledger

`M` = semantic match; `G` = gap. An `f/o` citation names an offered option. Grouped IDs share the same decisive finding.

### `article-2-section-2` — 2/29

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `ii2-commander-army`, `ii2-commander-navy`, `ii2-commander-militia` | G | f0–2 copy the pardon-only impeachment exception; militia also lacks the actual-service trigger. |
| `ii2-written-opinion`, `ii2-opinion-subject` | G | No opinion frame or offered written-opinion/Duties relation. |
| `ii2-reprieves`, `ii2-pardons` | G | f3/o0 joins two grant objects; f3/o2 isolates Reprieves but drops the United States-offences scope. No atomic option preserves each full grant. |
| `ii2-impeachment-exception` | G | f3 encodes the exclusion only as a positive grant with an exception; no negative impeachment-specific option. |
| `ii2-treaty-making`, `ii2-treaty-threshold`, `ii2-senate-treaty-advice-consent` | G | f4 has President/power/advice and consent but omits the two-thirds-of-present threshold; f5 assigns concurrence to Consent, not Senators. |
| `ii2-nominate-ambassadors` | M | f8/o0. |
| `ii2-nominate-public-ministers`, `ii2-nominate-supreme-judges`, `ii2-nominate-other-officers` | G | f8 clips the distinct office title or, for other Officers, the not-otherwise-provided and established-by-Law limits. |
| `ii2-nominate-consuls` | M | f8/o13. |
| `ii2-appoint-ambassadors`, `ii2-appoint-public-ministers`, `ii2-appoint-consuls`, `ii2-appoint-supreme-judges`, `ii2-appoint-other-officers`, `ii2-senate-appointment-advice-consent` | G | f9 has appointment fragments but never carries Senate advice and consent; several office objects and other-Officer limits also clip. |
| `ii2-inferior-officers-vesting`, `ii2-inferior-officers-president`, `ii2-inferior-officers-courts`, `ii2-inferior-officers-department-heads` | G | f10 has partial vesting objects; no option retains the inferior-Officer appointment, by-Law means, and selected recipient together. |
| `ii2-recess-vacancies`, `ii2-recess-commissions`, `ii2-recess-expiry` | G | f11 offers President/authorized_to/fill up all Vacancies without Senate-recess scope; no commission-grant or next-session-expiry edge. |

### `article-2-section-3` — 0/9

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `ii3-state-union`, `ii3-recommend` | G | No State-of-the-Union information or recommendation frame. |
| `ii3-convene-both`, `ii3-convene-either` | G | f0–1 extract adjourn/think fragments, not convening on extraordinary Occasions. |
| `ii3-adjourn` | G | f0 has Congress/Information as actor and omits both the House-disagreement trigger and President-chosen time. |
| `ii3-receive-ambassadors`, `ii3-receive-ministers` | G | f2–3 say Time receives the diplomats; President actor is absent. |
| `ii3-take-care` | G | f4 has Time taking “Care that the Laws be faithfully” and clips execution and President. |
| `ii3-commission` | G | f6 offers Congress Information/commission/Officers, with wrong actor; f5 is another malformed fragment. |

### `article-3-section-2` — 4/36

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `iii2-judicial-power-constitution-law`, `iii2-judicial-power-constitution-equity`, `iii2-judicial-power-federal-laws-law`, `iii2-judicial-power-federal-laws-equity`, `iii2-judicial-power-treaties-law`, `iii2-judicial-power-treaties-equity` | G | f0–4 split Cases, Law, Equity, and arising-under source; no option binds a Case type to its constitutional, federal-law, or treaty basis. |
| `iii2-judicial-power-ambassadors` | M | f5/o0. |
| `iii2-judicial-power-public-ministers`, `iii2-judicial-power-consuls` | G | f6–7 offer the diplomat alone, without “Cases affecting.” |
| `iii2-judicial-power-admiralty` | M | f8/o4: judicial Power extends to Cases of admiralty; an atomic equivalent of admiralty-jurisdiction cases. |
| `iii2-judicial-power-maritime` | G | f8/o0 joins admiralty and maritime; f8/o14 says only maritime Jurisdiction and loses Cases. No atomic maritime-cases option. |
| `iii2-judicial-power-us-party` | M | f9/o0. |
| `iii2-judicial-power-between-states` | M | f10/o0. |
| `iii2-judicial-power-state-other-state-citizens`, `iii2-judicial-power-different-states-citizens`, `iii2-judicial-power-same-state-land-grants`, `iii2-judicial-power-state-foreign-states`, `iii2-judicial-power-state-foreign-citizens`, `iii2-judicial-power-state-foreign-subjects`, `iii2-judicial-power-state-citizens-foreign-states`, `iii2-judicial-power-state-citizens-foreign-citizens`, `iii2-judicial-power-state-citizens-foreign-subjects` | G | No judicial-Power/extends-to option for these controversy pairings; f11 is Citizens/claim/Lands, not jurisdiction. |
| `iii2-original-ambassadors`, `iii2-original-public-ministers`, `iii2-original-consuls`, `iii2-original-state-party` | G | f19/o0 gives only supreme Court/has/original Jurisdiction, omitting the required Case category; f12–18 extract irrelevant case fragments. |
| `iii2-appellate`, `iii2-appellate-law`, `iii2-appellate-fact`, `iii2-appellate-exceptions`, `iii2-appellate-regulations` | G | f21 gives generic appellate jurisdiction or Law/Fact but not other-Cases scope or congressional Exceptions/Regulations; no Congress/may-make edge. |
| `iii2-jury`, `iii2-impeachment-exception` | G | No jury-trial relation or negative impeachment exception option. |
| `iii2-trial-in-state`, `iii2-trial-outside-state`, `iii2-congress-direct-trial-place` | G | f22 has State venue but condition copies the jury/impeachment clause; f23 makes Trial “committed” and never encodes Congress-directed out-of-State venue. |

### `article-4-section-2` — 2/9

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `iv2-privileges` | M | f0/o0: Citizens of each State entitled to Privileges of Citizens in the several States. |
| `iv2-immunities` | M | f1/o0: Citizens of each State entitled to Immunities of Citizens in the several States. |
| `iv2-fugitive-treason`, `iv2-fugitive-felony`, `iv2-fugitive-other-crime` | G | f2–12 extract charged/flee/delivered fragments with wrong actors or no demand, flight, destination, and delivery relation. |
| `iv2-fugitive-demand`, `iv2-fugitive-removal` | G | No executive-demand edge; f11 has “up”/removed-to/State and loses the Person, jurisdictional destination, and demand. |
| `iv2-service-no-discharge` | G | f13 negates escaping rather than discharge; f14 has positive discharge and wrong subject. |
| `iv2-service-delivery` | G | f15 has partial delivered/up-on-Claim objects, but modality is absent and the claimant/due-service condition never completes. |

### `article-4-section-3` — 0/12

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `iv3-admit-new-states` | G | f0 has a passive admission option, but its condition wrongly imports the intra-State formation consent rule. |
| `iv3-form-within-state`, `iv3-junction-states`, `iv3-junction-parts` | G | f1–3 lose the negative prohibition and/or split the junction object; their consent condition is not enough to repair polarity. |
| `iv3-state-legislature-consent`, `iv3-congress-consent` | G | No correctly scoped consent requirement; f3 is “New States/concerned_as/…” |
| `iv3-dispose-territory`, `iv3-dispose-property`, `iv3-rules-territory`, `iv3-rules-property` | G | f4 only offers “dispose”; f5 clips the object before the full Territory or other Property belonging-to-United-States scope. |
| `iv3-us-claims`, `iv3-state-claims` | G | f6–8 make Congress the actor and use positive construed_as, losing Constitution subject and negative polarity. |

### `article-5` — 0/13

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `v-congress-propose`, `v-house-threshold` | G | f1–2 separate two-thirds deeming from proposal and attach both future amendment provisos as conditions; no correctly scoped proposal option. |
| `v-state-applications`, `v-convention-call`, `v-convention-proposal` | G | f3 gives Congress/call/Convention, but no two-thirds State applications trigger; no State-legislature application or Convention-proposes edge. |
| `v-ratify-legislatures`, `v-ratify-conventions`, `v-legislature-ratification-threshold`, `v-convention-ratification-threshold` | G | f4 says Congress/ratified_by/Legislatures; no amendment-validity relation, three-fourths threshold, convention branch, or selected mode. |
| `v-congress-mode` | G | f5 says Congress/proposed_by/Congress, not congressional choice of ratification mode. |
| `v-pre1808-first`, `v-pre1808-fourth` | G | f6–8 misassign actor and polarity; no negative pre-1808 amendment effect on each protected clause. |
| `v-equal-suffrage` | G | f9 makes Congress the deprived actor and keeps positive polarity; State consent protection is absent. |

### `article-6` — 1/18

| Gold ID(s) | Result | Candidate or decisive gap |
|---|:---:|---|
| `vi-debts`, `vi-engagements` | G | f0–1 extract contracting/entry, not continuing validity against the United States under the Constitution. |
| `vi-supreme-constitution`, `vi-supreme-laws`, `vi-supreme-treaties-made`, `vi-supreme-treaties-future` | G | f2–4 lack the correct Constitution/Laws/Treaties subject → supreme-Law relation with Pursuance or Authority scope. |
| `vi-state-judges-bound` | M | f5/o0; “thereby” resolves to the preceding supreme-Law subjects in the same provision. |
| `vi-state-constitution-contrary`, `vi-state-law-contrary` | G | f5 has Judges/bound/thereby but no negative non-displacement rule for contrary State constitutions or laws. |
| `vi-oath-senators`, `vi-oath-representatives`, `vi-oath-state-legislators`, `vi-oath-federal-executive`, `vi-oath-federal-judicial`, `vi-oath-state-executive`, `vi-oath-state-judicial` | G | f6–9 fragment the enumerated officeholders; none binds the proper holder to an oath or affirmation to support the Constitution. |
| `vi-no-religious-test-office`, `vi-no-religious-test-trust` | G | f10 uses wrong State actor and positive requires; religious Test and negative polarity are absent. |

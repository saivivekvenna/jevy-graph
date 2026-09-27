# Oracle Choice diagnostic policy

This is a Codex-reviewed **development** component test. An audited complete
interpretation is supplied as an option in most packets. It measures whether
Jev recognizes that interpretation among realistic errors. It does not measure
whether JevyGraph can generate the correct option, production recall, or the
held-out release bar. Packets with no complete option test rejection.

## Complete claim representation

A complete claim preserves the actor, relation, target, polarity, modality,
material condition, comparator, time anchor, and attribution stated in its
source. These packets use one self-contained structured record per option.
For future graph scoring, the same information may instead be in an event
record with **explicit** links to structured context records. Resolve those
links before matching the claim. Do not infer an attachment from nearby
evidence text alone. Keep the existing strict single-record score beside any
future linked-record score; changing representation is not an extraction gain.

## Source conflicts

Judge source-local support, claim completeness, and document agreement
separately. If Results asserts X and a caption asserts its opposite, both
source-local statements can be faithful when each is attributed to its
location. Flag the cross-document conflict separately. A contradicted
source-local statement is not automatically an unsupported extraction.
Unsupported relationships, omitted material qualifiers, and an invented
resolution of a conflict still fail this diagnostic.

## Choice scoring

Each packet has four alternatives with identical structured fields and a
`reject` choice. Jev sees the source excerpt and shuffled alternatives, but
does not receive labels, error types, or adjudication rationales. Count a
packet correct only when it chooses the audited complete alternative, or
`reject` when none is complete. Report results per failure type and actual
request/token usage. Do not tune the prompt or rerun selections to improve
this development score.

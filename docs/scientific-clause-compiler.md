# Scientific claim compiler

Scientific prose is represented as typed claims rather than flattened triples.
The dependency parser locates bounded source spans; deterministic grammar maps
those spans into candidate roles; Jev resolves only genuine ambiguity.

## Claim model

A claim contains:

- one of six types: attribute, directional effect, comparison, causality,
  association, or null result;
- required subject, relation, and object fields;
- optional comparison, conditions, measurements, modality, polarity, and
  attribution;
- the original evidence and source offsets.

A claim missing any required field is rejected. Procedures, figure references,
and narrative transitions remain in the source and trace output without becoming
claims.

## Pipeline

1. Segment the document into source-labelled factual clauses.
2. Classify each clause as a finding, procedure, purpose, heading, interpretation,
   or mixed clause.
3. Locate predicate anchors and dependency-bound argument spans.
4. Apply reusable grammatical constructions for active, passive, comparative,
   causal, associative, negative, and measured-attribute statements.
5. Bind comparison, condition, measurement, negation, modality, and attribution
   before claim assembly.
6. Copy singleton slots locally. Ask Jev only about ambiguous slots, always with
   a `none` choice.
7. Reject incomplete records and verify support, boundaries, qualifiers,
   atomicity, and instruction scope.
8. Emit the claim graph and its RDF projection.

## Invariants

- Every field is licensed by a source span or explicit local context.
- Reporting wrappers and procedure nouns cannot become scientific actors.
- Measurements and comparisons remain structured fields unless they are the
  actual value of an attribute.
- Coordination expands only when the grammar licenses the pairing.
- Context cannot cross a section or conflicting intervention boundary.
- Each emitted record contains one atomic claim.
- A failed construction produces a traceable miss instead of a loose Cartesian
  product.

## Parser boundary

The parser proposes spans and grammatical roles. It does not generate facts.
Relation normalization comes from a bounded dictionary, and Jev can select
`none` when the offered reading is unsupported.

Legal provisions, general prose, tables, and equations continue through their
simpler extraction routes.

## Verification

Run the local scientific tests with the optional parser environment:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_dependency_scientific -q
```

Run the frozen unseen literature audit with:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dependency_unseen.py
```

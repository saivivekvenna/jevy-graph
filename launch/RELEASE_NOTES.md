# Jevy Graph

Jevy Graph compiles documents into evidence-linked knowledge graphs and RDF. It
creates deterministic source-derived choices, uses Jev only for ambiguity and
verification, and retains boundaries, qualifiers, attribution, and provenance.

## Included

- dependency-free core CLI and Python API;
- ordinary prose assembly with pronoun continuity, coordinated predicates,
  negation, time, price, deadline, and condition handling;
- typed scientific claims for attributes, effects, comparisons, causality,
  associations, and null results;
- legal provision assembly and complete Codex-reviewed Constitution fixtures;
- structured tables, measurements, equations, PDF, DOCX, Markdown, CSV, and
  UTF-8 text input;
- natural-language graph scope plus grouping by source, entity, or relation;
- source-grounded RDF with evidence and verification scores;
- a streaming upload demo, container definition, and health endpoint; and
- a frozen cross-domain benchmark with stage-level loss and usage reporting.

The current offline benchmark reaches all 1,267 reviewed claims across 104
active fixtures. This is deterministic candidate coverage. Final precision and
recall remain gated on sufficient independently human-reviewed held-out data.

```bash
python -m pip install jevy-graph
printf 'Alice founded Acme.' | jevy-graph --no-verify
```

Jev verification requires `TYPESAFE_API_KEY`. Scanned PDFs require an OCR step
before upload. External entity linking and ontology alignment are outside this
release.

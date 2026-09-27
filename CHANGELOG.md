# Changelog

## Unreleased

- Added instruction-aware scope filtering and graph organization by source,
  entity, or relation.
- Added qualified claim records for scientific findings, legal provisions,
  ordinary prose, measurements, and structured tables.
- Added a conservative prose clause assembler for coordinated predicates,
  pronouns, negation, dates, prices, deadlines, and conditions.
- Added the frozen cross-domain claim benchmark, stage-level loss tracing, and
  the complete Codex-reviewed Constitution inventory.
- Reduced Jev payload duplication and preserved explicit rejection reasons in
  benchmark output.
- Added container deployment, environment-based server binding, and `/healthz`.

## 0.1.0 - 2026-09-22

Initial public release.

- Deterministic extraction of bounded subject/predicate/object candidates from
  prose, lists, tables, equations, and measurements.
- Jev-backed candidate selection and independent support and entity-boundary
  verification.
- Source-grounded RDF/Turtle output with evidence, provenance, polarity, and
  calibrated scores.
- Dependency-free Python API and CLI.
- Local streaming graph demo with PDF, DOCX, Markdown, CSV, and text uploads.
- Cancellation-aware parallel batching and compact processing for large
  documents.

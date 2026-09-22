# Jevy Graph v0.1.0

Jevy Graph compiles documents into source-grounded RDF. It deterministically
generates candidate relationships, uses Jev to resolve ambiguity, independently
verifies each selected claim, and emits RDF with evidence and provenance.

The first release includes:

- CLI and Python API with no runtime Python dependencies
- extraction from prose, lists, tables, equations, and measurements
- source spans, modality, negation, conditions, sections, and page context
- direct semantic edges plus reified provenance statements
- a local streaming graph demo for PDF, DOCX, Markdown, CSV, and text files
- cancellation-aware parallel processing for large documents

Install after the PyPI release is live:

```bash
python -m pip install jevy-graph
```

Jev-backed verification requires a TypeSafe API key. Deterministic extraction can
be tried without a key:

```bash
printf 'Alice founded Acme.' | jevy-graph --no-verify
```

Known limits: no external entity linking, ontology alignment, OCR, or scanned-PDF
support. The demo is local-only and is not hardened for public uploads.

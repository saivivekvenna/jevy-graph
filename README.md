# jevy-graph

A minimal compiler from plain text to source-grounded RDF. It deterministically
builds a bounded lattice of entity boundaries and normalized predicates, asks
Jev to select the best combination, then verifies the resulting claims.

The project is an MVP: it favors inspectable behavior, parallel batches, and
source-grounded output.

## Pipeline

1. Inspect layout-preserving PDF text for tables, equations, assignments,
   measurements, page boundaries, and scientific section headings.
2. Compile table cells and explicit measurements into atomic frames with stable
   predicates, typed values, row/header context, and cell-level provenance.
3. Clean the remaining prose, preserve paragraph boundaries, and normalize
   document-declared acronyms and harmless entity variants.
4. Split prose into sentences and semicolon-delimited clauses.
5. Discover explicit, passive, modal, and negated relations; expand coordinated
   subjects, objects, actions, and inherited list structures.
6. Enumerate up to 64 subject and object spans and rank up to 32 complete RDF
   triple candidates per relation frame.
7. Ask Jev a comparative `Choice` question for every ambiguous frame.
8. Verify selected triples with parallel `Noul` questions for exact support and
   entity quality. Apply stricter evidence floors to open-verb discoveries than
   to deterministic semantic and grammatical patterns. Network batches run
   concurrently.
9. Emit Turtle with evidence, calibrated scores, modality, polarity, normalized
   offsets, source units, table/page locators, conditions, extraction origin,
   stable predicates, and conservative literal typing. Negated claims are
   reified without asserting their positive triples.

Frames with only one valid normalized triple bypass comparative selection but
still receive full support and entity-quality verification. Ambiguous choices
are sent in batches of 24, verification in batches of 40, with up to twelve
requests in flight. The bounded batches keep dense table evidence below API
payload limits without serializing the document pipeline.

## Run

Requires Python 3.11 or newer.

```bash
python -m pip install -e .
cp .env.example .env
# Add your TypeSafe key to .env.

jevy-graph input.txt -o graph.ttl
```

For a deterministic smoke test without an API call:

```bash
printf 'Alice founded Acme. Acme is located in Toronto.' \
  | jevy-graph --no-verify
```

Each accepted relationship is emitted together with an `rdf:Statement` carrying
its source clause, selection scores, support probability, entity-quality
probability, modality, and polarity. The default acceptance floors are `0.45`
support, `0.10` entity quality, and `0.70` combined; change them with
`--threshold`, `--entity-threshold`, and `--joint-threshold`. The combined score
keeps precise action-valued claims without accepting candidates that are weak
on both support and boundaries. Open-verb discoveries additionally require
`0.50` support, `0.20` entity quality, and `0.80` combined.

## Test

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Demo interface

A monochrome graph demo lives in [`demo/`](demo/). It sends file uploads to the
real compiler, adds verified claims as they arrive, and shows the source
sentence for every hovered edge. Run it locally with:

```bash
PYTHONPATH=src python3 -m jevy_graph.demo_server
```

Then open <http://localhost:8080/demo/>. PDF, DOCX, and UTF-8 text-like files are
supported. The Jev API key remains in the server-side `.env` file.

## Current scope

- UTF-8 plain text input
- layout-aware table, equation, assignment, and benchmark-value extraction
- scientific and legal source-section detection without schema crossover
- open modal and morphological predicate discovery
- coordination and legal-list expansion
- local pronoun recovery and conservative entity normalization
- concurrent Jev selection and verification
- Turtle output with provenance, modality, polarity, and typed numeric literals
- source-unit, page/table locator, condition, and extraction-origin metadata
- recall fixtures for legal, scientific, and general prose

The CLI expects UTF-8 text extracted from PDFs; the demo server also accepts
binary PDFs through the system `pdftotext` utility. Repeated headers, page
numbers, and hard wraps are cleaned automatically. External knowledge-base
linking remains out of scope, and entity linking stays conservative unless the
document declares an alias explicitly.

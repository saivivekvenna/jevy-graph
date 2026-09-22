# Jevy Graph

[![CI](https://github.com/saivivekvenna/jevy-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/saivivekvenna/jevy-graph/actions/workflows/ci.yml)

Jevy Graph compiles documents into source-grounded RDF. It discovers atomic
relations locally, asks [Jev](https://typesafe.ai/) to resolve ambiguous entity
boundaries and predicates, verifies every selected claim, and emits Turtle with
evidence and provenance.

The compiler is designed for high-recall extraction from ordinary prose,
scientific papers, legal text, tables, measurements, and equations. It does not
require an ontology or a document-specific schema.

## Features

- Multiple atomic claims from one sentence, clause, list, or table row
- Normalized entities and stable predicates without external entity linking
- Modality, negation, conditions, sections, pages, and evidence spans preserved
- Jev selection and verification streamed in parallel batches
- RDF statements with calibrated support and entity-quality scores
- CLI, Python API, and a real-time Cytoscape demo
- No runtime Python dependencies

## How it works

```text
document
  -> deterministic clause, table, equation, and measurement extraction
  -> bounded subject / predicate / object candidates
  -> Jev candidate selection
  -> Jev support and boundary verification
  -> thresholding and deduplication
  -> source-grounded RDF/Turtle
```

Jev never invents free-form graph text. It chooses among candidates generated
from the document, then independently scores the selected relationship. Frames
with one valid interpretation skip the selection call but are still verified.

## Quick start

Jevy Graph requires Python 3.11 or newer and a TypeSafe API key.

```bash
git clone https://github.com/saivivekvenna/jevy-graph.git
cd jevy-graph
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Add your key to `.env`:

```dotenv
TYPESAFE_API_KEY=your-key-here
```

Compile UTF-8 text to Turtle:

```bash
jevy-graph document.txt -o graph.ttl
```

For a local-only extraction smoke test that does not call Jev:

```bash
printf 'Alice founded Acme. Acme is located in Toronto.' \
  | jevy-graph --no-verify
```

## Demo

The demo accepts PDF, DOCX, Markdown, CSV, and plain-text files. Normal uploads
stream verified claims as their Jev batches finish. Documents that produce at
least 2,000 relation frames use larger compute batches and mount the completed
graph once. Selection and verification overlap across batches; every emitted
claim still passes both support and entity-boundary checks. Large uploads send
fixed candidate fields once per question instead of repeating them in every
option. No candidate options are removed by this encoding.

Starting a new upload cancels the previous request. Already running Jev calls
may finish, but pending batches stop when the server detects the disconnect.
The final API event includes Jev-reported token usage and request/retry counts.

An elapsed timer measures upload through backend completion, excluding final
graph layout. Hover over an edge or leaf node to read its source text and triple
in the labeled footer without highlighting or hiding the rest of the graph.

```bash
jevy-graph-demo
```

Open <http://localhost:8080/demo/>. PDF support requires `pdftotext`, available
from Poppler (`brew install poppler` on macOS or `apt install poppler-utils` on
Debian and Ubuntu).

The API key stays on the server and is never sent to the browser.

## Python API

```python
import os

from jevy_graph import Thresholds, compile_text
from jevy_graph.jev import JevClient

client = JevClient(os.environ["TYPESAFE_API_KEY"])
result = compile_text(
    "Alice founded Acme.",
    client=client,
    thresholds=Thresholds(support=0.45, entity=0.10, joint=0.70),
)

print(result.turtle)
print(result.accepted)
```

Omit `client` for deterministic, unverified extraction.

## RDF model

Each accepted positive relationship is emitted as a direct semantic edge and
as an `rdf:Statement` carrying its provenance:

```turtle
<urn:jevy:entity:alice-...> <urn:jevy:relation:founded> <urn:jevy:entity:acme-...> .

<urn:jevy:claim:...> a rdf:Statement ;
    rdf:subject <urn:jevy:entity:alice-...> ;
    rdf:predicate <urn:jevy:relation:founded> ;
    rdf:object <urn:jevy:entity:acme-...> ;
    jevy:evidence "Alice founded Acme." ;
    jevy:support "0.950000"^^xsd:decimal ;
    jevy:entityQuality "0.910000"^^xsd:decimal .
```

Negative claims are reified with `jevy:polarity "negative"` without asserting
the positive edge. Numeric values are emitted as typed literals when possible.

## Scope

The CLI reads UTF-8 text. The demo additionally converts PDF and DOCX uploads.
The extractor handles ordinary prose, legal lists, scientific sections,
layout-preserving tables, assignments, equations, and measurements.

External knowledge-base linking, ontology alignment, OCR, and scanned PDFs are
out of scope. Entity normalization is intentionally conservative unless the
document explicitly declares an alias.

## Development

```bash
python -m unittest discover -s tests -q
```

Pull requests should include a focused regression test for behavior changes.
Keep extraction deterministic and keep API credentials out of fixtures, logs,
and commits.

### Performance checks

Use a new process to measure a first upload. No graph layout or browser rendering
is included; extraction, Jev processing, and final filtering are timed separately.
The benchmark writes source-grounded claims and metrics to the ignored `out/`
directory. `--live` makes paid API calls; without it only extraction is measured.

```bash
PYTHONPATH=src python scripts/benchmark.py document.pdf \
  --live --compact --workers 12 --batch-size 48 --output out/benchmark.json
```

Use `--sample 512` for a bounded comparison, or `--reference` to run selection
for all frames before verification. Frame and candidate hashes allow checking
that an optimization preserves the entire deterministic candidate set.

Measured locally on September 21, 2026 (first upload, Python 3.14):

| Document / configuration | Accepted claims | Compute time | Reported input tokens |
| --- | ---: | ---: | ---: |
| Odyssey PDF, original implementation | ~5,150 | ~75.3s | Not recorded |
| Odyssey PDF, pipelined, original question format | 5,164 | 49.1s | 21,417,219 |
| Odyssey PDF, compact fixed fields and paced requests | 5,123 | 45.3s | 19,178,128 |
| Constitution PDF, normal streaming configuration | 449 | 3.84s | 1,221,971 |

All Odyssey configurations used 14,881 frames. The optimized extractor produced
identical frame and candidate hashes to the original. The 45.3s run included
23 rate-limit retries, so network conditions and account limits materially
affect timing. Model decisions vary between calls: claim counts are a regression
signal, not proof of complete coverage or correctness. The full uncompressed and
compact runs shared 3,950 exact claims, so matching volumes should not be read as
identical outputs. Ten-second processing of
the full Odyssey has not been demonstrated with verification preserved.

## Privacy and security

The demo binds to `127.0.0.1` by default and is intended for local use. Document
text used in Jev decisions is sent to TypeSafe's API. Review TypeSafe's policies
before processing sensitive material, and add authentication plus upload
hardening before exposing the demo server publicly.

Never commit `.env`; it is ignored by Git.

## License

[MIT](LICENSE)

# Jevy Graph

Jevy Graph turns text and document uploads into source-grounded knowledge
graphs. It builds bounded claim candidates locally, uses
[Jev](https://typesafe.ai/) to resolve ambiguous choices, verifies every
selected claim, and emits RDF/Turtle with the source evidence and qualifiers.

The core package has no runtime Python dependencies. It supports ordinary
prose, legal text, scientific findings, tables, measurements, and equations.

## Claim model

Simple statements become subject–relation–object edges. Claims can also retain
the structure that a flat triple would lose:

```text
Claim
├── subject
├── relation
├── object
├── comparison
├── conditions
├── measurements
├── polarity and modality
├── attribution
└── evidence and source location
```

For ordinary and legal prose, the clause assembler carries unambiguous actors
across coordinated predicates and pronouns while keeping dates, prices,
conditions, deadlines, and negation out of entity names. Scientific findings
use six reusable claim types: `attribute`, `directional_effect`, `comparison`,
`causality`, `association`, and `null_result`.

## Pipeline

```text
document conversion
  -> section, sentence, and clause segmentation
  -> deterministic claim and slot candidates
  -> optional local scientific dependency parsing
  -> Jev selection with an explicit none choice
  -> support, boundary, qualifier, atomicity, and scope checks
  -> evidence-linked claim graph and RDF projection
```

Fixed slots skip Jev selection. Ambiguous slots contain bounded source-derived
options. Every emitted claim is checked against its original evidence.

## Install

Jevy Graph requires Python 3.11 or newer.

```bash
python -m pip install jevy-graph
export TYPESAFE_API_KEY=your-key-here
```

The optional local scientific parser uses scispaCy:

```bash
python -m pip install 'jevy-graph[scientific-parser]'
# Install a compatible model such as en_core_sci_sm.
```

## Use

Compile a document with Jev verification:

```bash
jevy-graph document.txt -o graph.ttl
```

Inspect deterministic extraction without making paid calls:

```bash
jevy-graph document.txt --no-verify -o graph.ttl
```

Focus and organize the graph with natural language:

```bash
jevy-graph paper.txt \
  --instruction 'Include biological functions and causal findings; exclude routine procedures. Group by relation type.' \
  --claims-output claims.json \
  -o graph.ttl
```

Supported organization views are source section, subject entity, and relation
type. With no instruction, the pipeline extracts all source-supported claims.

### Python API

```python
import os

from jevy_graph import compile_text
from jevy_graph.jev import JevClient

client = JevClient(os.environ["TYPESAFE_API_KEY"])
result = compile_text(
    "Alice founded Acme in 2021.",
    client=client,
    instruction="Focus on organization roles; group by subject entity.",
)

print(result.accepted)
print(result.turtle)
```

## RDF output

Every accepted relation is represented by a `jevy:Claim` and `rdf:Statement`.
Unqualified positive relations also receive a direct semantic edge. Qualified
claims keep evidence, offsets, source section, polarity, modality, comparison,
conditions, measurements, attribution, and verification scores.

```turtle
<urn:jevy:claim:...> a jevy:Claim, rdf:Statement ;
    rdf:subject <urn:jevy:entity:natacl6-...> ;
    rdf:predicate <urn:jevy:relation:has-ionic-conductivity> ;
    rdf:object <urn:jevy:entity:3-3-ms-cm-1-...> ;
    jevy:claimType "attribute" ;
    jevy:condition "at 300 K" ;
    jevy:measurement "3.3 mS cm−1" ;
    jevy:evidence "NaTaCl6 has an ionic conductivity of 3.3 mS cm−1 at 300 K." .
```

## Demo and deployment

Run the local upload demo:

```bash
jevy-graph-demo --scientific-parser
```

Open <http://localhost:8080/demo/>. The demo accepts UTF-8 text, Markdown, CSV,
DOCX, and text-based PDFs. PDF conversion requires Poppler's `pdftotext`. The
TypeSafe key stays on the server.

The included container runs the dependency-light demo and installs Poppler:

```bash
docker build -t jevy-graph .
docker run --rm -p 8080:8080 \
  -e TYPESAFE_API_KEY="$TYPESAFE_API_KEY" jevy-graph
curl http://localhost:8080/healthz
```

`HOST` and `PORT` are configurable environment variables. The default
container values are `0.0.0.0` and `8080`.

## Benchmark

The benchmark is a frozen claim audit rather than a claim-count test. Each gold
claim records its evidence, subject, relation, object, polarity, modality,
condition, attribution, source unit, and instruction scope. Held-out fixtures
are hash-locked in `benchmarks/test-manifest.json`. Reports trace losses through
source conversion, frame generation, candidate generation, Jev selection,
verification, and final filtering.

The current offline suite evaluates 104 active fixtures. It contains 1,267
in-scope reviewed claims and complete Codex review of all 74 substantive units
in the frozen U.S. Constitution.

| Domain | Fixtures | Reviewed claims reached by candidates | Known-claim coverage |
| --- | ---: | ---: | ---: |
| Biomedical | 20 | 240/240 | 100% |
| Legal | 76 | 919/919 | 100% |
| General prose | 4 | 62/62 | 100% |
| Structured data | 4 | 46/46 | 100% |

These numbers measure whether a reviewed answer is present in the deterministic
choices available to Jev. They do not claim 100% final precision: unmatched
outputs require adjudication, and the independent human-reviewed held-out set
is still too small in biomedical, legal, and general prose. The release gate is
at least 95% precision and recall in every domain and instruction profile, with
zero unsupported critical claims. Precision and recall remain unreported until
that review requirement is satisfied.

Run the no-cost candidate audit:

```bash
PYTHONPATH=src python3 scripts/evaluate.py \
  --output out/quality-offline.json
```

Run the verified benchmark when paid Jev calls are intended:

```bash
PYTHONPATH=src python3 scripts/evaluate.py --live \
  --output out/quality-live.json
```

The untouched five-paper dependency-parser check currently emits 57 structured
claims for 66 audited targets, with 10 exact raw label matches. Reproduce that
separate generalization check without paid calls:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dependency_unseen.py
```

See [`benchmarks/README.md`](benchmarks/README.md) for annotation and
adjudication rules and [`benchmarks/RESULTS.md`](benchmarks/RESULTS.md) for the
current benchmark snapshot.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
python3 -m build
```

Keep extraction deterministic, preserve the exact supporting text, and add a
focused regression case for every behavior change.

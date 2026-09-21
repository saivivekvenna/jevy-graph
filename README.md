# jevy-graph

A minimal compiler from plain text to source-grounded RDF. It deterministically
builds a bounded lattice of entity boundaries and normalized predicates, asks
Jev to select the best combination, then verifies the resulting claims.

The project is an MVP: it favors inspectable behavior, fast batches, and
conservative output over broad language coverage.

## Pipeline

1. Normalize text and document-declared acronyms.
2. Detect relation-bearing clauses with deterministic patterns.
3. Enumerate up to 48 subject and 48 object spans per relation, including modal
   forms such as `Congress shall` and their canonical alternatives.
4. Rank and normalize up to 96 complete subject-predicate-object candidates.
5. Ask one Jev `Choice` question to select a complete triple, retaining its
   probability and confidence. The API model version is pinned for repeatable
   evaluations.
6. Ask four independent Jev `Noul` questions for explicit support, direction,
   factuality, and entity-label quality.
7. Emit accepted triples as Turtle with source evidence and probabilities.

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
its source sentence and all Jev decision scores. Support, direction, and
factuality default to `0.80`; entity quality defaults to `0.35`. Change them
with `--threshold` and `--entity-threshold`.

## Test

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Current scope

- UTF-8 plain text input
- bounded deterministic span and predicate lattices
- document-declared acronym normalization
- batched Jev resolution and verification
- Turtle output with provenance

PDF parsing, coreference resolution, open-ended predicate discovery, and global
entity linking are intentionally outside this first MVP.

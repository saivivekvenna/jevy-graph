# jevy-graph

A minimal compiler from plain text to source-grounded RDF. It extracts a small,
deterministic set of candidate relations and asks Jev to verify them in batches.

The project is an MVP: it favors inspectable behavior and conservative output
over broad language coverage.

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
its source sentence and Jev support/factuality probabilities. The default
threshold is `0.80`; change it with `--threshold`.

## Test

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Current scope

- UTF-8 plain text input
- conservative, inspectable relation patterns
- document-declared acronym normalization
- batched Jev verification
- Turtle output with provenance

PDF parsing, coreference resolution, open-ended predicate discovery, and global
entity linking are intentionally outside this first MVP.

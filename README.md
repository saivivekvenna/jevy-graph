# jevy-graph

A minimal compiler from plain text to source-grounded RDF. It deterministically
builds a bounded lattice of entity boundaries and normalized predicates, asks
Jev to select the best combination, then verifies the resulting claims.

The project is an MVP: it favors inspectable behavior, parallel batches, and
source-grounded output.

## Pipeline

1. Clean PDF-extracted text, preserve paragraph boundaries, and normalize
   document-declared acronyms and harmless entity variants.
2. Split text into sentences and semicolon-delimited clauses.
3. Discover explicit, passive, modal, and negated relations; expand coordinated
   subjects, objects, actions, and inherited list structures.
4. Enumerate up to 64 subject and object spans and rank up to 32 complete RDF
   triple candidates per relation frame.
5. Ask Jev a comparative `Choice` question for every frame.
6. Verify selected triples with parallel `Noul` questions for exact support and
   entity quality. Apply stricter evidence floors to open-verb discoveries than
   to deterministic semantic and grammatical patterns. Network batches run
   concurrently.
7. Emit Turtle with evidence, calibrated scores, modality, polarity, normalized
   offsets, source units, conditions, extraction origin, stable predicates, and
   conservative literal typing. Negated claims are reified without asserting
   their positive triples.

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

## Current scope

- UTF-8 plain text input
- open modal and morphological predicate discovery
- coordination and legal-list expansion
- local pronoun recovery and conservative entity normalization
- concurrent Jev selection and verification
- Turtle output with provenance, modality, polarity, and typed numeric literals
- source-unit, condition, and extraction-origin metadata
- recall fixtures for legal, scientific, and general prose

Binary PDF parsing and external knowledge-base linking are not bundled. Supply
UTF-8 text extracted from PDFs; repeated headers, page numbers, and hard wraps
are cleaned automatically. Entity linking remains conservative unless the
document declares an alias explicitly.

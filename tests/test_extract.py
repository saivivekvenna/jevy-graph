from __future__ import annotations

import unittest

from jevy_graph.extract import extract_candidates
from jevy_graph.normalize import canonical_label, find_aliases


class NormalizeTests(unittest.TestCase):
    def test_explicit_acronym_alias(self) -> None:
        text = "Knowledge Graph Compiler (KGC) supports RDF. KGC uses Jev."
        aliases = find_aliases(text)
        self.assertEqual(canonical_label("KGC", aliases), "Knowledge Graph Compiler")


class ExtractTests(unittest.TestCase):
    def test_extracts_multiple_relations(self) -> None:
        candidates = extract_candidates("Alice founded Acme. Acme is located in Toronto.")
        triples = {(item.subject, item.predicate, item.object) for item in candidates}
        self.assertIn(("Alice", "founded", "Acme"), triples)
        self.assertIn(("Acme", "located_in", "Toronto"), triples)

    def test_extracts_type_relation(self) -> None:
        candidates = extract_candidates("Toronto is a city.")
        self.assertEqual(
            (candidates[0].subject, candidates[0].predicate, candidates[0].object),
            ("Toronto", "type", "city"),
        )

    def test_rejects_pronoun_subject(self) -> None:
        self.assertEqual(extract_candidates("It uses RDF."), [])

    def test_negation_is_not_part_of_subject(self) -> None:
        candidates = extract_candidates("Acme did not acquire Beta.")
        self.assertEqual(candidates[0].subject, "Acme")


if __name__ == "__main__":
    unittest.main()

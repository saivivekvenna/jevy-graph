from __future__ import annotations

import unittest

from jevy_graph.extract import extract_candidates


def triples(text: str) -> set[tuple[str, str, str]]:
    return {
        (candidate.subject, candidate.predicate, candidate.object)
        for candidate in extract_candidates(text)
    }


class RecallEvaluationTests(unittest.TestCase):
    def test_constitutional_structure_and_powers(self) -> None:
        text = (
            "Legislative Powers shall be vested in Congress. "
            "Congress shall consist of a Senate and House of Representatives. "
            "Each Senator shall have one Vote. "
            "Congress shall have Power to lay and collect Taxes, Duties; "
            "to borrow Money; to regulate Commerce. "
            "The President shall be Commander in Chief of the Army and Navy. "
            "The Vice President shall have no Vote."
        )
        expected = {
            ("Legislative Powers", "vested_in", "Congress"),
            ("Congress", "consists_of", "Senate"),
            ("Congress", "consists_of", "House of Representatives"),
            ("Senator", "has", "one Vote"),
            ("Congress", "authorized_to", "lay Taxes"),
            ("Congress", "authorized_to", "collect Taxes"),
            ("Congress", "authorized_to", "borrow Money"),
            ("Congress", "authorized_to", "regulate Commerce"),
            ("President", "commander_in_chief_of", "Army"),
            ("President", "commander_in_chief_of", "Navy"),
            ("Vice President", "has", "Vote"),
        }
        actual = triples(text)
        self.assertEqual(expected - actual, set())

    def test_scientific_relations(self) -> None:
        actual = triples(
            "BRCA1 inhibits tumor growth. Cas9 activates DNA repair. "
            "The encoder contains self-attention layers."
        )
        expected = {
            ("BRCA1", "inhibits", "tumor growth"),
            ("Cas9", "activates", "DNA repair"),
            ("encoder", "contains", "self-attention layers"),
        }
        self.assertEqual(expected - actual, set())

    def test_general_prose_relations(self) -> None:
        actual = triples(
            "Alice founded Acme. Acme acquired Beta. Beta is located in Toronto."
        )
        expected = {
            ("Alice", "founded", "Acme"),
            ("Acme", "acquired", "Beta"),
            ("Beta", "located_in", "Toronto"),
        }
        self.assertEqual(expected - actual, set())


if __name__ == "__main__":
    unittest.main()

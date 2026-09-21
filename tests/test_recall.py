from __future__ import annotations

import unittest

from jevy_graph.extract import extract_candidates


def triples(text: str) -> set[tuple[str, str, str]]:
    return {
        (candidate.subject, candidate.predicate, candidate.object)
        for candidate in extract_candidates(text)
    }


class RecallEvaluationTests(unittest.TestCase):
    def test_preserves_source_unit_and_condition(self) -> None:
        candidates = extract_candidates(
            "Article. I.\nSection. 2. If vacancies occur, Congress shall fill seats."
        )
        claim = next(candidate for candidate in candidates if candidate.predicate == "fills")
        self.assertEqual(claim.source_unit, "ARTICLE_1_SECTION_2")
        self.assertEqual(claim.condition, "If vacancies occur")

    def test_joins_sentence_across_pdf_page_break(self) -> None:
        actual = triples(
            "The accused shall enjoy the right to a public trial and to be\n\n"
            "informed of the accusation."
        )
        self.assertIn(("accused", "has_right_to", "be informed of the accusation"), actual)

    def test_expands_secure_rights_and_warrant_requirements(self) -> None:
        actual = triples(
            "The right of the people to be secure in their persons, houses, papers, "
            "and effects, against unreasonable searches and seizures, shall not be "
            "violated, and no Warrants shall issue, but upon probable cause, supported "
            "by Oath or affirmation, and particularly describing the place to be "
            "searched, and the persons or things to be seized."
        )
        secure = {
            object_
            for subject, predicate, object_ in actual
            if subject == "people" and predicate == "has_right_to"
        }
        self.assertEqual(len(secure), 4)
        self.assertIn(("Warrants", "issues_upon", "probable cause"), actual)
        self.assertIn(("probable cause", "supported_by", "Oath or affirmation"), actual)

    def test_expands_modal_action_list(self) -> None:
        actual = triples(
            "No State shall, without consent, lay a duty, keep troops, enter an "
            "agreement, or engage in war."
        )
        predicates = {predicate for subject, predicate, _ in actual if subject == "State"}
        self.assertTrue({"lays", "keep", "enter", "engage"} <= predicates)

    def test_links_repeal_to_containing_provision(self) -> None:
        actual = triples(
            "Amendment XXI.\nSection 1. The eighteenth article is hereby repealed."
        )
        self.assertIn(
            ("AMENDMENT_21_SECTION_1", "repeals", "eighteenth article"), actual
        )

    def test_expands_purpose_clause_into_atomic_claims(self) -> None:
        actual = triples(
            "We the People, in Order to form a more perfect Union, establish Justice, "
            "insure domestic Tranquility, provide for the common defence, promote the "
            "general Welfare, and secure Liberty, do ordain and establish this "
            "Constitution for the United States."
        )
        purposes = {
            object_
            for subject, predicate, object_ in actual
            if predicate == "has_purpose"
        }
        self.assertEqual(len(purposes), 6)
        self.assertIn(
            (
                "We the People",
                "ordains_and_establishes",
                "Constitution for the United States",
            ),
            actual,
        )

    def test_expands_coordinated_rights_and_inherits_prohibition(self) -> None:
        actual = triples(
            "Congress shall make no law respecting an establishment of religion, or "
            "prohibiting the free exercise thereof; or abridging the freedom of speech, "
            "or of the press; or the right of the people peaceably to assemble, and to "
            "petition the Government for a redress of grievances."
        )
        expected = {
            ("Congress", "respects", "establishment of religion"),
            ("Congress", "prohibits", "free exercise thereof"),
            ("Congress", "abridges", "freedom of speech"),
            ("Congress", "abridges", "of the press"),
            ("people", "has_right_to", "assemble"),
            (
                "people",
                "has_right_to",
                "petition the Government for a redress of grievances",
            ),
        }
        self.assertEqual(expected - actual, set())
        inherited = [
            candidate
            for candidate in extract_candidates(
                "Congress shall make no law respecting religion; or abridging speech."
            )
            if candidate.predicate == "abridges"
        ]
        self.assertEqual(inherited[0].polarity, "negative")

    def test_expands_right_and_prefatory_clause(self) -> None:
        actual = triples(
            "A well regulated Militia, being necessary to the security of a free State, "
            "the right of the people to keep and bear Arms, shall not be infringed."
        )
        expected = {
            ("well regulated Militia", "necessary_to", "security of a free State"),
            ("people", "has_right_to", "keep Arms"),
            ("people", "has_right_to", "bear Arms"),
            ("right of the people to keep and bear Arms", "type", "infringed"),
        }
        self.assertEqual(expected - actual, set())

    def test_stops_right_action_before_unpunctuated_modal(self) -> None:
        actual = triples(
            "The right of citizens to vote shall not be denied or abridged by a State."
        )
        self.assertIn(("citizens", "has_right_to", "vote"), actual)

    def test_expands_elliptical_passive_list(self) -> None:
        candidates = extract_candidates(
            "Excessive bail shall not be required, nor excessive fines imposed, "
            "nor cruel and unusual punishments inflicted."
        )
        actual = {
            (candidate.subject, candidate.predicate, candidate.object)
            for candidate in candidates
        }
        self.assertEqual(
            {
                ("excessive fines", "type", "imposed"),
                ("cruel and unusual punishments", "type", "inflicted"),
            }
            - actual,
            set(),
        )
        self.assertTrue(
            all(
                candidate.polarity == "negative"
                for candidate in candidates
                if candidate.predicate == "type"
            )
        )

    def test_expands_neither_subjects_and_exception(self) -> None:
        actual = triples(
            "Neither slavery nor involuntary servitude, except as a punishment for "
            "crime, shall exist within the United States."
        )
        expected = {
            ("slavery", "exists_in", "United States"),
            ("involuntary servitude", "exists_in", "United States"),
            (
                "involuntary servitude",
                "has_exception",
                "punishment for crime",
            ),
        }
        self.assertEqual(expected - actual, set())

    def test_inherits_relation_across_semicolon_list(self) -> None:
        actual = triples(
            "Judicial Power shall extend to cases under the Constitution; "
            "to cases affecting ambassadors; to controversies between States."
        )
        expected = {
            ("Judicial Power", "extends_to", "cases under the Constitution"),
            ("Judicial Power", "extends_to", "cases affecting ambassadors"),
            ("Judicial Power", "extends_to", "controversies between States"),
        }
        self.assertEqual(expected - actual, set())

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

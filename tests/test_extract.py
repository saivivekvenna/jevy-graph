from __future__ import annotations

import unittest

from jevy_graph.extract import clean_document, extract_candidates, extract_frames
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

    def test_rejects_deictic_singleton_subject(self) -> None:
        self.assertEqual(extract_candidates("The second is a network."), [])

    def test_negation_is_not_part_of_subject(self) -> None:
        candidates = extract_candidates("Acme did not acquire Beta.")
        self.assertEqual(candidates[0].subject, "Acme")
        self.assertEqual(candidates[0].polarity, "negative")

    def test_enumerates_boundary_and_predicate_options(self) -> None:
        frame = extract_frames(
            "The Congress shall have Power to lay and collect Taxes."
        )[0]
        self.assertIn("Congress", frame.subject_options)
        self.assertIn("authorized_to", frame.predicate_options)
        self.assertEqual(frame.modality, "shall")

    def test_expands_coordinated_actions(self) -> None:
        candidates = extract_candidates(
            "Congress shall have Power to lay and collect Taxes."
        )
        triples = {(item.predicate, item.object) for item in candidates}
        self.assertIn(("authorized_to", "lay Taxes"), triples)
        self.assertIn(("authorized_to", "collect Taxes"), triples)

    def test_atomizes_long_authority_clause_into_compact_nodes(self) -> None:
        candidates = extract_candidates(
            "Congress shall have Power to provide for organizing, arming, and "
            "disciplining, the Militia, and for governing such Part of them as may "
            "be employed in the Service of the United States, reserving authority "
            "to the States."
        )
        actions = {
            item.object for item in candidates if item.predicate == "authorized_to"
        }
        self.assertTrue(
            {"organize Militia", "arm Militia", "discipline Militia"} <= actions
        )
        self.assertTrue(all(len(action.split()) <= 14 for action in actions))

    def test_compacts_relative_detail_in_authority_node(self) -> None:
        candidates = extract_candidates(
            "Congress shall have Power to exercise exclusive Legislation in all "
            "Cases whatsoever, over such District (not exceeding ten Miles square) "
            "as may become the Seat of Government."
        )
        actions = {
            item.object for item in candidates if item.predicate == "authorized_to"
        }
        self.assertIn(
            "exercise exclusive Legislation in all Cases whatsoever, over such District",
            actions,
        )
        self.assertTrue(all(len(action.split()) <= 14 for action in actions))

    def test_discovers_general_modal_relations(self) -> None:
        candidates = extract_candidates(
            "Legislative Powers shall be vested in Congress. "
            "Congress shall consist of a Senate and House of Representatives."
        )
        triples = {(item.subject, item.predicate, item.object) for item in candidates}
        self.assertIn(("Legislative Powers", "vested_in", "Congress"), triples)
        self.assertIn(("Congress", "consists_of", "Senate"), triples)
        self.assertIn(
            ("Congress", "consists_of", "House of Representatives"), triples
        )

    def test_inherits_authority_across_semicolon_list(self) -> None:
        candidates = extract_candidates(
            "Congress shall have Power to collect Taxes; to borrow Money; "
            "to regulate Commerce."
        )
        actions = {
            item.object
            for item in candidates
            if item.predicate == "authorized_to"
        }
        self.assertTrue({"collect Taxes", "borrow Money", "regulate Commerce"} <= actions)

    def test_normalizes_quantified_entities(self) -> None:
        candidates = extract_candidates(
            "Each Senator shall have one Vote. A Senator has an office."
        )
        self.assertTrue(all(item.subject == "Senator" for item in candidates))

    def test_enumerates_internal_subject_and_object_spans(self) -> None:
        frame = extract_frames(
            "Attention mechanisms are used in conjunction with recurrent networks."
        )[0]
        self.assertIn("Attention mechanisms", frame.subject_options)
        self.assertIn("used_with", frame.predicate_options)
        self.assertIn("recurrent networks", frame.object_options)

    def test_does_not_treat_known_as_knows(self) -> None:
        self.assertEqual(extract_frames("The values are known outputs."), [])

    def test_does_not_treat_perfect_auxiliary_as_possession(self) -> None:
        frames = extract_frames("Attention mechanisms have become widely used.")
        predicates = {
            predicate for frame in frames for predicate in frame.predicate_options
        }
        self.assertNotIn("has", predicates)

    def test_strips_pdf_bullet_from_entity(self) -> None:
        candidate = extract_candidates("• The encoder contains self-attention layers.")[0]
        self.assertEqual(candidate.subject, "encoder")

    def test_joins_hard_wrapped_pdf_text(self) -> None:
        candidate = extract_candidates("Acme con-\ntains three divisions.")[0]
        self.assertEqual(
            (candidate.subject, candidate.predicate, candidate.object),
            ("Acme", "contains", "three divisions"),
        )

    def test_does_not_extract_verb_from_hyphenated_noun(self) -> None:
        frames = extract_frames(
            "Additive attention computes compatibility using a feed-forward network."
        )
        predicates = {
            predicate for frame in frames for predicate in frame.predicate_options
        }
        self.assertNotIn("feed", predicates)

    def test_rejects_numeric_table_fragment_as_subject(self) -> None:
        self.assertEqual(extract_frames("8 after training for 3."), [])

    def test_extracts_layout_table_cells_as_typed_claims(self) -> None:
        text = (
            "2 Results\n\n"
            "Table 7: Evaluation results\n\n"
            "Model        Accuracy\n"
            "Alpha        91.5\n\n\n"
            "3 Conclusion\n"
        )
        claim = next(
            item
            for item in extract_candidates(text)
            if item.subject == "Alpha" and item.predicate == "has_accuracy"
        )
        self.assertEqual(claim.object, "91.5")
        self.assertEqual(claim.object_kind, "decimal")
        self.assertEqual(claim.source_locator, "Table 7")

    def test_scientific_sections_do_not_become_amendments(self) -> None:
        claims = extract_candidates(
            "3 Model Architecture\n\nThe Transformer uses attention. "
            "As described in Section 5.3, it trains quickly."
        )
        self.assertTrue(claims)
        self.assertTrue(
            all(not (claim.source_unit or "").startswith("AMENDMENT_None") for claim in claims)
        )
        self.assertTrue(
            any((claim.source_unit or "").startswith("SECTION_3_") for claim in claims)
        )

    def test_tracks_dotted_and_split_scientific_headings(self) -> None:
        claims = extract_candidates(
            "Abstract\nAlpha uses beta.\n1.\nIntroduction\nGamma uses delta.\n"
            "2.1. Results\nEpsilon uses zeta."
        )
        units = {
            (claim.subject, claim.source_unit)
            for claim in claims
            if claim.predicate == "uses"
        }
        self.assertIn(("Alpha", "ABSTRACT"), units)
        self.assertIn(("Gamma", "SECTION_1_INTRODUCTION"), units)
        self.assertIn(("Epsilon", "SECTION_2_1_RESULTS"), units)

    def test_tracks_gutenberg_chapters_and_removes_license(self) -> None:
        text = (
            "Project metadata has restrictions.\n"
            "*** START OF THE PROJECT GUTENBERG EBOOK SAMPLE ***\n"
            "CHAPTER I. Arrival\nAlice entered Wonderland.\n"
            "*** END OF THE PROJECT GUTENBERG EBOOK SAMPLE ***\n"
            "The license permits redistribution."
        )
        cleaned = clean_document(text)
        self.assertNotIn("restrictions", cleaned)
        self.assertNotIn("redistribution", cleaned)
        claims = extract_candidates(text)
        arrival = next(item for item in claims if item.predicate == "entered")
        self.assertEqual(arrival.source_unit, "CHAPTER_1_ARRIVAL")

    def test_does_not_parse_abnf_repetition_as_numeric_assignment(self) -> None:
        claims = extract_candidates('dur-second = 1*DIGIT "S"')
        self.assertFalse(any(claim.predicate == "equals" for claim in claims))

    def test_uses_explicit_measurement_subject_outside_ml(self) -> None:
        claims = extract_candidates(
            "Standard time in the Netherlands was 19 minutes and 32.13 seconds ahead."
        )
        triples = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertIn(
            ("Standard time in the Netherlands", "has_duration_minutes", "19"),
            triples,
        )
        self.assertIn(
            ("Standard time in the Netherlands", "has_duration_seconds", "32.13"),
            triples,
        )

    def test_tracks_appendices_and_named_back_matter(self) -> None:
        claims = extract_candidates(
            "Appendix A. Grammar\nAlpha uses beta.\n"
            "Authors' Addresses\nGamma uses delta."
        )
        units = {
            (claim.subject, claim.source_unit)
            for claim in claims
            if claim.predicate == "uses"
        }
        self.assertIn(("Alpha", "APPENDIX_A_GRAMMAR"), units)
        self.assertIn(("Gamma", "AUTHORS_ADDRESSES"), units)

    def test_rejects_discourse_fragments_as_entities(self) -> None:
        candidates = extract_candidates("Here emerged a model. In fact, paint mixed colors.")
        self.assertFalse(
            any(item.subject.casefold() in {"here", "in fact"} for item in candidates)
        )

    def test_normalizes_common_open_verb_gerunds(self) -> None:
        predicates = {
            item.predicate
            for item in extract_candidates(
                "Viruses are invading cells. People were tumbling into one another."
            )
        }
        self.assertIn("invades", predicates)
        self.assertIn("tumbles_into", predicates)

    def test_preserves_decimal_benchmark_measurement(self) -> None:
        claims = extract_candidates("Our model achieves a BLEU score of 41.8.")
        self.assertIn(
            ("model", "has_bleu", "41.8"),
            {(item.subject, item.predicate, item.object) for item in claims},
        )


if __name__ == "__main__":
    unittest.main()

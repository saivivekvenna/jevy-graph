from __future__ import annotations

import json
from pathlib import Path
import unittest

from jevy_graph.extract import _clauses
from jevy_graph.provisions import (
    ProvisionState,
    assemble_provisions,
    relation_frames_from_provisions,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-8-codex-reviewed-2026-09-27.json"
)
SECTION_7_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-7-codex-reviewed-2026-09-27.json"
)
SECTION_9_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-9-codex-reviewed-2026-09-27.json"
)
SECTION_10_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-10-codex-reviewed-2026-09-26.json"
)
ARTICLE_2_SECTION_1_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-2-section-1-codex-reviewed-2026-09-26.json"
)
ARTICLE_2_SECTION_2_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-2-section-2-codex-reviewed-2026-09-27.json"
)
ARTICLE_3_SECTION_2_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-3-section-2-codex-reviewed-2026-09-27.json"
)
AMENDMENT_14_SECTION_4_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-14-section-4-codex-reviewed-2026-09-27.json"
)
AMENDMENT_14_SECTION_3_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-14-section-3-codex-reviewed-2026-09-27.json"
)
AMENDMENT_25_SECTION_4_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-25-section-4-codex-reviewed-2026-09-27.json"
)
AMENDMENT_12_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-12-codex-reviewed-2026-09-27.json"
)
ARTICLE_1_SECTION_5_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-5-codex-reviewed-2026-09-27.json"
)
ARTICLE_1_SECTION_6_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-6-codex-reviewed-2026-09-27.json"
)
ARTICLE_6_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-6-codex-reviewed-2026-09-27.json"
)
AMENDMENT_14_SECTION_2_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-14-section-2-codex-reviewed-2026-09-27.json"
)
ARTICLE_5_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-5-codex-reviewed-2026-09-27.json"
)
ARTICLE_4_SECTION_3_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-4-section-3-codex-reviewed-2026-09-27.json"
)
AMENDMENT_17_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-17-codex-reviewed-2026-09-27.json"
)
ARTICLE_2_SECTION_3_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-2-section-3-codex-reviewed-2026-09-27.json"
)
AMENDMENT_14_SECTION_1_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-14-section-1-codex-reviewed-2026-09-27.json"
)
ARTICLE_4_SECTION_2_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-4-section-2-codex-reviewed-2026-09-27.json"
)
ARTICLE_1_SECTION_4_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-article-1-section-4-codex-reviewed-2026-09-27.json"
)
AMENDMENT_23_SECTION_1_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-23-section-1-codex-reviewed-2026-09-27.json"
)
AMENDMENT_20_SECTION_3_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-20-section-3-codex-reviewed-2026-09-27.json"
)
AMENDMENT_20_SECTION_4_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "constitution-amendment-20-section-4-codex-reviewed-2026-09-27.json"
)
FAIR_USE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "span-pilot-legal-2026-09-27.json"
)
FTC_UNFAIRNESS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "fixtures"
    / "span-fresh-legal-2026-09-26.json"
)


def _key(item: object) -> tuple[object, ...]:
    if isinstance(item, dict):
        return (
            item["subject"], item["predicate"], item["object"], item["evidence"],
            item.get("modality"), item.get("polarity"), item.get("condition"),
        )
    return (
        item.subject, item.predicate, item.object, item.evidence,
        item.modality, item.polarity, item.condition,
    )


class ProvisionAssemblerTests(unittest.TestCase):
    def _assert_fixture_coverage(
        self, fixture_path: Path, expected_count: int, source_unit: str,
    ) -> None:
        fixture = json.loads(fixture_path.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(clause.text, clause.source_unit, state)
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), expected_count)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(len(actual), expected_count)
        self.assertEqual(source_units, [source_unit] * expected_count)

    def test_article_i_section_5_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            ARTICLE_1_SECTION_5_FIXTURE, 18, "ARTICLE_1_SECTION_5",
        )

    def test_amendment_xiv_section_2_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            AMENDMENT_14_SECTION_2_FIXTURE, 15, "AMENDMENT_14_SECTION_2",
        )

    def test_article_v_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(ARTICLE_5_FIXTURE, 13, "ARTICLE_5")

    def test_article_iv_section_3_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            ARTICLE_4_SECTION_3_FIXTURE, 12, "ARTICLE_4_SECTION_3",
        )

    def test_amendment_xvii_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(AMENDMENT_17_FIXTURE, 12, "AMENDMENT_17")

    def test_article_ii_section_3_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            ARTICLE_2_SECTION_3_FIXTURE, 9, "ARTICLE_2_SECTION_3",
        )

    def test_amendment_xiv_section_1_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            AMENDMENT_14_SECTION_1_FIXTURE, 12, "AMENDMENT_14_SECTION_1",
        )

    def test_article_iv_section_2_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            ARTICLE_4_SECTION_2_FIXTURE, 9, "ARTICLE_4_SECTION_2",
        )

    def test_article_i_section_4_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            ARTICLE_1_SECTION_4_FIXTURE, 9, "ARTICLE_1_SECTION_4",
        )

    def test_amendment_xxiii_section_1_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            AMENDMENT_23_SECTION_1_FIXTURE, 9, "AMENDMENT_23_SECTION_1",
        )

    def test_amendment_xx_section_3_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            AMENDMENT_20_SECTION_3_FIXTURE, 9, "AMENDMENT_20_SECTION_3",
        )

    def test_amendment_xx_section_4_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            AMENDMENT_20_SECTION_4_FIXTURE, 2, "AMENDMENT_20_SECTION_4",
        )

    def test_fair_use_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(FAIR_USE_FIXTURE, 6, "DOCUMENT")

    def test_ftc_unfairness_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(FTC_UNFAIRNESS_FIXTURE, 3, "DOCUMENT")

    def test_document_rules_require_a_source_signature(self) -> None:
        state = ProvisionState()
        self.assertEqual(
            assemble_provisions(
                "(2) the nature of the copyrighted work", "DOCUMENT", state,
            ),
            [],
        )
        self.assertEqual(
            assemble_provisions(
                "Such public policy considerations may not serve as a primary "
                "basis for such determination.",
                "DOCUMENT",
                state,
            ),
            [],
        )

    def test_article_i_section_6_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(
            ARTICLE_1_SECTION_6_FIXTURE, 18, "ARTICLE_1_SECTION_6",
        )

    def test_article_vi_has_complete_exact_candidate_coverage(self) -> None:
        self._assert_fixture_coverage(ARTICLE_6_FIXTURE, 18, "ARTICLE_6")

    def test_amendment_xii_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(AMENDMENT_12_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 32)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(len(actual), 32)
        self.assertEqual(source_units, ["AMENDMENT_12"] * 32)

    def test_article_i_section_7_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(SECTION_7_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 33)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["ARTICLE_1_SECTION_7"] * 33)

    def test_article_i_section_8_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        # Exercise the same clause-at-a-time path used by extract_frames.  This
        # catches failures to carry the opening authority into later ``To``
        # provisions as well as errors in the individual templates.
        for clause in _clauses(fixture["text"]):
            actual.extend(assemble_provisions(
                clause.text, clause.source_unit, state,
            ))
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 76)
        self.assertEqual({_key(item) for item in actual}, expected)

    def test_article_i_section_9_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(SECTION_9_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 40)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["ARTICLE_1_SECTION_9"] * 40)

    def test_article_i_section_10_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(SECTION_10_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 33)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["ARTICLE_1_SECTION_10"] * 33)

    def test_article_ii_section_1_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(ARTICLE_2_SECTION_1_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 59)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["ARTICLE_2_SECTION_1"] * 59)

    def test_article_ii_section_2_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(ARTICLE_2_SECTION_2_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 29)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["ARTICLE_2_SECTION_2"] * 29)

    def test_article_iii_section_2_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(ARTICLE_3_SECTION_2_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 36)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["ARTICLE_3_SECTION_2"] * 36)

    def test_amendment_xiv_section_4_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(AMENDMENT_14_SECTION_4_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 35)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["AMENDMENT_14_SECTION_4"] * 35)

    def test_amendment_xiv_section_3_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(AMENDMENT_14_SECTION_3_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 25)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(source_units, ["AMENDMENT_14_SECTION_3"] * 25)

    def test_amendment_xxv_section_4_has_complete_exact_candidate_coverage(self) -> None:
        fixture = json.loads(AMENDMENT_25_SECTION_4_FIXTURE.read_text())
        state = ProvisionState()
        actual = []
        source_units = []
        for clause in _clauses(fixture["text"]):
            provisions = assemble_provisions(
                clause.text, clause.source_unit, state,
            )
            actual.extend(provisions)
            source_units.extend(
                frame.source_unit
                for frame in relation_frames_from_provisions(
                    provisions,
                    context=clause.text,
                    sentence_index=0,
                    start=clause.start,
                    end=clause.end,
                    source_unit=clause.source_unit,
                )
            )
        expected = {
            _key(item) for item in fixture["gold"] if item.get("in_scope", True)
        }
        self.assertEqual(len(expected), 25)
        self.assertEqual({_key(item) for item in actual}, expected)
        self.assertEqual(len(actual), 25)
        self.assertEqual(source_units, ["AMENDMENT_25_SECTION_4"] * 25)

    def test_standalone_excerpt_is_recognized_without_a_source_locator(self) -> None:
        text = (
            "The Congress shall have Power To lay and collect Taxes, Duties, "
            "Imposts and Excises, to pay the Debts and provide for the common "
            "Defence and general Welfare of the United States"
        )
        claims = assemble_provisions(text, None, ProvisionState())
        self.assertEqual(len(claims), 11)
        self.assertIn(
            ("Congress", "has_Power_to_collect", "Excises"),
            {(item.subject, item.predicate, item.object) for item in claims},
        )

    def test_unrelated_legal_prose_does_not_activate_the_assembler(self) -> None:
        actual = assemble_provisions(
            "Congress may regulate an agency by Law.",
            "ARTICLE_2_SECTION_1",
            ProvisionState(),
        )
        self.assertEqual(actual, [])

    def test_relation_frames_preserve_provision_evidence_and_qualifiers(self) -> None:
        text = "To borrow Money on the credit of the United States"
        provisions = assemble_provisions(
            text, "ARTICLE_1_SECTION_8", ProvisionState(),
        )
        frames = relation_frames_from_provisions(
            provisions,
            context="Congress shall have Power. " + text,
            sentence_index=3,
            start=12,
            end=65,
            source_unit="ARTICLE_1_SECTION_8",
        )
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].subject_options, ("Congress",))
        self.assertEqual(frames[0].predicate_options, ("has_Power_to_borrow",))
        self.assertEqual(frames[0].object_options, ("Money",))
        self.assertEqual(frames[0].evidence, text)
        self.assertEqual(frames[0].condition, "on the credit of the United States")
        self.assertEqual(frames[0].origin, "provision")


if __name__ == "__main__":
    unittest.main()

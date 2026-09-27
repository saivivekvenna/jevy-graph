from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from jevy_graph.extract import extract_claims, extract_frames
from jevy_graph.jev import _triple_options
from jevy_graph.scientific.compiler import ScientificClauseCompiler


def signature(item) -> tuple[str, str, str, str | None]:
    return (
        item.subject.normalized,
        item.predicate,
        item.object.normalized,
        item.qualifiers.modality,
    )


class ScientificClauseCompilerTests(unittest.TestCase):
    def compile_one(self, text: str):
        compiler = ScientificClauseCompiler()
        return compiler.compile(text, source_unit="RESULTS", sentence_index=0)

    def test_active_and_passive_causal_paraphrases_are_equivalent(self) -> None:
        active = self.compile_one("GENE1 knockdown inhibited cell growth.")
        passive = self.compile_one("Cell growth was inhibited by GENE1 knockdown.")
        self.assertIn(
            ("GENE1 knockdown", "inhibits", "cell growth", "asserted"),
            {signature(item) for item in active.hypotheses},
        )
        self.assertIn(
            ("GENE1 knockdown", "inhibits", "Cell growth", "asserted"),
            {signature(item) for item in passive.hypotheses},
        )

    def test_reporting_wrapper_does_not_become_subject(self) -> None:
        result = self.compile_one(
            "The results showed that GENE1 knockdown inhibited cell growth."
        )
        signatures = {signature(item) for item in result.hypotheses}
        self.assertIn(
            ("GENE1 knockdown", "inhibits", "cell growth", "asserted"),
            signatures,
        )
        self.assertFalse(any(item.subject.normalized == "The results" for item in result.hypotheses))

    def test_negative_effect_preserves_polarity(self) -> None:
        result = self.compile_one("GENE1 knockdown did not affect GENE2 expression.")
        item = next(item for item in result.hypotheses if item.predicate == "does_not_change")
        self.assertEqual(item.subject.normalized, "GENE1 knockdown")
        self.assertEqual(item.object.normalized, "GENE2 expression")
        self.assertEqual(item.qualifiers.polarity, "negative")

    def test_structured_claim_is_canonical_scientific_output(self) -> None:
        claims = extract_claims(
            "RESULTS\nGENE1 knockdown inhibited cell growth."
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.claim_type, "causality")
        self.assertEqual(
            (claim.subject, claim.relation, claim.object),
            ("GENE1 knockdown", "inhibits", "cell growth"),
        )
        self.assertEqual(claim.evidence, "GENE1 knockdown inhibited cell growth.")

    def test_null_result_has_explicit_negation(self) -> None:
        claim = extract_claims(
            "RESULTS\nGENE1 knockdown did not affect GENE2 expression."
        )[0]
        self.assertEqual(claim.claim_type, "null_result")
        self.assertTrue(claim.negated)
        self.assertEqual(claim.polarity, "negative")

    def test_heading_clears_carried_intervention(self) -> None:
        compiler = ScientificClauseCompiler()
        compiler.compile(
            "We knocked down GENE1 in CELL-1 cells.",
            source_unit="RESULTS", sentence_index=0,
        )
        compiler.compile(
            "GENE2 promotes cell survival",
            source_unit="RESULTS", sentence_index=1,
        )
        result = compiler.compile(
            "Cell proliferation was significantly inhibited in CELL-2 cells.",
            source_unit="RESULTS", sentence_index=2,
        )
        self.assertFalse(any(item.subject.normalized == "GENE1 knockdown" for item in result.hypotheses))

    def test_frozen_eif4a3_has_at_least_51_exact_atomic_events(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "benchmarks/corpus/eif4a3-cdc5l-results.txt").read_text()
        gold = json.loads(
            (root / "benchmarks/audits/eif4a3-results-frozen-gold-2026-09-27.json").read_text()
        )["gold"]
        frames = [frame for frame in extract_frames(text) if frame.origin == "event"]

        def norm(value: str | None) -> str:
            return re.sub(
                r"\s+", " ", (value or "").casefold().replace("“", "").replace("”", ""),
            ).strip()

        actual = {
            (
                norm(frame.subject_options[0]), norm(frame.predicate_options[0]),
                norm(frame.object_options[0]), norm(frame.modality),
            )
            for frame in frames
        }
        covered = {
            item["id"] for item in gold
            if (
                norm(item["subject"]), norm(item["predicate"]),
                norm(item["object"]), norm(item["modality"]),
            ) in actual
        }
        self.assertGreaterEqual(len(covered), 51)
        self.assertEqual(set(item["id"] for item in gold) - covered, {"E020"})

    def test_five_paper_suite_compiles_all_reviewed_claims_as_singletons(self) -> None:
        root = Path(__file__).resolve().parents[1]
        audit = json.loads(
            (root / "benchmarks/audits/broad-literature-frozen-gold-2026-09-27.json")
            .read_text()
        )
        total = 0
        signatures = set()
        for document in audit["documents"]:
            frames = extract_frames((root / document["source"]).read_text())
            events = [frame for frame in frames if frame.origin == "event"]
            self.assertEqual(len(events), len(document["gold"]), document["pmcid"])
            self.assertTrue(all(len(_triple_options(frame)) == 1 for frame in events))
            total += len(events)
            signatures.update(
                (frame.subject_options[0], frame.predicate_options[0],
                 frame.object_options[0])
                for frame in events
            )
        self.assertEqual(total, 69)
        self.assertIn(("GF-B/V model", "discriminates", "B. pseudomallei"), signatures)
        self.assertIn((
            "foundation-dynamic-core representation", "generalizes_to", "new mice",
        ), signatures)


if __name__ == "__main__":
    unittest.main()

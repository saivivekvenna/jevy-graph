from __future__ import annotations

import unittest

from jevy_graph.extract import extract_claims
from jevy_graph.scientific import (
    DependencyParserUnavailable,
    DependencyScientificCompiler,
)
from jevy_graph.scientific.model import ScientificContext


class DependencyScientificCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.compiler = DependencyScientificCompiler()
        except DependencyParserUnavailable as exc:
            raise unittest.SkipTest(str(exc))

    def signatures(self, text: str):
        return {
            (
                item.subject.normalized, item.predicate, item.object.normalized,
                item.qualifiers.polarity, item.qualifiers.render(),
            )
            for item in self.compiler.compile(text, ScientificContext())
        }

    def test_reporting_wrapper_and_conjunction(self) -> None:
        actual = self.signatures(
            "The results showed that GENE1 knockdown significantly inhibited "
            "cell growth and migration in treated cells."
        )
        self.assertIn(
            ("GENE1 knockdown", "inhibits", "cell growth", "positive", "in treated cells"),
            actual,
        )
        self.assertIn(
            ("GENE1 knockdown", "inhibits", "cell migration", "positive", "in treated cells"),
            actual,
        )

    def test_passive_negation_and_comparison(self) -> None:
        passive = self.signatures(
            "Cell growth was inhibited by GENE1 knockdown under hypoxic conditions."
        )
        self.assertIn(
            ("GENE1 knockdown", "inhibits", "Cell growth", "positive", "under hypoxic conditions"),
            passive,
        )
        negative = self.signatures(
            "GENE1 knockdown did not affect GENE2 expression."
        )
        self.assertIn(
            ("GENE1 knockdown", "does_not_change", "GENE2 expression", "negative", None),
            negative,
        )
        comparison = self.signatures(
            "Patients receiving drug A had lower mortality than those receiving placebo."
        )
        self.assertIn(
            ("Patients receiving drug A", "has_lower", "mortality", "positive", "than those receiving placebo"),
            comparison,
        )

    def test_causal_nominal_and_measurement(self) -> None:
        actual = self.signatures(
            "Rising temperature caused a 20% decline in species richness."
        )
        self.assertIn(
            ("Rising temperature", "causes", "20% decline in species richness", "positive", "20%"),
            actual,
        )

    def test_claim_graph_separates_comparison_condition_and_measurement(self) -> None:
        comparison = extract_claims(
            "RESULTS\nMeplazumab reduced mortality compared with placebo.",
            scientific_dependency_compiler=self.compiler,
        )[0]
        self.assertEqual(comparison.comparison, "placebo")
        self.assertEqual(comparison.conditions, ())

        directional = extract_claims(
            "RESULTS\nDA-6 pretreatment increased chlorophyll content by 16% "
            "under drought stress.",
            scientific_dependency_compiler=self.compiler,
        )[0]
        self.assertEqual(directional.object, "chlorophyll content")
        self.assertEqual(directional.measurements, ("16%",))
        self.assertEqual(directional.conditions, ("under drought stress",))

    def test_measured_attribute_uses_value_as_object(self) -> None:
        claim = extract_claims(
            "RESULTS\nNaTaCl6 has an ionic conductivity of 3.3 mS cm−1 at 300 K.",
            scientific_dependency_compiler=self.compiler,
        )[0]
        self.assertEqual(claim.claim_type, "attribute")
        self.assertEqual(claim.subject, "NaTaCl6")
        self.assertEqual(claim.relation, "has_ionic_conductivity")
        self.assertEqual(claim.object, "3.3 mS cm−1")
        self.assertEqual(claim.conditions, ("at 300 K",))


if __name__ == "__main__":
    unittest.main()

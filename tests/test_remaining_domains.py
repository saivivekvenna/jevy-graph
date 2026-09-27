from __future__ import annotations

import unittest

from jevy_graph.extract import extract_candidates


def indexed(text: str):
    return {
        (claim.subject, claim.predicate, claim.object): claim
        for claim in extract_candidates(text)
    }


class RemainingDomainEventTests(unittest.TestCase):
    def test_compact_correlation_list_keeps_level_names_and_each_p_value(self) -> None:
        claims = indexed(
            "The TINCR expression level was reversely correlated to serosal "
            "invasion (p = 0.001), lymph metastasis (p = 0.037), and tumour "
            "node metastasis (TNM) classification (p = 0.016), while positively "
            "correlated with differentiation degree (p = 0.017)."
        )
        expected = {
            "serosal invasion": ("inversely_correlated_with", "p = 0.001"),
            "lymph metastasis": ("inversely_correlated_with", "p = 0.037"),
            "tumour node metastasis (TNM) classification": (
                "inversely_correlated_with", "p = 0.016",
            ),
            "differentiation degree": ("positively_correlated_with", "p = 0.017"),
        }
        for object_, (predicate, condition) in expected.items():
            claim = claims[("TINCR expression level", predicate, object_)]
            self.assertEqual((claim.modality, claim.condition), (None, condition))

    def test_comparative_ecology_events_keep_scope_and_negative_necessity(self) -> None:
        claims = indexed(
            "We found that plants generally benefited from soil microbes, and "
            "this benefit was greater whenever their current watering conditions "
            "matched the microbes' historical watering conditions. Principally, "
            "the plant's presence was not necessary in the historical treatments "
            "for this environmental matching benefit to emerge. Moreover, we "
            "found microbes from droughted soils could better tolerate drought stress."
        )
        benefit = claims[("soil microbes", "benefit", "plants")]
        self.assertEqual(benefit.condition, "generally; in this study")
        match = claims[(
            "matching current and historical watering conditions", "increases",
            "plant benefit from soil microbes",
        )]
        self.assertIn("relative to nonmatching conditions", match.condition)
        necessity = claims[(
            "plant presence in historical treatments", "is_necessary_for",
            "environmental matching benefit",
        )]
        self.assertEqual(necessity.polarity, "negative")
        tolerance = claims[(
            "microbes from droughted soils", "tolerate", "drought stress",
        )]
        self.assertEqual(tolerance.modality, "could")

    def test_abstract_interventions_results_and_interpretation_are_atomic(self) -> None:
        claims = indexed(
            "To this end, we used an established placebo analgesia paradigm in "
            "combination with 2 opposing pharmacological modulations of dopaminergic "
            "tone, i.e., the dopamine antagonist sulpiride and the dopamine precursor "
            "L-dopa which were both applied in an experimental, double-blind, "
            "randomized, placebo-controlled trial with a between-subject design in "
            "N = 168 healthy volunteers. The study medication successfully altered "
            "dopaminergic tone during the conditioning procedure. Contrary to our "
            "hypotheses, the medication did not modulate the formation of positive "
            "treatment expectation and placebo analgesia tested 1 day later. Placebo "
            "analgesia was no longer detectable on day 8 after conditioning. Using a "
            "combined frequentist and Bayesian approach, our data provide strong "
            "evidence against a direct dopaminergic influence on the generation and "
            "maintenance of placebo effects."
        )
        self.assertIn(("study", "used", "placebo analgesia paradigm"), claims)
        self.assertIn(("sulpiride", "is", "dopamine antagonist"), claims)
        self.assertIn(("L-dopa", "is", "dopamine precursor"), claims)
        for drug in ("sulpiride", "L-dopa"):
            applied = claims[(drug, "applied_in", "placebo analgesia trial")]
            self.assertIn("N = 168 healthy volunteers", applied.condition)
        altered = claims[("study medication", "altered", "dopaminergic tone")]
        self.assertEqual(altered.condition, "during the conditioning procedure")
        for outcome in ("formation of positive treatment expectation", "placebo analgesia"):
            self.assertEqual(
                claims[("study medication", "modulated", outcome)].polarity,
                "negative",
            )
        detectable = claims[("placebo analgesia", "detectable", "day 8 after conditioning")]
        self.assertEqual(detectable.polarity, "negative")
        for process in ("generation", "maintenance"):
            self.assertIn((
                "study data", "provide_strong_evidence_against",
                f"direct dopaminergic influence on {process} of placebo effects",
            ), claims)

    def test_copular_person_type_keeps_nationality_with_occupation(self) -> None:
        claims = indexed(
            'Wilfried "Willi" Schneider (born 13 March 1963 in Mediaș, '
            'Transylvania) is a German skeleton racer who competed from 1992 to 2002.'
        )
        self.assertIn(
            ("Wilfried Willi Schneider", "type", "German skeleton racer"),
            claims,
        )


if __name__ == "__main__":
    unittest.main()

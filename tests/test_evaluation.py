from __future__ import annotations

import unittest
from unittest.mock import patch

from jevy_graph.evaluation import output_fingerprint, quality_summary, release_gate, score_fixture
from jevy_graph.extract import extract_frames
from jevy_graph.models import CandidateTriple, RelationFrame, VerifiedTriple


class EvaluationTests(unittest.TestCase):
    def test_explicit_attribution_is_scored_separately_from_source_unit(self) -> None:
        text = "Smith et al. reported that Alice founded Acme."
        fixture = {
            "id": "cited", "domain": "general", "gold": [{
                "id": "founding", "subject": "Alice", "predicate": "founded",
                "object": "Acme", "source_unit": "ARTICLE_1",
                "attribution": "Smith et al.", "evidence": text,
            }],
        }
        base = CandidateTriple("Alice", "founded", "Acme", text, 0, 0, len(text),
                               source_unit="ARTICLE_1")
        from dataclasses import replace

        for attribution in (None, "Jones et al."):
            with self.subTest(attribution=attribution):
                candidate = replace(base, attribution=attribution)
                report = score_fixture(fixture, converted_text=text, frames=[],
                                       candidates=[candidate],
                                       verified=[VerifiedTriple(candidate, 0.9, 0.9)])
                self.assertEqual(report["metrics"]["matched"], 0)
                self.assertEqual(report["metrics"]["qualifier_errors"], {"attribution": 1})
        cited = replace(base, attribution="Smith et al.")
        report = score_fixture(fixture, converted_text=text, frames=[],
                               candidates=[cited], verified=[VerifiedTriple(cited, 0.9, 0.9)])
        self.assertEqual(report["metrics"]["matched"], 1)

    def test_reports_generation_loss_without_claiming_precision(self) -> None:
        fixture = {
            "id": "probe", "domain": "general", "review_status": "provisional",
            "annotation_scope": "targeted", "gold": [{
                "id": "missing", "subject": "Alice", "predicate": "owns",
                "object": "Acme", "evidence": "Alice owns Acme",
            }],
        }
        text = "Alice owns Acme."
        report = score_fixture(
            fixture, converted_text=text, frames=[], candidates=[], verified=[]
        )
        self.assertEqual(report["losses"][0]["stage"], "frame_generation")
        self.assertIsNone(report["metrics"]["precision"])
        self.assertFalse(release_gate([report])["passes"])

    def test_one_to_one_matching_and_qualifier_audit(self) -> None:
        fixture = {
            "id": "legal", "domain": "legal", "review_status": "human_reviewed",
            "annotation_scope": "exhaustive", "gold": [{
                "id": "prohibition", "subject": "Congress", "predicate": "acquires",
                "object": "Acme", "evidence": "Congress shall not acquire Acme",
                "polarity": "negative", "modality": "shall", "condition": None,
            }],
        }
        text = "Congress shall not acquire Acme."
        candidate = CandidateTriple("Congress", "acquires", "Acme", text, 0, 0, len(text), modality="shall", polarity="positive")
        fixture["output_adjudications"] = [{
            "output_fingerprint": output_fingerprint(fixture["id"], text, candidate),
            "verdict": "wrong_qualifier", "review_status": "human_reviewed",
            "critical": False,
            "reason": "The source explicitly prohibits acquisition.",
            "source_evidence": text,
        }]
        report = score_fixture(
            fixture, converted_text=text, frames=extract_frames(text),
            candidates=[candidate], verified=[VerifiedTriple(candidate, 0.9, 0.9)],
        )
        self.assertEqual(report["metrics"]["matched"], 0)
        self.assertEqual(report["metrics"]["qualifier_errors"], {"polarity": 1})
        self.assertEqual(report["metrics"]["precision"], 0.0)
        self.assertEqual(report["metrics"]["recall"], 0.0)

    def test_adjudicated_paraphrase_matches_gold_with_different_condition_words(self) -> None:
        text = "The board may appoint an auditor if shareholders approve."
        candidate = CandidateTriple(
            "the board", "can appoint", "an auditor", text, 0, 0, len(text),
            modality="may", condition="with shareholder approval",
        )
        fixture = {
            "id": "paraphrase", "domain": "legal", "review_status": "human_reviewed",
            "annotation_scope": "exhaustive", "gold": [{
                "id": "appointment", "subject": "board", "predicate": "appoints",
                "object": "auditor", "modality": "may",
                "condition": "if shareholders approve",
                "evidence": text,
            }],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("paraphrase", text, candidate),
                "verdict": "equivalent", "gold_id": "appointment",
                "review_status": "human_reviewed",
                "reason": "Can appoint and may appoint express the same permission; the approval condition is preserved.",
                "source_evidence": text,
            }],
        }
        report = score_fixture(
            fixture, converted_text=text, frames=[], candidates=[candidate],
            verified=[VerifiedTriple(candidate, 0.9, 0.9)],
        )
        self.assertEqual(report["metrics"]["matched"], 1)
        self.assertEqual(report["metrics"]["precision"], 1.0)
        self.assertEqual(report["metrics"]["recall"], 1.0)
        self.assertEqual(report["matches"][0]["match_type"], "adjudicated_equivalent")
        self.assertTrue(report["independent_human_review"])

    def test_wrong_qualifier_adjudication_is_negative_not_equivalent(self) -> None:
        text = "The board may appoint an auditor if shareholders approve."
        candidate = CandidateTriple(
            "the board", "can appoint", "an auditor", text, 0, 0, len(text),
            modality="may", condition="without shareholder approval",
        )
        fixture = {
            "id": "wrong-condition", "domain": "legal", "review_status": "human_reviewed",
            "annotation_scope": "exhaustive", "gold": [{
                "id": "appointment", "subject": "board", "predicate": "appoints",
                "object": "auditor", "modality": "may",
                "condition": "if shareholders approve", "evidence": text,
            }],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("wrong-condition", text, candidate),
                "verdict": "wrong_qualifier", "review_status": "human_reviewed",
                "gold_id": "appointment", "critical": True,
                "reason": "This reverses the approval condition.", "source_evidence": text,
            }],
        }
        report = score_fixture(
            fixture, converted_text=text, frames=[], candidates=[candidate],
            verified=[VerifiedTriple(candidate, 0.9, 0.9)],
        )
        self.assertEqual(report["metrics"]["matched"], 0)
        self.assertEqual(report["metrics"]["precision"], 0.0)
        self.assertEqual(report["metrics"]["recall"], 0.0)
        self.assertEqual(report["metrics"]["unsupported_critical"], 1)

    def test_duplicate_gold_mapping_is_rejected(self) -> None:
        text = "Alice founded Acme."
        first = CandidateTriple("Alice", "established", "Acme", text, 0, 0, len(text))
        second = CandidateTriple("Alice", "created", "Acme", text, 0, 0, len(text))
        fixture = {
            "id": "duplicates", "domain": "general", "gold": [{
                "id": "founding", "subject": "Alice", "predicate": "founded",
                "object": "Acme", "evidence": text,
            }],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("duplicates", text, candidate),
                "verdict": "equivalent", "gold_id": "founding",
                "review_status": "codex_reviewed", "reason": "Same founding event.",
                "source_evidence": text,
            } for candidate in (first, second)],
        }
        with self.assertRaisesRegex(ValueError, "duplicate match to gold_id"):
            score_fixture(fixture, converted_text=text, frames=[], candidates=[first, second],
                          verified=[VerifiedTriple(first, 0.9, 0.9),
                                    VerifiedTriple(second, 0.9, 0.9)])

    def test_stale_output_adjudication_is_rejected(self) -> None:
        text = "Alice founded Acme."
        original = CandidateTriple("Alice", "created", "Acme", text, 0, 0, len(text))
        changed = CandidateTriple("Alice", "created", "Acme", text, 0, 0, len(text),
                                  condition="in 2020")
        fixture = {
            "id": "stale", "domain": "general", "gold": [],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("stale", text, original),
                "verdict": "unsupported", "review_status": "codex_reviewed",
                "critical": False,
                "reason": "The text states founding, not creation in 2020.",
                "source_evidence": text,
            }],
        }
        with self.assertRaisesRegex(ValueError, "stale adjudication"):
            score_fixture(fixture, converted_text=text, frames=[], candidates=[changed],
                          verified=[VerifiedTriple(changed, 0.9, 0.9)])
        with self.assertRaisesRegex(ValueError, "stale adjudication"):
            score_fixture(fixture, converted_text=text + " Added sentence.", frames=[],
                          candidates=[original], verified=[VerifiedTriple(original, 0.9, 0.9)])

    def test_codex_adjudication_does_not_upgrade_human_review(self) -> None:
        text = "Alice founded Acme."
        candidate = CandidateTriple("Alice", "established", "Acme", text, 0, 0, len(text))
        fixture = {
            "id": "mixed-review", "domain": "general", "review_status": "human_reviewed",
            "annotation_scope": "exhaustive", "gold": [{
                "id": "founding", "subject": "Alice", "predicate": "founded",
                "object": "Acme", "evidence": text,
            }],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("mixed-review", text, candidate),
                "verdict": "equivalent", "gold_id": "founding",
                "review_status": "codex_reviewed", "reason": "Established means founded here.",
                "source_evidence": text,
            }],
        }
        report = score_fixture(fixture, converted_text=text, frames=[],
                               candidates=[candidate],
                               verified=[VerifiedTriple(candidate, 0.9, 0.9)])
        self.assertTrue(report["release_eligible"])
        self.assertFalse(report["independent_human_review"])

    def test_adjudicated_out_of_scope_output_counts_as_scope_leak(self) -> None:
        text = "Alice founded Acme."
        candidate = CandidateTriple("Alice", "founded", "Acme", text, 0, 0, len(text))
        fixture = {
            "id": "scope", "domain": "general", "review_status": "human_reviewed",
            "annotation_scope": "exhaustive", "instruction": "Only biomedical claims",
            "gold": [],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("scope", text, candidate),
                "verdict": "out_of_scope", "review_status": "human_reviewed",
                "critical": False, "reason": "The instruction excludes company founding.",
                "source_evidence": text,
            }],
        }
        report = score_fixture(fixture, converted_text=text, frames=[],
                               candidates=[candidate],
                               verified=[VerifiedTriple(candidate, 0.9, 0.9)])
        self.assertEqual(report["metrics"]["scope_leaks"], 1)

    def test_identical_outputs_make_fingerprint_ambiguous(self) -> None:
        text = "Alice founded Acme."
        candidate = CandidateTriple("Alice", "created", "Acme", text, 0, 0, len(text))
        fixture = {
            "id": "ambiguous", "domain": "general", "gold": [],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("ambiguous", text, candidate),
                "verdict": "unsupported", "review_status": "codex_reviewed",
                "critical": False,
                "reason": "The specific output is unsupported.", "source_evidence": text,
            }],
        }
        duplicates = [VerifiedTriple(candidate, 0.9, 0.9),
                      VerifiedTriple(candidate, 0.9, 0.9)]
        # The ordinary compiler deduplicates outputs; this guards scorer inputs too.
        with patch("jevy_graph.evaluation.select", return_value=duplicates):
            with self.assertRaisesRegex(ValueError, "ambiguous or already matched"):
                score_fixture(fixture, converted_text=text, frames=[],
                              candidates=[candidate], verified=duplicates)

    def test_adjudication_requires_source_quote(self) -> None:
        text = "Alice founded Acme."
        candidate = CandidateTriple("Alice", "created", "Acme", text, 0, 0, len(text))
        fixture = {
            "id": "source-quote", "domain": "general", "gold": [],
            "output_adjudications": [{
                "output_fingerprint": output_fingerprint("source-quote", text, candidate),
                "verdict": "unsupported", "review_status": "codex_reviewed",
                "critical": False,
                "reason": "No support in the source.",
                "source_evidence": "Alice acquired Acme.",
            }],
        }
        with self.assertRaisesRegex(ValueError, "source_evidence must quote"):
            score_fixture(fixture, converted_text=text, frames=[], candidates=[candidate],
                          verified=[VerifiedTriple(candidate, 0.9, 0.9)])

    def test_unmatched_output_requires_review_before_precision(self) -> None:
        text = "Alice founded Acme."
        fixture = {
            "id": "review", "domain": "general", "review_status": "codex_reviewed",
            "annotation_scope": "exhaustive", "gold": [],
        }
        candidate = CandidateTriple("Alice", "owns", "Acme", text, 0, 0, len(text))
        report = score_fixture(
            fixture, converted_text=text, frames=[], candidates=[candidate],
            verified=[VerifiedTriple(candidate, 0.9, 0.9)],
        )
        self.assertFalse(report["release_eligible"])
        self.assertEqual(report["metrics"]["pending_unmatched_review"], 1)
        self.assertIsNone(report["metrics"]["precision"])

    def test_stage_loss_after_scope_filter(self) -> None:
        fixture = {
            "id": "focused", "domain": "biomedical", "review_status": "provisional",
            "annotation_scope": "targeted", "instruction": "Only biological effects",
            "gold": [{
                "id": "effect", "subject": "BRCA1", "predicate": "inhibits",
                "object": "tumor growth", "evidence": "BRCA1 inhibits tumor growth",
            }],
        }
        text = "BRCA1 inhibits tumor growth."
        frames = extract_frames(text)
        candidate = CandidateTriple("BRCA1", "inhibits", "tumor growth", text, 0, 0, len(text))
        report = score_fixture(
            fixture, converted_text=text, frames=frames, candidates=[candidate],
            verified=[VerifiedTriple(candidate, 0.9, 0.9, 0.1)],
        )
        self.assertEqual(report["losses"][0]["stage"], "final_filter")
        self.assertEqual(report["metrics"]["rejection_reasons"], {"outside_instruction_scope": 1})

    def test_release_gate_ignores_development_fixture(self) -> None:
        report = {
            "domain": "legal", "instruction": "", "split": "development",
            "release_eligible": True,
            "metrics": {"matched": 1, "accepted": 1, "gold_in_scope": 1,
                        "scope_leaks": 0, "unsupported_critical": 0},
        }
        gate = release_gate([report])
        self.assertFalse(gate["passes"])
        self.assertIn("legal", gate["missing_domains"])

    def test_codex_review_is_scored_but_not_called_human_review(self) -> None:
        fixture = {
            "id": "reviewed", "domain": "legal", "split": "test",
            "review_status": "codex_reviewed", "annotation_scope": "exhaustive",
            "gold": [{"id": "founding", "subject": "Alice", "predicate": "founded",
                      "object": "Acme", "evidence": "Alice founded Acme."}],
        }
        candidate = CandidateTriple("Alice", "founded", "Acme",
                                    "Alice founded Acme.", 0, 0, 19)
        report = score_fixture(fixture, converted_text=candidate.evidence,
                               frames=[], candidates=[candidate],
                               verified=[VerifiedTriple(candidate, 0.9, 0.9)])
        self.assertTrue(report["release_eligible"])
        self.assertFalse(report["independent_human_review"])
        legal = release_gate([report])["domains"]["legal"]
        self.assertFalse(legal["independent_human_review"])
        self.assertFalse(legal["sample_sufficient"])

    def test_release_gate_requires_substantial_heldout_claim_counts(self) -> None:
        reports = [
            {
                "domain": domain, "instruction": "", "split": "test",
                "release_eligible": True, "independent_human_review": True,
                "metrics": {
                    "matched": 15, "accepted": 15, "gold_in_scope": 15,
                    "scope_leaks": 0, "unsupported_critical": 0,
                },
            }
            for domain in ("legal", "biomedical", "general", "structured")
            for _ in range(2)
        ]
        gate = release_gate(reports, constitution_coverage={"complete": True})
        self.assertTrue(gate["passes"])
        codex_only = [report | {"independent_human_review": False} for report in reports]
        codex_gate = release_gate(codex_only, constitution_coverage={"complete": True})
        self.assertFalse(codex_gate["passes"])
        self.assertFalse(codex_gate["domains"]["legal"]["independent_human_review"])
        short = reports[:1] + reports[2:]
        self.assertFalse(release_gate(short, constitution_coverage={"complete": True})["passes"])

    def test_identifies_source_conversion_loss(self) -> None:
        fixture = {
            "id": "converted", "domain": "general", "gold": [{
                "id": "lost", "subject": "Alice", "predicate": "founded",
                "object": "Acme", "evidence": "Alice founded Acme",
            }],
        }
        report = score_fixture(
            fixture, converted_text="", frames=[], candidates=[], verified=[]
        )
        self.assertEqual(report["losses"][0]["stage"], "source_conversion")

    def test_forbidden_claim_checks_explicit_polarity(self) -> None:
        text = "Congress shall not acquire Acme."
        negative = CandidateTriple(
            "Congress", "acquired", "Acme", text, 0, 0, len(text),
            modality="shall", polarity="negative",
        )
        report = score_fixture(
            {"id": "legal", "domain": "legal", "gold": [], "forbidden": [{
                "subject": "Congress", "predicate": "acquired", "object": "Acme",
                "polarity": "positive", "critical": True,
            }]},
            converted_text=text, frames=[], candidates=[negative],
            verified=[VerifiedTriple(negative, 0.9, 0.9)],
        )
        self.assertEqual(report["metrics"]["unsupported_critical"], 0)

    def test_quality_summary_groups_domain_and_instruction(self) -> None:
        report = score_fixture(
            {"id": "probe", "domain": "biomedical", "instruction": "functions only",
             "gold": [{"id": "claim", "subject": "BRCA1", "predicate": "inhibits",
                       "object": "growth", "evidence": "BRCA1 inhibits growth"}]},
            converted_text="BRCA1 inhibits growth", frames=[], candidates=[], verified=[],
            usage={"requests": 2, "input_tokens": 10, "output_tokens": 3},
        )
        summary = quality_summary([report])
        self.assertIsNone(summary["domains"]["biomedical"]["precision"])
        self.assertEqual(summary["profiles"]["biomedical | functions only"]["requests"], 2)

    def test_loss_stage_distinguishes_same_triple_by_condition(self) -> None:
        text = "No person shall be elected more than twice."
        frames = [RelationFrame(
            ("person",), ("elected_to",), ("office",), text, text,
            0, 0, len(text), modality="shall", polarity="negative",
            condition="more than twice",
        )]
        candidate = CandidateTriple(
            "person", "elected_to", "office", text, 0, 0, len(text),
            modality="shall", polarity="negative", condition="more than twice",
        )
        fixture = {"id": "limits", "domain": "legal", "gold": [{
            "id": "limit", "subject": "person", "predicate": "elected_to",
            "object": "office", "evidence": text, "modality": "shall",
            "polarity": "negative", "condition": "more than twice",
        }]}
        # A same-triple output under another condition cannot hide final filtering.
        other = CandidateTriple(
            "person", "elected_to", "office", text, 0, 0, len(text),
            modality="shall", polarity="negative", condition="more than once",
        )
        report = score_fixture(
            fixture, converted_text=text, frames=frames, candidates=[candidate, other],
            verified=[VerifiedTriple(candidate, 0.1, 0.9), VerifiedTriple(other, 0.9, 0.9)],
        )
        self.assertEqual(report["losses"][0]["stage"], "final_filter")


if __name__ == "__main__":
    unittest.main()

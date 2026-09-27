from __future__ import annotations

import unittest
import json
from http.client import RemoteDisconnected
from itertools import product
from threading import Event, Lock
from unittest.mock import Mock, patch

from jevy_graph.jev import (
    ClaimAssessment,
    JevClient,
    _http_error_message,
    _ranked_indexes,
    _triple_options,
    build_claim_slot_request,
    build_choice_request,
    build_completeness_request,
    build_verification_request,
    parse_choice_answers,
    parse_claim_slot_answers,
    parse_completeness_answers,
    parse_verification_answers,
)
from jevy_graph.models import CandidateTriple, RelationFrame, VerifiedTriple


def frame() -> RelationFrame:
    return RelationFrame(
        ("Congress", "Congress shall"),
        ("has", "authorized_to"),
        ("Power", "Power to lay Taxes", "lay Taxes"),
        "Congress shall have Power to lay Taxes.",
        "Congress shall have Power to lay Taxes.",
        0,
        0,
        39,
        "shall",
    )


class JevTests(unittest.TestCase):
    def test_scientific_slot_request_sends_only_ambiguous_fields(self) -> None:
        source = RelationFrame(
            ("Meplazumab",), ("decreases", "affects"), ("mortality",),
            "Meplazumab reduced mortality compared with placebo.",
            "Meplazumab reduced mortality compared with placebo.",
            0, 0, 51, claim_type="directional_effect", comparison="placebo",
        )
        request = build_claim_slot_request([source])
        self.assertEqual(set(request["questions"]), {"f0_predicate"})
        question = request["questions"]["f0_predicate"]
        self.assertIn("none", question["criteria"])
        self.assertEqual(
            question["instructions"]["fixed_slots"],
            {"subject": "Meplazumab", "object": "mortality"},
        )
        self.assertEqual(question["instructions"]["comparison"], "placebo")

    def test_scientific_slot_answers_assemble_fields_or_reject(self) -> None:
        source = RelationFrame(
            ("Meplazumab",), ("decreases", "affects"), ("mortality",),
            "Meplazumab reduced mortality compared with placebo.",
            "Meplazumab reduced mortality compared with placebo.",
            0, 0, 51, claim_type="directional_effect", comparison="placebo",
        )
        selected = parse_claim_slot_answers([source], {"answers": {
            "f0_predicate": {
                "choice": "v0", "confidence": 0.93,
                "probabilities": {"v0": 0.88, "v1": 0.1, "none": 0.02},
            },
        }})
        self.assertEqual(selected[0].predicate, "decreases")
        self.assertEqual(selected[0].comparison, "placebo")
        self.assertEqual(selected[0].selection_probability, 0.88)
        self.assertEqual(
            parse_claim_slot_answers([source], {"answers": {
                "f0_predicate": {"choice": "none"},
            }}),
            [None],
        )

    def test_transport_reuses_connection_and_records_provider_usage(self) -> None:
        response = Mock(status=200)
        response.read.return_value = json.dumps({
            "answers": {}, "usage": {"input_tokens": 20, "output_tokens": 3}
        }).encode()
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("jevy_graph.jev.http.client.HTTPSConnection", return_value=connection) as factory:
            client = JevClient("test")
            client._post({})
            client._post({})
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(connection.request.call_count, 2)
        self.assertEqual(client.usage.requests, 2)
        self.assertEqual(client.usage.request_bytes, 4)
        self.assertEqual(client.usage.input_tokens, 40)
        self.assertEqual(client.usage.output_tokens, 6)

    def test_transport_reconnects_after_closed_socket(self) -> None:
        stale = Mock()
        stale.getresponse.side_effect = RemoteDisconnected("closed")
        response = Mock(status=200)
        response.read.return_value = b'{"answers": {}}'
        fresh = Mock()
        fresh.getresponse.return_value = response
        with patch("jevy_graph.jev.http.client.HTTPSConnection", side_effect=[stale, fresh]):
            with patch("jevy_graph.jev.time.sleep"), patch.object(JevClient, "_wait_for_request"):
                client = JevClient("test", attempts=2)
                client._post({})
        stale.close.assert_called_once()
        self.assertEqual(client.usage.retries, 1)

    def test_payment_errors_are_not_retried(self) -> None:
        response = Mock(status=402)
        response.read.return_value = b'{}'
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("jevy_graph.jev.http.client.HTTPSConnection", return_value=connection):
            client = JevClient("test")
            with self.assertRaisesRegex(Exception, "no available credits"):
                client._post({})
        self.assertEqual(client.usage.requests, 1)

    def test_compact_candidates_reconstruct_every_original_triple(self) -> None:
        source = RelationFrame(("Alice", "Bob"), ("founded",), ("Acme", "Acme Labs"), "Alice founded Acme Labs.", "Alice founded Acme Labs.", 0, 0, 23)
        original = build_choice_request([source], allow_reject=True)["questions"]["f0_triple"]["criteria"]
        compact = build_choice_request([source], compact=True, allow_reject=True)["questions"]["f0_triple"]
        fixed = compact["instructions"]["fixed_fields"]
        rebuilt = {
            key: ({**fixed, **value} if key != "reject" else value)
            for key, value in compact["criteria"].items()
        }
        self.assertEqual(original, rebuilt)

    def test_universal_object_quantifier_survives_candidate_normalization(self) -> None:
        source = RelationFrame(
            ("Electors",), ("make_List_of",), ("all Persons voted for",),
            "The Electors shall make a List of all Persons voted for.",
            "The Electors shall make a List of all Persons voted for.", 0, 0, 53,
            "shall",
        )
        self.assertEqual(
            _triple_options(source),
            (("Electors", "make_List_of", "all Persons voted for"),),
        )

    def test_selection_can_reject_every_candidate(self) -> None:
        self.assertNotIn(
            "reject", build_choice_request([frame()])["questions"]["f0_triple"]["criteria"]
        )
        request = build_choice_request([frame()], allow_reject=True)
        self.assertIn("reject", request["questions"]["f0_triple"]["criteria"])
        result = parse_choice_answers([frame()], {"answers": {"f0_triple": {"choice": "reject"}}})
        self.assertEqual(result, [None])

    def test_frame_attribution_reaches_candidate_and_support_question(self) -> None:
        from dataclasses import replace

        source = replace(frame(), attribution="Smith et al. (2024)")
        request = build_choice_request([source])
        choice = next(iter(request["questions"]["f0_triple"]["criteria"]))
        candidate = parse_choice_answers(
            [source], {"answers": {"f0_triple": {
                "choice": choice, "confidence": 0.9, "probabilities": {choice: 0.9},
            }}}
        )[0]
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.attribution, "Smith et al. (2024)")
        support = build_verification_request([candidate])["questions"]["c0_support"]["instructions"]["candidate"]
        self.assertEqual(support["attribution"], "Smith et al. (2024)")
        cited_question = build_verification_request([candidate], compact_policies=False)["questions"]["c0_support"]["instructions"]["question"]
        own_question = build_verification_request([replace(candidate, attribution=None)], compact_policies=False)["questions"]["c0_support"]["instructions"]["question"]
        self.assertIn("attributes this relationship to the named prior study", cited_question)
        self.assertNotIn("named prior study", own_question)

    def test_instruction_scope_is_part_of_verification(self) -> None:
        candidate = CandidateTriple("Cells", "washed_with", "PBS", "Cells were washed with PBS.", 0, 0, 25)
        request = build_verification_request([candidate], instruction="Only biological functions")
        self.assertIn("c0_scope", request["questions"])
        response = {"answers": {
            "c0_support": {"noul": 0.9},
            "c0_entities": {"noul": 0.9},
            "c0_qualifiers": {"noul": 0.8},
            "c0_atomicity": {"noul": 0.7},
            "c0_scope": {"noul": 0.02},
        }}
        scored = parse_verification_answers([candidate], response, instruction="Only biological functions")
        self.assertEqual(scored[0].scope_relevance, 0.02)

    def test_negative_finding_is_explained_to_scope_question(self) -> None:
        candidate = CandidateTriple(
            "mutant expression", "inhibited", "metastasis",
            "Unlike wild type, mutant expression did not inhibit metastasis.",
            0, 0, 62, polarity="negative",
        )
        request = build_verification_request(
            [candidate], instruction="Only biological findings"
        )
        scope = request["questions"]["c0_scope"]["instructions"]["candidate"]
        self.assertEqual(scope["polarity"], "negative")
        self.assertIn("negative finding", scope["claim_reading"])

    def test_experiment_provenance_is_separate_from_biological_result(self) -> None:
        candidate = CandidateTriple(
            "gene knockdown experiment", "revealed", "pathway activation",
            "The knockdown experiment revealed pathway activation.",
            0, 0, 51,
        )
        request = build_verification_request(
            [candidate], instruction="Only biological findings"
        )
        scope = request["questions"]["c0_scope"]["instructions"]["candidate"]
        self.assertIn("separate result claim", scope["claim_reading"])

    def test_verification_sends_only_context_needed_for_each_decision(self) -> None:
        candidate = CandidateTriple(
            "Cells", "washed_with", "PBS", "Cells were washed with PBS.",
            0, 0, 25, context="The cells were collected. Cells were washed with PBS.",
        )
        request = build_verification_request([candidate])
        questions = request["questions"]
        support = questions["c0_support"]["instructions"]["candidate"]
        entities = questions["c0_entities"]["instructions"]["candidate"]
        self.assertIn("context_ref", support)
        self.assertNotIn("context_ref", entities)
        self.assertEqual(entities["predicate"], candidate.predicate)
        self.assertEqual(request["state"]["evidence_by_id"][entities["evidence_ref"]],
                         candidate.evidence)

        duplicate_context = CandidateTriple(
            "Cells", "washed_with", "PBS", "Cells were washed with PBS.",
            0, 0, 25, context="Cells were washed with PBS.",
        )
        support = build_verification_request([duplicate_context])["questions"]["c0_support"]["instructions"]["candidate"]
        self.assertNotIn("context_ref", support)

    def test_verification_reuses_identical_evidence_and_instruction(self) -> None:
        first = CandidateTriple("A", "activates", "B", "A activates B and C.", 0, 0, 20)
        second = CandidateTriple("A", "activates", "C", "A activates B and C.", 0, 0, 20)
        request = build_verification_request([first, second], instruction="Only functions")
        self.assertEqual(request["state"]["evidence_by_id"],
                         {"e0": "A activates B and C."})
        self.assertEqual(request["state"]["user_instruction"], "Only functions")
        self.assertEqual(request["questions"]["c0_support"]["instructions"]
                         ["candidate"]["evidence_ref"], "e0")
        self.assertEqual(request["questions"]["c1_scope"]["instructions"]
                         ["candidate"]["evidence_ref"], "e0")
        self.assertEqual(len(request["state"]["question_policies"]), 5)
        self.assertEqual(
            request["questions"]["c0_support"]["instructions"]["question"],
            request["questions"]["c1_support"]["instructions"]["question"],
        )
        expanded = build_verification_request([first, second],
                                               instruction="Only functions",
                                               compact_policies=False)
        self.assertNotIn("question_policies", expanded["state"])
        self.assertIn("evidence explicitly assert", expanded["questions"]
                      ["c0_support"]["instructions"]["question"])

    def test_instruction_view_rejects_unsupported_grouping(self) -> None:
        from jevy_graph.jev import parse_intent_answer

        with self.assertRaisesRegex(ValueError, "not supported"):
            parse_intent_answer("Group by historical importance", {
                "answers": {"organization": {"choice": "unsupported"}}
            })

    def test_ranked_options_preserve_original_cartesian_order(self) -> None:
        for sizes in product(range(5), repeat=3):
            expected = sorted(
                product(*(range(size) for size in sizes)),
                key=lambda item: (sum(item), max(item), item),
            )
            self.assertEqual(list(_ranked_indexes(sizes)), expected)

    def test_pipeline_verifies_before_all_selection_finishes(self) -> None:
        verification_started = Event()
        counter_lock = Lock()

        class LocalClient(JevClient):
            calls = 0

            def _resolve_batch(self, frames):
                with counter_lock:
                    self.calls += 1
                    call = self.calls
                if call == 2:
                    if not verification_started.wait(2):
                        raise AssertionError("verification waited for all selections")
                return [CandidateTriple("Alice", "founded", "Acme", "Alice founded Acme.", 0, 0, 19)]

            def _verify_batch(self, candidates):
                verification_started.set()
                return [VerifiedTriple(c, 0.9, 0.9) for c in candidates]

        multi = RelationFrame(("Alice", "Bob"), ("founded",), ("Acme",), "Alice founded Acme.", "Alice founded Acme.", 0, 0, 19)
        result = LocalClient("test", choice_batch_size=1, max_workers=2).score([multi, multi])
        self.assertEqual(len(result), 2)
        self.assertTrue(verification_started.is_set())

    def test_pipeline_stops_scheduling_after_failure(self) -> None:
        class LocalClient(JevClient):
            calls = 0

            def _score_frame_batch(self, frames):
                self.calls += 1
                raise RuntimeError("failed request")

        client = LocalClient("test", choice_batch_size=1, max_workers=1)
        with self.assertRaisesRegex(RuntimeError, "failed request"):
            client.score([frame()] * 10)
        self.assertEqual(client.calls, 1)

    def test_closing_stream_stops_pending_batches(self) -> None:
        class LocalClient(JevClient):
            calls = 0

            def _score_frame_batch(self, frames):
                self.calls += 1
                candidate = CandidateTriple("Alice", "founded", "Acme", "Alice founded Acme.", 0, 0, 19)
                return [VerifiedTriple(candidate, 0.9, 0.9)]

        client = LocalClient("test", choice_batch_size=1, max_workers=1)
        batches = client.iter_score_batches([frame()] * 10)
        next(batches)
        batches.close()
        self.assertEqual(client.calls, 1)

    def test_explains_payment_required(self) -> None:
        self.assertIn("no available credits", _http_error_message(402))
        self.assertEqual(_http_error_message(500), "Jev request failed with HTTP 500")

    def test_skips_choice_for_single_option(self) -> None:
        single = RelationFrame(
            ("Toronto",),
            ("type",),
            ("city",),
            "Toronto is a city.",
            "Toronto is a city.",
            0,
            0,
            18,
        )

        class LocalClient(JevClient):
            def _post(self, payload: dict[str, object]) -> dict[str, object]:
                raise AssertionError("unexpected request")

        client = LocalClient("test")
        result = client.resolve([single])
        self.assertEqual((result[0].subject, result[0].predicate), ("Toronto", "type"))
        self.assertEqual(client.singleton_selections, 1)

    def test_choice_round_trip(self) -> None:
        options = _triple_options(frame())
        target = options.index(("Congress", "authorized_to", "lay Taxes"))
        choice = f"t{target}"
        request = build_choice_request([frame()])
        question = request["questions"]["f0_triple"]
        self.assertEqual(question["type"], "choice")
        self.assertNotIn("modality", question["criteria"][choice])
        self.assertEqual(question["instructions"]["modality"], "shall")
        result = parse_choice_answers(
            [frame()],
            {
                "answers": {
                    "f0_triple": {
                        "choice": choice,
                        "confidence": 0.84,
                        "probabilities": {choice: 0.76},
                    }
                }
            },
        )
        self.assertEqual(
            (result[0].subject, result[0].predicate, result[0].object),
            ("Congress", "authorized_to", "lay Taxes"),
        )

    def test_rejects_unknown_choice(self) -> None:
        with self.assertRaisesRegex(Exception, "invalid choice"):
            parse_choice_answers(
                [frame()],
                {
                    "answers": {
                        "f0_triple": {
                            "choice": "none",
                            "confidence": 0.9,
                            "probabilities": {"none": 0.9},
                        }
                    }
                },
            )

    def test_streams_batches_as_they_finish(self) -> None:
        single = RelationFrame(
            ("Toronto",),
            ("type",),
            ("city",),
            "Toronto is a city.",
            "Toronto is a city.",
            0,
            0,
            18,
        )

        class LocalClient(JevClient):
            def _verify_batch(
                self, candidates: list[CandidateTriple]
            ) -> list[VerifiedTriple]:
                return [VerifiedTriple(candidate, 0.9, 0.9) for candidate in candidates]

        batches = list(
            LocalClient("test", choice_batch_size=1).iter_score_batches([single, single])
        )
        self.assertEqual([len(batch) for batch in batches], [1, 1])

    def test_completeness_audit_keeps_dimensions_independent(self) -> None:
        candidate = CandidateTriple(
            "TINCR knockdown", "increased", "proliferation",
            "TINCR knockdown increased proliferation in CRC cells.",
            0, 0, 57, condition="in CRC cells",
        )
        client = JevClient("test")
        seen = []

        def post(payload):
            seen.append(payload)
            return {"answers": {
                "c0_support": {"noul": 0.91},
                "c0_boundaries": {"noul": 0.82},
                "c0_qualifiers": {"noul": 0.73},
                "c0_atomicity": {"noul": 0.88},
            }}

        client._post = post
        assessments = client.assess_claims([candidate])
        self.assertEqual(assessments, [ClaimAssessment(
            candidate=candidate,
            support=0.91,
            boundaries=0.82,
            qualifiers=0.73,
            atomicity=0.88,
        )])
        self.assertTrue(assessments[0].passes(qualifiers=0.7))
        self.assertFalse(assessments[0].passes(boundaries=0.9))
        self.assertEqual(client.assess_completeness([candidate]), [{
            "support": 0.91, "boundaries": 0.82,
            "qualifiers": 0.73, "atomicity": 0.88,
        }])
        self.assertEqual(
            set(seen[0]["questions"]),
            {"c0_support", "c0_boundaries", "c0_qualifiers", "c0_atomicity"},
        )

    def test_completeness_request_deduplicates_evidence_and_policies(self) -> None:
        evidence = "TINCR knockdown increased proliferation in CRC cells."
        first = CandidateTriple(
            "TINCR knockdown", "increased", "proliferation", evidence,
            0, 0, len(evidence), condition="in CRC cells",
            context="Earlier context. " + evidence,
        )
        second = CandidateTriple(
            "TINCR knockdown", "increased", "migration", evidence,
            0, 0, len(evidence), condition="in CRC cells",
            context="Earlier context. " + evidence,
        )

        request = build_completeness_request([first, second])
        state = request["state"]
        self.assertEqual(len(state["evidence_by_id"]), 2)
        self.assertEqual(
            request["questions"]["c0_support"]["instructions"]["claim"]
            ["evidence_ref"],
            request["questions"]["c1_atomicity"]["instructions"]["claim"]
            ["evidence_ref"],
        )
        self.assertEqual(len(state["dimension_policies"]), 4)
        self.assertEqual(
            request["questions"]["c0_qualifiers"]["instructions"]["question"],
            "Score this claim using state.dimension_policies.qualifiers.",
        )

        expanded = build_completeness_request([first], compact_policies=False)
        self.assertNotIn("dimension_policies", expanded["state"])
        self.assertIn(
            "every material condition",
            expanded["questions"]["c0_qualifiers"]["instructions"]["question"],
        )

    def test_claim_assessment_batches_every_candidate(self) -> None:
        candidates = [
            CandidateTriple(
                f"subject {index}", "activates", f"object {index}",
                f"subject {index} activates object {index}.", index, 0, 30,
            )
            for index in range(3)
        ]
        payloads = []
        client = JevClient(
            "test", verification_batch_size=2, max_workers=1
        )

        def post(payload):
            payloads.append(payload)
            return {
                "answers": {
                    key: {"noul": 0.9}
                    for key in payload["questions"]
                }
            }

        client._post = post
        assessments = client.assess_claims(candidates)

        self.assertEqual(
            [assessment.candidate for assessment in assessments], candidates
        )
        self.assertEqual([len(payload["questions"]) for payload in payloads], [8, 4])
        self.assertTrue(
            all("dimension_policies" in payload["state"] for payload in payloads)
        )

    def test_completeness_parser_reports_candidate_and_dimension_errors(self) -> None:
        candidate = CandidateTriple(
            "A", "activates", "B", "A activates B.", 0, 0, 14
        )
        response = {"answers": {
            "c0_support": {"noul": "0.9"},
            "c0_boundaries": {"noul": 0.8},
            "c0_qualifiers": {"noul": 0.7},
            "c0_atomicity": {"noul": 0.6},
        }}
        assessment = parse_completeness_answers([candidate], response)[0]
        self.assertIs(assessment.candidate, candidate)
        self.assertEqual(assessment.scores(), {
            "support": 0.9,
            "boundaries": 0.8,
            "qualifiers": 0.7,
            "atomicity": 0.6,
        })

        response["answers"]["c0_qualifiers"] = {"noul": 1.1}
        with self.assertRaisesRegex(
            Exception, "qualifiers score is out of range for candidate 0"
        ):
            parse_completeness_answers([candidate], response)

        response["answers"]["c0_qualifiers"] = {"noul": 0.7}
        del response["answers"]["c0_atomicity"]
        with self.assertRaisesRegex(
            Exception, "omitted atomicity for candidate 0"
        ):
            parse_completeness_answers([candidate], response)


if __name__ == "__main__":
    unittest.main()

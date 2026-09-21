from __future__ import annotations

import unittest

from jevy_graph.jev import (
    JevClient,
    _http_error_message,
    _triple_options,
    build_choice_request,
    parse_choice_answers,
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


if __name__ == "__main__":
    unittest.main()

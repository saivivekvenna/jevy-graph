from __future__ import annotations

import unittest
import json
from http.client import RemoteDisconnected
from itertools import product
from threading import Event, Lock
from unittest.mock import Mock, patch

from jevy_graph.jev import (
    JevClient,
    _http_error_message,
    _ranked_indexes,
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
        original = build_choice_request([source])["questions"]["f0_triple"]["criteria"]
        compact = build_choice_request([source], compact=True)["questions"]["f0_triple"]
        fixed = compact["instructions"]["fixed_fields"]
        rebuilt = {key: {**fixed, **value} for key, value in compact["criteria"].items()}
        self.assertEqual(original, rebuilt)

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


if __name__ == "__main__":
    unittest.main()

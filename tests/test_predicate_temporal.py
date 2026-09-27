from __future__ import annotations

import unittest

from jevy_graph.extract import extract_frames


class PredicateTemporalTests(unittest.TestCase):
    def test_trailing_during_phrase_qualifies_its_event(self) -> None:
        frames = extract_frames(
            "The study medication successfully altered dopaminergic tone "
            "during the conditioning procedure."
        )
        altered = next(frame for frame in frames if frame.predicate_options[0] == "altered")
        self.assertEqual(altered.condition, "during the conditioning procedure")

    def test_trailing_setting_does_not_move_to_earlier_event(self) -> None:
        frames = extract_frames(
            "Drug altered pressure and researchers measured pain during treatment."
        )
        altered = next(frame for frame in frames if frame.predicate_options[0] == "altered")
        measured = next(frame for frame in frames if frame.predicate_options[0] == "measured")
        self.assertIsNone(altered.condition)
        self.assertEqual(measured.condition, "during treatment")


if __name__ == "__main__":
    unittest.main()

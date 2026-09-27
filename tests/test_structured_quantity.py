from __future__ import annotations

import unittest

from jevy_graph.structured import extract_structured_frames


class StructuredQuantityTests(unittest.TestCase):
    def test_relative_day_is_event_timing_not_training_duration(self) -> None:
        frames = extract_structured_frames(
            "The medication did not alter placebo analgesia tested 1 day later."
        )
        self.assertFalse(any("duration" in frame.predicate_options[0] for frame in frames))

    def test_training_and_generic_duration_keep_distinct_meanings(self) -> None:
        training = extract_structured_frames("The model trained for 3 days.")
        procedure = extract_structured_frames("The procedure lasted 2 days.")
        self.assertIn(
            ("model", "has_training_duration_days", "3"),
            [(frame.subject_options[0], frame.predicate_options[0], frame.object_options[0])
             for frame in training],
        )
        self.assertIn(
            ("procedure", "has_duration_days", "2"),
            [(frame.subject_options[0], frame.predicate_options[0], frame.object_options[0])
             for frame in procedure],
        )


if __name__ == "__main__":
    unittest.main()

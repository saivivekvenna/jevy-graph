from __future__ import annotations

import unittest

from jevy_graph.extract import extract_candidates


def claims(text: str):
    return {
        (item.subject, item.predicate, item.object): item
        for item in extract_candidates(text)
    }


class ProseClauseAssemblyTests(unittest.TestCase):
    def test_ordinary_prose_resolves_references_and_separates_qualifiers(self) -> None:
        result = claims(
            "After a decade at Meridian Labs, Maya Chen joined Arcadia Robotics "
            "in 2021. She became chief engineer the following year. Arcadia "
            "acquired Northwind Sensors for $48 million in March 2024, but kept "
            "its Vancouver office open. The company may move sensor production "
            "to Calgary if demand exceeds current capacity, although it has not "
            "announced a final decision."
        )
        self.assertEqual(set(result), {
            ("Maya Chen", "joined", "Arcadia Robotics"),
            ("Maya Chen", "became", "chief engineer"),
            ("Arcadia Robotics", "acquired", "Northwind Sensors"),
            ("Arcadia Robotics", "kept_open", "Vancouver office"),
            ("Arcadia Robotics", "moves", "sensor production to Calgary"),
            ("Arcadia Robotics", "announced", "final decision"),
        })
        self.assertEqual(
            result[("Maya Chen", "joined", "Arcadia Robotics")].condition,
            "After a decade at Meridian Labs; in 2021",
        )
        self.assertEqual(
            result[("Arcadia Robotics", "acquired", "Northwind Sensors")].condition,
            "for $48 million; in March 2024",
        )
        move = result[("Arcadia Robotics", "moves", "sensor production to Calgary")]
        self.assertEqual((move.modality, move.condition),
                         ("may", "if demand exceeds current capacity"))
        announcement = result[("Arcadia Robotics", "announced", "final decision")]
        self.assertEqual((announcement.modality, announcement.polarity),
                         (None, "negative"))

    def test_standalone_rule_keeps_deadline_condition_and_negation_scope(self) -> None:
        result = claims(
            "A landlord shall return the security deposit within 30 days after "
            "the tenant vacates the premises. The landlord may deduct documented "
            "repair costs, but shall not deduct charges for ordinary wear. If the "
            "landlord fails to provide an itemized statement, the tenant is "
            "entitled to twice the amount withheld."
        )
        self.assertEqual(set(result), {
            ("landlord", "returns", "security deposit"),
            ("landlord", "deducts", "documented repair costs"),
            ("landlord", "deducts", "charges for ordinary wear"),
            ("tenant", "entitled_to", "twice the amount withheld"),
        })
        returned = result[("landlord", "returns", "security deposit")]
        self.assertEqual(
            (returned.modality, returned.condition),
            ("shall", "within 30 days after the tenant vacates the premises"),
        )
        prohibited = result[("landlord", "deducts", "charges for ordinary wear")]
        self.assertEqual((prohibited.modality, prohibited.polarity),
                         ("shall", "negative"))
        entitled = result[("tenant", "entitled_to", "twice the amount withheld")]
        self.assertEqual(
            entitled.condition,
            "If the landlord fails to provide an itemized statement",
        )

    def test_person_reference_survives_an_intervening_organization_object(self) -> None:
        result = claims(
            "Jordan Lee founded Pinecone Media in 2018. "
            "She sold Pinecone Media in 2022."
        )
        self.assertIn(("Jordan Lee", "founded", "Pinecone Media"), result)
        self.assertIn(("Jordan Lee", "sold", "Pinecone Media"), result)

    def test_coordinated_predicates_share_only_the_subject(self) -> None:
        result = claims(
            "The board approved the annual budget in 2024, but rejected the "
            "expansion proposal."
        )
        self.assertEqual(set(result), {
            ("board", "approved", "annual budget"),
            ("board", "rejected", "expansion proposal"),
        })
        self.assertEqual(
            result[("board", "approved", "annual budget")].condition,
            "in 2024",
        )


if __name__ == "__main__":
    unittest.main()

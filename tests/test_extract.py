from __future__ import annotations

import json
import unittest
from pathlib import Path

from jevy_graph.extract import _clauses, clean_document, extract_candidates, extract_frames
from jevy_graph.normalize import canonical_label, find_aliases


def triples(text: str) -> set[tuple[str, str, str]]:
    return {
        (item.subject, item.predicate, item.object)
        for item in extract_candidates(text)
    }


class ExtractTests(unittest.TestCase):
    def test_untouched_results_gold_has_complete_general_event_frames(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "benchmarks/corpus/tap73-ferroptosis-results.txt").read_text()
        gold = json.loads(
            (root / "benchmarks/audits/tap73-results-frozen-gold-2026-09-27.json")
            .read_text()
        )["gold"]
        frames = [frame for frame in extract_frames(text) if frame.origin == "event"]
        actual = {
            (
                frame.subject_options[0], frame.predicate_options[0],
                frame.object_options[0], frame.modality, frame.condition,
            )
            for frame in frames
        }
        missing = [
            item["id"] for item in gold
            if (
                item["subject"], item["predicate"], item["object"],
                item["modality"], item["condition"],
            ) not in actual
        ]
        self.assertEqual(missing, [])
        self.assertNotIn(
            ("BMECs", "induce", "ferroptosis"),
            {
                (frame.subject_options[0], frame.predicate_options[0], frame.object_options[0])
                for frame in frames
            },
        )

    def test_scientific_abbreviations_and_decimals_do_not_split_evidence(self) -> None:
        source = (
            "Growth was measured in vitro (i.e., at p < 0.05) in U.S. cells. "
            "Survival increased."
        )
        clauses = _clauses(source)
        self.assertEqual(len(clauses), 2)
        self.assertEqual(clauses[0].text,
                         "Growth was measured in vitro (i.e., at p < 0.05) in U.S. cells.")
        self.assertEqual(source[clauses[0].start:clauses[0].end], clauses[0].text)

    def test_scientific_section_headings_label_full_paper_frames(self) -> None:
        paper = (
            Path(__file__).resolve().parents[1]
            / "benchmarks/corpus/tincr-epcam-full.txt"
        ).read_text()
        frames = extract_frames(paper)
        representative_evidence = {
            "The qRT-PCR analysis revealed": "RESULTS",
            "(A) Effects of oe-TINCR": "RESULTS",  # structured measurement
            "Accumulating evidence indicates": "DISCUSSION",
            "Total 44 human colorectal cancer tissues": "MATERIALS_AND_METHODS",
            "Luciferase activity was measured": "MATERIALS_AND_METHODS",
        }
        for prefix, expected_unit in representative_evidence.items():
            matched = [frame for frame in frames if frame.evidence.startswith(prefix)]
            self.assertTrue(matched, prefix)
            self.assertEqual({frame.source_unit for frame in matched}, {expected_unit})

    def test_scientific_heading_variants_and_prose_do_not_shift_sections(self) -> None:
        clauses = _clauses(
            "Abstract\nAlpha affects Beta.\n"
            "Results and Discussion\nResults indicate that Gamma affects Delta.\n"
            "Materials & Methods\nSamples were measured.\n"
            "Conclusions\nGamma affects Epsilon."
        )
        self.assertEqual(
            [clause.source_unit for clause in clauses if "affects" in clause.text],
            ["ABSTRACT", "RESULTS_AND_DISCUSSION", "CONCLUSIONS"],
        )
        self.assertEqual(
            next(clause.source_unit for clause in clauses if "measured" in clause.text),
            "MATERIALS_AND_METHODS",
        )

    def test_coordinated_results_correlations_keep_each_target_statistic(self) -> None:
        paper = (
            Path(__file__).resolve().parents[1]
            / "benchmarks/corpus/tincr-epcam-full.txt"
        ).read_text()
        frames = [
            frame for frame in extract_frames(paper)
            if frame.source_unit == "RESULTS"
            and frame.subject_options[0] == "TINCR expression"
            and frame.predicate_options[0].endswith("correlated_with")
            and "serosal invasion" in frame.evidence
        ]
        self.assertEqual(
            {(frame.predicate_options[0], frame.object_options[0], frame.condition)
             for frame in frames},
            {
                ("inversely_correlated_with", "serosal invasion",
                 "CRC tumour tissue samples; p = 0.001"),
                ("inversely_correlated_with", "lymph metastasis",
                 "CRC tumour tissue samples; p = 0.037"),
                ("inversely_correlated_with", "TNM classification",
                 "CRC tumour tissue samples; p = 0.016"),
                ("positively_correlated_with", "differentiation degree",
                 "CRC tumour tissue samples; p = 0.017"),
            },
        )
        self.assertTrue(all(frame.modality == "observed" for frame in frames))

    def test_coordinated_correlations_generalize_and_do_not_make_statistics_nodes(self) -> None:
        source = (
            "The team profiled ALPHA in treated patient samples. As shown in Table 2, "
            "the ALPHA expression levels were negatively correlated with "
            "tumour size (p < 0.02), vascular invasion (p = 0.04), while "
            "positively correlated with treatment response (p = 0.03)."
        )
        claims = extract_candidates(source)
        self.assertEqual(
            {(claim.subject, claim.predicate, claim.object, claim.condition)
             for claim in claims if "correlated_with" in claim.predicate},
            {
                ("ALPHA expression", "inversely_correlated_with", "tumour size",
                 "in treated patient samples; p < 0.02"),
                ("ALPHA expression", "inversely_correlated_with", "vascular invasion",
                 "in treated patient samples; p = 0.04"),
                ("ALPHA expression", "positively_correlated_with", "treatment response",
                 "in treated patient samples; p = 0.03"),
            },
        )
        self.assertFalse(any(claim.subject.casefold() == "p" for claim in claims))

    def test_coordinated_associations_keep_target_specific_statistics(self) -> None:
        claims = extract_candidates(
            "MarkerB was associated with fatigue (p = 0.01) and nausea "
            "(p = 0.03), while negatively associated with recovery (p = 0.04)."
        )
        self.assertEqual(
            {(claim.subject, claim.predicate, claim.object, claim.condition)
             for claim in claims},
            {
                ("MarkerB", "associated_with", "fatigue", "p = 0.01"),
                ("MarkerB", "associated_with", "nausea", "p = 0.03"),
                ("MarkerB", "negatively_associated_with", "recovery", "p = 0.04"),
            },
        )

    def test_extracts_general_relations(self) -> None:
        actual = triples("Alice founded Acme. Acme is located in Toronto.")
        self.assertIn(("Alice", "founded", "Acme"), actual)
        self.assertIn(("Acme", "located_in", "Toronto"), actual)

    def test_preserves_negation_and_modality(self) -> None:
        claims = extract_candidates("Congress shall not acquire Acme.")
        self.assertEqual((claims[0].modality, claims[0].polarity), ("shall", "negative"))

    def test_auxiliary_negation_splits_targets_and_scopes_reduced_timing(self) -> None:
        source = (
            "The study medication altered dopaminergic tone during conditioning. "
            "Contrary to our hypotheses, the medication did not modulate the "
            "formation of positive treatment expectation and placebo analgesia "
            "tested 1 day later."
        )
        frames = extract_frames(source)
        negative = [frame for frame in frames if frame.polarity == "negative"]
        self.assertEqual(
            {(frame.subject_options[0], frame.predicate_options[0],
              frame.object_options[0], frame.condition) for frame in negative},
            {("study medication", "modulated",
              "formation of positive treatment expectation", None),
             ("study medication", "modulated", "placebo analgesia",
              "tested 1 day later")},
        )
        self.assertFalse(any(frame.predicate_options[0] == "tested" for frame in frames))

    def test_auxiliary_negation_generalizes_across_actors_verbs_and_domains(self) -> None:
        cases = (
            ("The council did not approve permits and licenses issued after the hearing.",
             "council", "approved", {"permits": None,
                                      "licenses": "issued after the hearing"}),
            ("Acme does not ship sensors and receivers tested at noon.",
             "Acme", "ship", {"sensors": None, "receivers": "tested at noon"}),
            ("The treatment did not significantly affect mood measured at baseline "
             "and pain tested 1 day later.",
             "treatment", "affected", {"mood": "measured at baseline",
                                        "pain": "tested 1 day later"}),
            ("The board did not approve licenses and permits during the hearing.",
             "board", "approved", {"licenses": "during the hearing",
                                    "permits": "during the hearing"}),
        )
        for source, actor, predicate, targets in cases:
            with self.subTest(source=source):
                frames = extract_frames(source)
                self.assertEqual(
                    {(frame.subject_options[0], frame.predicate_options[0],
                      frame.object_options[0], frame.polarity, frame.condition)
                     for frame in frames},
                    {(actor, predicate, target, "negative", condition)
                     for target, condition in targets.items()},
                )

    def test_auxiliary_negation_keeps_joint_named_complex_and_contrast(self) -> None:
        joint = extract_frames(
            "The assay did not show the formation of DomainX and β-UnitB complex."
        )
        self.assertEqual(
            [(frame.object_options[0], frame.polarity) for frame in joint],
            [("formation of DomainX and β-UnitB complex", "negative")],
        )
        contrast = extract_frames(
            "Knockdown of TINCR did not change the EpCAM mRNA but downregulated "
            "the EpCAM protein levels in CRC cells (Figure 4C and 4D)."
        )
        self.assertEqual(len(contrast), 2)

    def test_negative_coordination_distributes_shared_objects_without_leakage(self) -> None:
        source = (
            "Neither the Council nor any Board shall inspect or retain any sample "
            "or record collected in the archive."
        )
        frames = extract_frames(source)
        actual = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.modality, frame.polarity, frame.condition)
            for frame in frames
        }
        expected = {
            (actor, predicate, f"{item} collected in the archive", "shall", "negative", None)
            for actor in ("Council", "Board")
            for predicate in ("inspect", "retain")
            for item in ("sample", "record")
        }
        self.assertEqual(actual, expected)

    def test_interposed_consent_applies_only_to_acceptance(self) -> None:
        source = (
            "No charter shall be granted by the Council: And no researcher holding "
            "any office under them, shall, without the Board's approval, accept of "
            "any grant, award, or title, from any Foundation or University."
        )
        frames = extract_frames(source)
        acceptance = [frame for frame in frames if "accept" in frame.predicate_options]
        self.assertEqual(len(acceptance), 6)
        self.assertTrue(all(frame.polarity == "negative" and frame.modality == "shall"
                            and frame.condition == "without the Board's approval"
                            for frame in acceptance))
        self.assertEqual({frame.subject_options[0] for frame in acceptance},
                         {"researcher holding office under the Council"})
        self.assertEqual({frame.object_options[0] for frame in acceptance}, {
            f"{item} from {source}"
            for item in ("grant", "award", "title")
            for source in ("Foundation", "University")
        })
        charter = [frame for frame in frames if "granted_by" in frame.predicate_options]
        self.assertEqual(len(charter), 1)
        self.assertIsNone(charter[0].condition)

    def test_semicolon_exception_stays_with_its_action(self) -> None:
        frames = extract_frames(
            "Article. II.\nSection. 2.\n"
            "The President shall be Commander in Chief of the Army and Navy "
            "of the United States; he shall have Power to grant Reprieves and "
            "Pardons for Offences against the United States, except in Cases "
            "of Impeachment."
        )
        commanders = [f for f in frames if f.predicate_options ==
                      ("commander_in_chief_of",)]
        grants = [f for f in frames if f.predicate_options == ("authorized_to",)]
        self.assertEqual(len(commanders), 2)
        self.assertTrue(all(f.condition is None for f in commanders))
        self.assertTrue(all("Impeachment" in (f.condition or "") for f in grants))

    def test_power_purpose_stays_on_preceding_actions(self) -> None:
        frames = extract_frames(
            "The Council may have Power to levy and collect Fees and Dues, "
            "to fund the laboratory; the Council may have Power to appoint "
            "officers, except during recess."
        )
        qualified = {
            frame.object_options[0]
            for frame in frames
            if frame.predicate_options == ("authorized_to",)
            and frame.condition == "to fund the laboratory"
        }
        self.assertEqual(
            qualified,
            {"levy Fees", "levy Dues", "collect Fees", "collect Dues"},
        )
        appointments = [
            frame for frame in frames
            if frame.predicate_options == ("authorized_to",)
            and "appoint officers" in frame.object_options
        ]
        self.assertTrue(appointments)
        self.assertTrue(all("fund the laboratory" not in (frame.condition or "")
                            for frame in appointments))

    def test_serial_list_actions_resolve_actor_and_shared_object(self) -> None:
        source = (
            "The Reviewers shall meet in the Archive. And they shall make a List "
            "of all the Entries selected, and of the Number of Marks for each; "
            "which List they shall sign and certify, and transmit sealed to the "
            "Registry, directed to the Curator."
        )
        actual = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in extract_frames(source) if frame.origin == "semantic"
        }
        self.assertIn(("Reviewers", "make_List_of", "all Entries selected", None),
                      actual)
        self.assertIn(("Reviewers", "include_in_List", "Number of Marks for each Entry",
                       None), actual)
        list_object = "List of all Entries selected and the Number of Marks for each"
        self.assertIn(("Reviewers", "sign", list_object, None), actual)
        self.assertIn(("Reviewers", "certify", list_object, None), actual)
        self.assertIn((
            "Reviewers", "transmit", list_object,
            "sealed; to the Registry; directed to the Curator",
        ), actual)
        self.assertIn((list_object, "transmitted_to", "Registry", None), actual)
        self.assertIn((list_object, "directed_to", "Curator", None), actual)

    def test_serial_list_rule_does_not_invent_positive_negated_actions(self) -> None:
        source = (
            "The Reviewers shall meet in the Archive. And they shall make a List "
            "of all Entries selected; which List they shall not sign and certify, "
            "and transmit sealed to the Registry."
        )
        serial = [
            frame for frame in extract_frames(source)
            if frame.origin == "semantic" and frame.predicate_options[0] in {
                "sign", "certify", "transmit", "transmitted_to",
            }
        ]
        self.assertEqual(serial, [])

    def test_serial_list_rule_splits_ballots_and_distinct_lists(self) -> None:
        source = (
            "The Delegates shall vote by ballot for Chair and Treasurer; they "
            "shall name in their ballots the person voted for as Chair, and in "
            "distinct ballots the person voted for as Treasurer, and they shall "
            "make distinct lists of all persons voted for as Chair, and of all "
            "persons voted for as Treasurer, and of the number of votes for each, "
            "which lists they shall sign and certify, and transmit sealed to the "
            "Office, directed to the Clerk."
        )
        actual = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0])
            for frame in extract_frames(source) if frame.origin == "semantic"
        }
        for role in ("Chair", "Treasurer"):
            self.assertIn(("Delegates", "vote_by_ballot_for", role), actual)
            self.assertIn(("Delegates", "make_distinct_list_of",
                           f"all persons voted for as {role}"), actual)
        self.assertIn(("Delegates", "name_in_distinct_ballots",
                       "person voted for as Treasurer"), actual)
        self.assertIn(("Delegates", "transmit",
                       "distinct lists of all persons voted for as Chair and Treasurer"),
                      actual)

        conditioned = extract_frames(
            "If the Council has quorum, the Council may have Power to collect "
            "Fees, to fund the laboratory."
        )
        self.assertTrue(any(
            frame.object_options[0] == "collect Fees"
            and frame.condition == "If the Council has quorum; to fund the laboratory"
            for frame in conditioned
        ))
        self.assertTrue(any(
            frame.object_options[0] == "collect Fees"
            and frame.condition == "If the Council has quorum"
            for frame in conditioned
        ))

    def test_coordinated_and_interposed_conditions_keep_their_branch(self) -> None:
        annual = extract_frames(
            "Article. I.\nSection. 4.\nThe Congress shall assemble at least "
            "once in every Year, and such Meeting shall be on the first Monday "
            "in December, unless they shall by Law appoint a different Day."
        )
        self.assertIsNone(next(f for f in annual if f.predicate_options ==
                               ("assemble_at",)).condition)
        amendment = extract_frames(
            "Article. V.\nThe Congress, whenever two thirds of both Houses "
            "shall deem it necessary, shall propose Amendments to this "
            "Constitution, or, on the Application of the Legislatures of two "
            "thirds of the several States, shall call a Convention for "
            "proposing Amendments."
        )
        proposal = next(f for f in amendment if f.predicate_options == ("proposes",))
        convention = next(f for f in amendment if f.predicate_options == ("call",))
        self.assertIn("two thirds of both Houses", proposal.condition or "")
        self.assertIn("Application of the Legislatures of two thirds",
                      convention.condition or "")
        self.assertNotIn("whenever two thirds of both Houses",
                         convention.condition or "")

        veto = extract_frames(
            "If the President approve the Bill he shall sign it, but if not "
            "he shall return it to the House."
        )
        returns = [f for f in veto if f.predicate_options == ("returns",)]
        self.assertTrue(returns)
        self.assertTrue(all("If the President approve" not in (f.condition or "")
                            for f in returns))

    def test_expands_authority_actions(self) -> None:
        actual = triples(
            "Congress shall have Power to lay and collect Taxes; to borrow Money; "
            "to regulate Commerce."
        )
        objects = {
            object_ for _, predicate, object_ in actual if predicate == "authorized_to"
        }
        self.assertTrue(
            {"lay Taxes", "collect Taxes", "borrow Money", "regulate Commerce"}
            <= objects
        )

    def test_expands_rights_and_prohibitions(self) -> None:
        actual = triples(
            "Congress shall make no law respecting religion; or abridging speech. "
            "The right of citizens to vote shall not be denied."
        )
        self.assertIn(("Congress", "abridges", "speech"), actual)
        self.assertIn(("citizens", "has_right_to", "vote"), actual)

    def test_first_amendment_preserves_the_no_law_operator(self) -> None:
        text = (
            "Amendment I\nCongress shall make no law respecting an establishment "
            "of religion, or prohibiting the free exercise thereof; or abridging "
            "the freedom of speech, or of the press; or the right of the people "
            "peaceably to assemble, and to petition the Government for a "
            "redress of grievances."
        )
        frames = extract_frames(text)
        actual = {
            (f.subject_options[0], f.predicate_options[0], f.object_options[0])
            for f in frames
        }
        self.assertIn(
            ("Congress", "enacts_law_respecting", "establishment of religion"),
            actual,
        )
        self.assertIn(
            ("Congress", "enacts_law_prohibiting", "free exercise of religion"),
            actual,
        )
        self.assertIn(
            ("Congress", "enacts_law_abridging", "freedom of the press"),
            actual,
        )
        self.assertNotIn(("Congress", "respects", "establishment of religion"), actual)
        self.assertEqual(len(frames), 8)

    def test_tenth_amendment_reservation_keeps_its_conditions(self) -> None:
        text = (
            "Amendment X\nThe powers not delegated to the United States by "
            "the Constitution, nor prohibited by it to the States, are reserved "
            "to the States respectively, or to the people."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 1)
        frame = frames[0]
        self.assertEqual(frame.subject_options, ("powers",))
        self.assertEqual(frame.predicate_options, ("reserved_to",))
        self.assertEqual(frame.object_options, ("States respectively or people",))
        self.assertIn("not delegated", frame.condition)
        self.assertIn("not prohibited", frame.condition)

    def test_third_amendment_separates_peace_and_war_rules(self) -> None:
        text = (
            "Amendment III\nNo Soldier shall, in time of peace be quartered "
            "in any house, without the consent of the Owner, nor in time of war, "
            "but in a manner to be prescribed by law."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 2)
        self.assertEqual(
            {(f.predicate_options[0], f.condition) for f in frames},
            {
                ("quartered_in", "in time of peace; without consent of the Owner"),
                ("requires", "in time of war"),
            },
        )

    def test_biomedical_setting_and_incubation_duration(self) -> None:
        text = (
            "In macrophages, IL-10 suppresses TNF-alpha expression by inhibiting "
            "NF-kB activation. Cells were washed with PBS and incubated for "
            "30 minutes."
        )
        frames = extract_frames(text)
        mechanism = [
            f for f in frames if f.subject_options[0] == "IL-10"
        ]
        self.assertEqual(len(mechanism), 2)
        self.assertTrue(all(f.condition == "In macrophages" for f in mechanism))
        duration = next(f for f in frames if f.predicate_options == ("has_duration_minutes",))
        self.assertEqual(duration.subject_options, ("incubation of Cells",))

    def test_fourth_amendment_covers_protections_and_warrant_rules(self) -> None:
        text = (
            "Amendment IV\nThe right of the people to be secure in their "
            "persons, houses, papers, and effects, against unreasonable searches "
            "and seizures, shall not be violated, and no Warrants shall issue, "
            "but upon probable cause, supported by Oath or affirmation, and "
            "particularly describing the place to be searched, and the persons "
            "or things to be seized."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 21)
        self.assertEqual(
            sum(f.predicate_options == ("has_right_to",) for f in frames), 8
        )
        self.assertEqual(
            sum(f.predicate_options == ("has_status",) and f.polarity == "negative"
                for f in frames), 8
        )
        self.assertIn(
            ("Warrants", "requires", "probable cause"),
            {(f.subject_options[0], f.predicate_options[0], f.object_options[0])
            for f in frames},
        )

    def test_fifth_amendment_keeps_each_exception_with_its_clause(self) -> None:
        text = (
            "Amendment V\nNo person shall be held to answer for a capital, or "
            "otherwise infamous crime, unless on a presentment or indictment "
            "of a Grand Jury, except in cases arising in the land or naval forces, "
            "or in the Militia, when in actual service in time of War or public "
            "danger; nor shall any person be subject for the same offence to be "
            "twice put in jeopardy of life or limb; nor shall be compelled in any "
            "criminal case to be a witness against himself, nor be deprived of "
            "life, liberty, or property, without due process of law; nor shall "
            "private property be taken for public use, without just compensation."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 8)
        double_jeopardy = next(
            f for f in frames if f.predicate_options == ("subject_to",)
        )
        self.assertEqual(double_jeopardy.condition, "for the same offence")
        self.assertTrue(all(f.polarity == "negative" for f in frames))
        self.assertEqual(
            sum(f.predicate_options == ("deprived_of",) for f in frames), 3
        )

    def test_sixth_amendment_keeps_accused_as_rights_holder(self) -> None:
        text = (
            "Amendment VI\nIn all criminal prosecutions, the accused shall "
            "enjoy the right to a speedy and public trial, by an impartial jury "
            "of the State and district wherein the crime shall have been committed, "
            "which district shall have been previously ascertained by law, and "
            "to be informed of the nature and cause of the accusation; to be "
            "confronted with the witnesses against him; to have compulsory "
            "process for obtaining witnesses in his favor, and to have the "
            "Assistance of Counsel for his defence."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 10)
        self.assertEqual(
            sum(f.subject_options == ("accused",) and f.predicate_options == ("has_right_to",)
                for f in frames), 9
        )
        self.assertTrue(
            all("in all criminal prosecutions" in (f.condition or "") for f in frames)
        )

    def test_seventh_amendment_does_not_copy_threshold_to_reexamination(self) -> None:
        text = (
            "Amendment VII\nIn Suits at common law, where the value in controversy "
            "shall exceed twenty dollars, the right of trial by jury shall be "
            "preserved, and no fact tried by a jury, shall be otherwise re-examined "
            "in any Court of the United States, than according to the rules of "
            "the common law."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 2)
        right, reexamination = frames
        self.assertIn("twenty dollars", right.condition)
        self.assertEqual(
            reexamination.condition,
            "except according to the rules of the common law",
        )
        self.assertEqual(reexamination.polarity, "negative")

    def test_eleventh_amendment_separates_suit_and_plaintiff_categories(self) -> None:
        text = (
            "AMENDMENT XI\nThe Judicial power of the United States shall not be "
            "construed to extend to any suit in law or equity, commenced or "
            "prosecuted against one of the United States by Citizens of another "
            "State, or by Citizens or Subjects of any Foreign State."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 6)
        self.assertEqual(
            {f.object_options[0] for f in frames},
            {
                "suit in law against one of the United States",
                "suit in equity against one of the United States",
            },
        )
        self.assertTrue(all(f.polarity == "negative" for f in frames))

    def test_sixteenth_amendment_keeps_tax_object_and_exemptions(self) -> None:
        text = (
            "AMENDMENT XVI\nThe Congress shall have power to lay and collect "
            "taxes on incomes, from whatever source derived, without apportionment "
            "among the several States, and without regard to any census or enumeration."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 2)
        self.assertEqual(
            {f.object_options[0] for f in frames},
            {
                "lay taxes on incomes from whatever source derived",
                "collect taxes on incomes from whatever source derived",
            },
        )
        self.assertTrue(all("without apportionment" in f.condition for f in frames))

    def test_twenty_seventh_amendment_requires_intervening_election(self) -> None:
        text = (
            "AMENDMENT XXVII\nNo law, varying the compensation for the services "
            "of the Senators and Representatives, shall take effect, until an "
            "election of Representatives shall have intervened."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 2)
        self.assertTrue(
            all(f.predicate_options == ("takes_effect_only_after",) for f in frames)
        )
        self.assertEqual(
            {f.subject_options[0] for f in frames},
            {
                "law varying compensation for services of Senators",
                "law varying compensation for services of Representatives",
            },
        )

    def test_article_two_removal_requires_impeachment_and_conviction(self) -> None:
        text = (
            "Article. II.\nSection. 4.\nThe President, Vice President and all "
            "civil Officers of the United States, shall be removed from Office "
            "on Impeachment for, and Conviction of, Treason, Bribery, or other "
            "high Crimes and Misdemeanors."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 9)
        self.assertEqual(
            {f.subject_options[0] for f in frames},
            {"President", "Vice President", "civil Officers of the United States"},
        )
        self.assertTrue(
            all("Impeachment for and Conviction of" in f.condition for f in frames)
        )

    def test_twenty_first_amendment_preserves_local_law_condition(self) -> None:
        text = (
            "AMENDMENT XXI\nSection 2.\nThe transportation or importation into "
            "any State, Territory, or possession of the United States for "
            "delivery or use therein of intoxicating liquors, in violation of "
            "the laws thereof, is hereby prohibited."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 6)
        self.assertEqual(
            {f.object_options[0] for f in frames},
            {"State", "Territory", "possession of the United States"},
        )
        self.assertTrue(
            all(f.polarity == "negative" and
                "in violation of the laws thereof" in f.condition for f in frames)
        )

    def test_senate_oath_uses_only_present_antecedent_context(self) -> None:
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "benchmarks/fixtures/constitution-article-1-section-3-reviewed.json"
        )
        text = json.loads(fixture_path.read_text())["text"]
        frames = extract_frames(text)
        self.assertEqual(len(frames), 28)
        oath = next(f for f in frames if f.predicate_options == ("sits_under",))
        self.assertIn("The Senate shall have the sole Power", oath.context)
        self.assertEqual(
            extract_frames(
                "Article. I.\nSection. 3.\nWhen sitting for that Purpose, "
                "they shall be on Oath or Affirmation."
            ),
            [],
        )

    def test_ratification_condition_uses_current_amendment(self) -> None:
        text = (
            "AMENDMENT XX\nSection 6.\nThis article shall be inoperative "
            "unless it shall have been ratified as an amendment to the "
            "Constitution by the legislatures of three-fourths of the several "
            "States within seven years from the date of its submission."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].subject_options, ("Amendment 20",))
        self.assertIn("three-fourths", frames[0].condition)
        self.assertEqual(frames[0].source_unit, "AMENDMENT_20_SECTION_6")

    def test_twentieth_amendment_keeps_meeting_date_exception(self) -> None:
        text = (
            "AMENDMENT XX\nSection 2.\nThe Congress shall assemble at least "
            "once in every year, and such meeting shall begin at noon on the "
            "3d day of January, unless they shall by law appoint a different day."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 3)
        annual = next(f for f in frames if f.predicate_options == ("minimum_meetings_per_year",))
        date = next(f for f in frames if f.predicate_options == ("begins_at",))
        self.assertIsNone(annual.condition)
        self.assertIn("unless Congress by law appoints", date.condition)

    def test_twentieth_amendment_successor_dates_follow_each_office(self) -> None:
        text = (
            "AMENDMENT XX\nSection 1.\nThe terms of the President and Vice "
            "President shall end at noon on the 20th day of January, and the "
            "terms of Senators and Representatives at noon on the 3d day of "
            "January, of the years in which such terms would have ended if "
            "this article had not been ratified; and the terms of their "
            "successors shall then begin."
        )
        claims = extract_candidates(text)
        self.assertEqual(len(claims), 8)
        successor = next(item for item in claims if
                         item.subject == "term of successor to Senator")
        self.assertEqual((successor.predicate, successor.object),
                         ("begins_at", "noon on the 3d day of January"))
        self.assertIn("would have ended", successor.condition or "")

    def test_vice_presidential_vacancy_requires_both_houses(self) -> None:
        text = (
            "AMENDMENT XXV\nSection 2.\nWhenever there is a vacancy in the "
            "office of the Vice President, the President shall nominate a Vice "
            "President who shall take office upon confirmation by a majority "
            "vote of both Houses of Congress."
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 2)
        taking_office = next(f for f in frames if f.predicate_options == ("takes_office",))
        self.assertIn("majority vote of both Houses", taking_office.condition)

    def test_voting_rights_atomize_forbidden_grounds(self) -> None:
        text = (
            "AMENDMENT XV\nSection 1.\nThe right of citizens of the United "
            "States to vote shall not be denied or abridged by the United States "
            "or by any State on account of race, color, or previous condition "
            "of servitude--"
        )
        frames = extract_frames(text)
        self.assertEqual(len(frames), 13)
        self.assertEqual(
            {f.condition for f in frames if f.polarity == "negative"},
            {
                "on account of race", "on account of color",
                "on account of previous condition of servitude",
            },
        )

    def test_extracts_scientific_relations(self) -> None:
        actual = triples(
            "BRCA1 inhibits tumor growth. The encoder contains self-attention layers."
        )
        self.assertIn(("BRCA1", "inhibits", "tumor growth"), actual)
        self.assertIn(("encoder", "contains", "self-attention layers"), actual)

    def test_extracts_table_measurements(self) -> None:
        text = (
            "2 Results\n\nTable 7: Evaluation results\n\n"
            "Model        Accuracy\nAlpha        91.5\n\n\n3 Conclusion\n"
        )
        claim = next(
            item
            for item in extract_candidates(text)
            if item.subject == "Alpha" and item.predicate == "has_accuracy"
        )
        self.assertEqual((claim.object, claim.object_kind), ("91.5", "decimal"))
        self.assertEqual(claim.source_locator, "Table 7")

    def test_transposed_measurements_keep_column_entities_and_units(self) -> None:
        text = (
            "Table 8: Observatory measurements\n\n"
            "Metric                  Mercury    Venus    Earth\n"
            "Mass (10^24 kg)         0.330      4.87     5.97\n"
            "Rotation Period (hours)  1407.6     -5832.5  23.9\n\n\n"
        )
        claims = extract_candidates(text)
        actual = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertIn(("Mercury", "has_mass_10_24_kg", "0.330"), actual)
        self.assertIn(("Venus", "has_rotation_period_hours", "-5832.5"), actual)
        self.assertEqual(len(actual), 6)

    def test_tracks_source_sections(self) -> None:
        claims = extract_candidates(
            "Abstract\nAlpha uses beta.\n2.1. Results\nEpsilon uses zeta."
        )
        units = {(claim.subject, claim.source_unit) for claim in claims}
        self.assertIn(("Alpha", "ABSTRACT"), units)
        self.assertIn(("Epsilon", "SECTION_2_1_RESULTS"), units)

    def test_cleans_pdf_wraps_and_gutenberg_boilerplate(self) -> None:
        wrapped = extract_candidates("Acme con-\ntains three divisions.")[0]
        self.assertEqual((wrapped.predicate, wrapped.object), ("contains", "three divisions"))
        document = (
            "metadata\n*** START OF THE PROJECT GUTENBERG EBOOK SAMPLE ***\n"
            "CHAPTER I. Arrival\nAlice entered Wonderland.\n"
            "*** END OF THE PROJECT GUTENBERG EBOOK SAMPLE ***\nlicense"
        )
        self.assertNotIn("license", clean_document(document))

    def test_resolves_declared_acronyms(self) -> None:
        text = "Knowledge Graph Compiler (KGC) supports RDF. KGC uses Jev."
        self.assertEqual(
            canonical_label("KGC", find_aliases(text)), "Knowledge Graph Compiler"
        )

    def test_rejects_unresolved_pronouns_and_fragments(self) -> None:
        self.assertEqual(extract_candidates("It uses RDF."), [])
        self.assertEqual(extract_frames("8 after training for 3."), [])

    def test_biomedical_main_relation_and_mechanism(self) -> None:
        actual = triples(
            "In macrophages, IL-10 suppresses TNF-alpha expression by "
            "inhibiting NF-kB activation."
        )
        self.assertIn(("IL-10", "suppresses", "TNF-alpha expression"), actual)
        self.assertIn(("IL-10", "inhibits", "NF-kB activation"), actual)

    def test_intervention_coordination_resolves_antecedents_and_hedge(self) -> None:
        claims = extract_candidates(
            "Overexpression of GeneA or GeneB in renal cells blocked marker "
            "induction by CytokineX, whereas knockdown of them sensitized the "
            "cells to CytokineX stimulation, suggesting that GeneA signaling "
            "is not responsible for marker induction."
        )
        by_triple = {(item.subject, item.predicate, item.object): item for item in claims}
        for gene in ("GeneA", "GeneB"):
            self.assertEqual(
                by_triple[(f"overexpression of {gene}", "blocked",
                           "marker induction by CytokineX")].condition,
                "in renal cells",
            )
            self.assertIn(
                (f"knockdown of {gene}", "sensitized",
                 "renal cells to CytokineX stimulation"), by_triple,
            )
        conclusion = by_triple[("GeneA signaling", "responsible_for", "marker induction")]
        self.assertEqual((conclusion.modality, conclusion.polarity),
                         ("suggested", "negative"))

    def test_downstream_blockade_preserves_partial_and_negative_results(self) -> None:
        claims = extract_candidates(
            "Blockade of several SignalX downstream pathways such as KinaseA or "
            "KinaseB, but not KinaseC and KinaseD, only partially inhibited "
            "protein expression."
        )
        actual = {(item.subject, item.predicate, item.object): item.polarity
                  for item in claims}
        for kinase in ("KinaseA", "KinaseB"):
            self.assertEqual(actual[(kinase, "downstream_of", "SignalX")], "positive")
            self.assertEqual(actual[(f"blockade of {kinase}", "partially_inhibited",
                                     "protein expression")], "positive")
        for kinase in ("KinaseC", "KinaseD"):
            self.assertEqual(actual[(f"blockade of {kinase}", "inhibited",
                                     "protein expression")], "negative")
        self.assertEqual(len(actual), 6)

    def test_induction_coreference_keeps_separate_biological_actors(self) -> None:
        claims = extract_candidates(
            "SignalX stimulated receptor activation in epithelial cells, and "
            "ectopic expression of KinaseA induced enzyme expression, whereas "
            "inhibition of KinaseA abolished its induction."
        )
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        self.assertEqual(actual[("SignalX", "stimulated", "receptor activation")].condition,
                         "in epithelial cells")
        self.assertIn(("ectopic expression of KinaseA", "induced", "enzyme expression"),
                      actual)
        self.assertIn(("inhibition of KinaseA", "abolished", "enzyme induction"), actual)

    def test_biological_outcome_lists_keep_settings_and_opposite_effect(self) -> None:
        claims = extract_candidates(
            "FactorQ was reversely correlated with disease progression and "
            "promoted cell growth, migration in vivo and in vitro. While "
            "overexpression of FactorQ had opposite effect."
        )
        actual = {(item.subject, item.predicate, item.object, item.condition)
                  for item in claims}
        self.assertIn(("FactorQ", "inversely_correlated_with",
                       "disease progression", None), actual)
        self.assertIn(("FactorQ", "promoted", "migration", "in vitro"), actual)
        self.assertIn(("overexpression of FactorQ", "had_opposite_effect_to",
                       "FactorQ-promoted cell growth and migration", None), actual)

    def test_biological_chain_and_procedure_list_remain_separate(self) -> None:
        claims = extract_candidates(
            "Loss of GeneX promoted hydrolysis of ProteinY and then released "
            "DomainZ, subsequently, activated the PathwayQ pathway. "
            "RNA isolation, qPCR and immunoblotting were performed as "
            "previously described."
        )
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        self.assertIn(("ProteinY hydrolysis", "released", "DomainZ"), actual)
        self.assertIn(("DomainZ", "activated", "PathwayQ pathway"), actual)
        self.assertEqual(actual[("qPCR", "has_status", "performed")].condition,
                         "as previously described")

    def test_biological_depletion_list_keeps_one_actor_and_all_outcomes(self) -> None:
        claims = extract_candidates(
            "Accordingly, GeneQ depletion trimmed fiber growth, prolonged "
            "receptor signaling, prevented apoptosis and enhanced random "
            "cell migration."
        )
        actual = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertEqual(actual, {
            ("GeneQ depletion", "trimmed", "fiber growth"),
            ("GeneQ depletion", "prolonged", "receptor signaling"),
            ("GeneQ depletion", "prevented", "apoptosis"),
            ("GeneQ depletion", "enhanced", "random cell migration"),
        })

    def test_biological_contrast_preserves_negative_mutant_result(self) -> None:
        claims = extract_candidates(
            "In animal models, silencing GeneQ increased metastasis, whereas "
            "ectopic expression of the wild-type form, unlike expression of "
            "two, relatively unstable oncogenic mutants from human tumors, "
            "inhibited metastasis."
        )
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        mutant = actual[("expression of two oncogenic GeneQ mutants", "inhibited",
                         "metastasis")]
        self.assertEqual(mutant.polarity, "negative")
        self.assertEqual(mutant.condition, "in animal models")
        self.assertIsNone(actual[("two oncogenic GeneQ mutants", "originated_from",
                                  "human tumors")].condition)

    def test_interstate_credit_keeps_recipient_origin_and_law_condition(self) -> None:
        claims = extract_candidates(
            "Article. IV.\nSection. 1.\nFull Faith and Credit shall be given in "
            "each State to the public Acts, Records, and judicial Proceedings "
            "of every other State. And the Congress may by general Laws prescribe "
            "the Manner in which such Acts, Records and Proceedings shall be "
            "proved, and the Effect thereof."
        )
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        self.assertEqual(len(actual), 9)
        credit = actual[("State", "gives_full_faith_and_credit_to",
                         "judicial Proceedings of every other State")]
        self.assertEqual((credit.modality, credit.condition, credit.source_unit),
                         ("shall", "in each State", "ARTICLE_4_SECTION_1"))
        proof = actual[("Congress", "may_prescribe_manner_of_proof_for", "Records")]
        self.assertEqual((proof.modality, proof.condition), ("may", "by general Laws"))

    def test_treason_evidence_and_attainder_limits_are_qualified(self) -> None:
        claims = extract_candidates(
            "Article. III.\nSection. 3.\nTreason against the United States, "
            "shall consist only in levying War against them, or in adhering "
            "to their Enemies, giving them Aid and Comfort. No Person shall "
            "be convicted of Treason unless on the Testimony of two Witnesses "
            "to the same overt Act, or on Confession in open Court. The Congress "
            "shall have Power to declare the Punishment of Treason, but no "
            "Attainder of Treason shall work Corruption of Blood, or Forfeiture "
            "except during the Life of the Person attainted."
        )
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        self.assertEqual(len(actual), 6)
        conviction = actual[("Person", "convicted_of", "Treason")]
        self.assertEqual(conviction.polarity, "negative")
        self.assertIn("two Witnesses to the same overt Act", conviction.condition)
        self.assertIn("Confession in open Court", conviction.condition)
        forfeiture = actual[("Attainder of Treason", "works", "Forfeiture")]
        self.assertEqual(forfeiture.polarity, "negative")
        self.assertEqual(forfeiture.condition,
                         "beyond the Life of the Person attainted")

    def test_poll_tax_right_covers_offices_actors_actions_and_tax_grounds(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XXIV\nSection 1.\nThe right of citizens of the United "
            "States to vote in any primary or other election for President or "
            "Vice President, for electors for President or Vice President, or "
            "for Senator or Representative in Congress, shall not be denied "
            "or abridged by the United States or any State by reason of failure "
            "to pay any poll tax or other tax."
        )
        self.assertEqual(len(claims), 54)
        actual = {(item.subject, item.predicate, item.object, item.condition): item
                  for item in claims}
        example = actual[(
            "right of citizens of the United States to vote", "abridged_by", "State",
            "in any primary or other election for Representative in Congress; "
            "by reason of failure to pay any other tax",
        )]
        self.assertEqual((example.modality, example.polarity, example.source_unit),
                         ("shall", "negative", "AMENDMENT_24_SECTION_1"))

    def test_acting_president_rule_keeps_both_declarations_as_conditions(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XXV\nSection 3.\nWhenever the President transmits to "
            "the President pro tempore of the Senate and the Speaker of the "
            "House of Representatives his written declaration that he is unable "
            "to discharge the powers and duties of his office, and until he "
            "transmits to them a written declaration to the contrary, such "
            "powers and duties shall be discharged by the Vice President as "
            "Acting President."
        )
        self.assertEqual(len(claims), 2)
        self.assertEqual({claim.subject for claim in claims},
                         {"powers of the President", "duties of the President"})
        for claim in claims:
            self.assertIn("President pro tempore of the Senate", claim.condition)
            self.assertIn("until he transmits a written declaration to the contrary",
                          claim.condition)
            self.assertEqual(claim.source_unit, "AMENDMENT_25_SECTION_3")

    def test_ineffective_stimulation_preserves_all_negative_functions(self) -> None:
        claims = extract_candidates(
            "From a functional point of view, LigandL stimulation of KO "
            "cancer cells was ineffective in eliciting intracellular signaling "
            "and in sustaining biological functions predictive of malignancy "
            "in vitro (i.e., anchorage-independent growth, invasion, and "
            "survival in the absence of matrix adhesion)."
        )
        self.assertEqual(len(claims), 7)
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        for outcome in ("anchorage-independent growth", "invasion",
                        "survival in the absence of matrix adhesion"):
            finding = actual[("LigandL stimulation of KO cancer cells", "sustained",
                              outcome)]
            self.assertEqual((finding.polarity, finding.condition),
                             ("negative", "in vitro"))
            self.assertIn((outcome, "predictive_of", "malignancy"), actual)

    def test_ablation_effect_does_not_invent_direction(self) -> None:
        claims = extract_candidates(
            "In both experimental models, GeneQ ablation affects the time "
            "of onset, the number, and the size of metastatic lesions."
        )
        self.assertEqual(len(claims), 3)
        self.assertEqual({claim.predicate for claim in claims}, {"affects"})
        self.assertEqual({claim.condition for claim in claims},
                         {"in both experimental models"})

    def test_reported_level_and_in_vivo_outcome_lists_keep_their_actor(self) -> None:
        claims = extract_candidates(
            "We observed that the GeneQ levels were increased in resistant "
            "cells and in metastatic samples. GeneQ promoted cell invasion "
            "and lung metastasis in vivo."
        )
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        self.assertIn(("GeneQ levels", "increased_in", "resistant cells"), actual)
        self.assertIn(("GeneQ levels", "increased_in", "metastatic samples"), actual)
        self.assertEqual(actual[("GeneQ", "promoted", "lung metastasis")].condition,
                         "in vivo")

    def test_downstream_pathway_requirement_keeps_direction(self) -> None:
        claims = extract_candidates(
            "The cellular and biological effects elicited by GeneQ were "
            "consistent with the reduced levels of ProteinR observed in cancer "
            "cells, and GeneQ-mediated ProteinR suppression activated the "
            "KinaseK pathway, which is required for GeneQ-mediated EMT."
        )
        actual = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertIn(("GeneQ-mediated ProteinR suppression", "activated",
                       "KinaseK pathway"), actual)
        self.assertIn(("KinaseK pathway", "required_for", "GeneQ-mediated EMT"),
                      actual)

    def test_revenue_modifier_does_not_become_spurious_verb(self) -> None:
        actual = triples(
            "All Bills for raising Revenue shall originate in the House of Representatives."
        )
        self.assertIn(
            ("Bills for raising Revenue", "originates_in", "House of Representatives"),
            actual,
        )
        self.assertFalse(any(predicate == "rais" for _, predicate, _ in actual))

    def test_parenthetical_passive_preserves_subject_and_negation(self) -> None:
        actual = extract_candidates(
            "No Senator or Representative shall, during the Time for which he was "
            "elected, be appointed to any civil Office under the Authority of the United States."
        )
        self.assertTrue(any(
            item.subject == "Senator or Representative"
            and item.predicate == "appointed_to"
            and item.polarity == "negative"
            for item in actual
        ))

    def test_constitution_section_markers(self) -> None:
        actual = extract_candidates(
            "Article. I.\nSection. 5.\nEach House shall keep a Journal.\n"
            "Section. 7.\nAll Bills for raising Revenue shall originate in the House of Representatives."
        )
        self.assertTrue(any(
            item.predicate == "originates_in" and item.source_unit == "ARTICLE_1_SECTION_7"
            for item in actual
        ))

    def test_heading_resets_prior_subject_context(self) -> None:
        claims = extract_candidates(
            "Article. VI.\nNo religious Test shall be required.\n"
            "Article. VII.\nThe Ratification of nine States shall establish a Union."
        )
        self.assertFalse(any(
            item.source_unit == "ARTICLE_7" and "religious Test" in item.subject
            for item in claims
        ))

    def test_timed_prohibition_distributes_actions_and_places(self) -> None:
        claims = extract_candidates(
            "After two months from the ratification of this article the "
            "manufacture, distribution, or transportation of medicinal oils "
            "within, the importation thereof into, or the exportation thereof "
            "from the Republic and all territory subject to the jurisdiction "
            "thereof for commercial purposes is hereby prohibited."
        )
        self.assertEqual(len(claims), 10)
        expected = next(item for item in claims if
                        item.subject == "exportation of medicinal oils" and
                        item.object == "territory subject to jurisdiction of Republic")
        self.assertEqual(expected.predicate, "permitted_from")
        self.assertEqual(expected.polarity, "negative")
        self.assertEqual(expected.condition,
                         "after two months from ratification of this article; "
                         "for commercial purposes")

    def test_explicit_subject_overrides_prior_legal_clause(self) -> None:
        claims = extract_candidates(
            "The Senate of the United States shall be composed of two Senators "
            "from each State; and each Senator shall have one Vote."
        )
        self.assertTrue(any(
            claim.subject == "Senator" and claim.predicate == "has"
            and claim.object == "one Vote" for claim in claims
        ))
        self.assertFalse(any(
            claim.subject == "Senate of the United States" and claim.predicate == "has"
            and claim.object == "one Vote" for claim in claims
        ))

    def test_authority_continuation_carries_governing_context(self) -> None:
        frames = extract_frames(
            "Congress shall have Power to raise Armies;\nTo provide and maintain a Navy."
        )
        navy = next(frame for frame in frames if frame.object_options[0] == "provide Navy")
        self.assertIn("Congress shall have Power", navy.context)
        self.assertEqual(navy.subject_options[0], "Congress")

    def test_perfect_modal_auxiliary_is_not_a_has_relation(self) -> None:
        claims = extract_candidates(
            "The Trial shall be at such Place as the Congress may by Law have directed."
        )
        self.assertFalse(any(
            claim.subject == "Congress" and claim.predicate == "has"
            for claim in claims
        ))

    def test_scientific_condition_and_hedged_negation(self) -> None:
        conditioned = extract_candidates(
            "If a patient lacks CYP3A4, simvastatin may cause toxicity."
        )
        self.assertTrue(any(
            claim.subject == "simvastatin" and claim.predicate == "causes"
            and claim.object == "toxicity" and claim.modality == "may"
            and claim.condition == "If a patient lacks CYP3A4"
            for claim in conditioned
        ))
        negated = extract_candidates(
            "BRCA1 may not inhibit tumor growth in hypoxic cells."
        )
        self.assertTrue(any(
            claim.subject == "BRCA1" and claim.predicate == "inhibits"
            and claim.polarity == "negative" and claim.modality == "may"
            for claim in negated
        ))

    def test_voting_rights_protection_is_atomic_and_qualified(self) -> None:
        text = (
            "Amendment XIX\nThe right of citizens of the United States to vote "
            "shall not be denied or abridged by the United States or by any "
            "State on account of sex."
        )
        claims = extract_candidates(text)
        protections = {
            (claim.predicate, claim.object) for claim in claims
            if claim.subject == "right of citizens of the United States to vote"
        }
        self.assertEqual(protections, {
            ("denied_by", "United States"), ("abridged_by", "United States"),
            ("denied_by", "State"), ("abridged_by", "State"),
        })
        self.assertTrue(all(
            claim.polarity == "negative" and claim.modality == "shall"
            and claim.condition == "on account of sex"
            for claim in claims if claim.predicate in {"denied_by", "abridged_by"}
        ))

    def test_voting_age_condition_is_not_an_unqualified_claim(self) -> None:
        claims = extract_candidates(
            "The right of citizens of the United States, who are eighteen years "
            "of age or older, to vote shall not be denied or abridged by the United "
            "States or by any State on account of age."
        )
        self.assertFalse(any(
            claim.predicate == "has_right_to" and not claim.condition
            for claim in claims
        ))
        self.assertEqual(sum(claim.predicate == "denied_by" for claim in claims), 2)

    def test_presidential_term_limits_keep_distinct_conditions(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XXII\nSection 1.\nNo person shall be elected to the "
            "office of the President more than twice, and no person who has held "
            "the office of President, or acted as President, for more than two years "
            "of a term to which some other person was elected President shall be "
            "elected to the office of the President more than once."
        )
        limits = [claim for claim in claims if claim.predicate == "elected_to"]
        self.assertEqual(len(limits), 2)
        self.assertEqual({claim.condition.split("; ")[-1] for claim in limits},
                         {"more than twice", "more than once"})
        self.assertTrue(all(claim.polarity == "negative" for claim in limits))
        self.assertFalse(any(claim.object == "person" for claim in claims))

    def test_presidential_term_exception_keeps_effective_term(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XXII\nSection 1.\nBut this Article shall not apply to any "
            "person holding the office of President when this Article was proposed "
            "by the Congress, and shall not prevent any person who may be holding "
            "the office of President, or acting as President, during the term within "
            "which this Article becomes operative from holding the office of President "
            "or acting as President during the remainder of such term."
        )
        self.assertEqual({claim.object for claim in claims if claim.predicate == "prevents"},
                         {"holding the office of President", "acting as President"})
        self.assertTrue(all(claim.subject == "Amendment 22" and claim.polarity == "negative"
                            for claim in claims))

    def test_person_pronoun_inherits_actor_not_prior_object(self) -> None:
        claims = extract_candidates(
            "The President may require the Opinion of the Officer. "
            "He shall have Power to grant Pardons."
        )
        self.assertTrue(any(
            claim.subject == "President" and claim.predicate == "authorized_to"
            for claim in claims
        ))
        self.assertFalse(any(
            claim.subject == "Opinion" and claim.predicate == "has"
            for claim in claims
        ))

    def test_officer_clause_does_not_establish_the_president_by_law(self) -> None:
        claims = extract_candidates(
            "The President shall appoint all other Officers of the United States, "
            "whose Appointments are not herein otherwise provided for, and which "
            "shall be established by Law."
        )
        self.assertTrue(any(
            claim.subject == "other Officers of the United States"
            and claim.predicate == "established_by" and claim.object == "Law"
            for claim in claims
        ))
        self.assertFalse(any(
            claim.subject == "President" and claim.predicate == "established_by"
            for claim in claims
        ))

    def test_biological_determination_preserves_causal_subject(self) -> None:
        claims = extract_candidates(
            "Combinatorial regulation of a single splice site by two "
            "tissue-specific splicing regulators determines the binary fate "
            "of the entire transcript."
        )
        self.assertTrue(any(
            claim.subject == (
                "Combinatorial regulation of a single splice site by two "
                "tissue-specific splicing regulators"
            ) and claim.predicate == "determines"
            and claim.object == "binary fate of the entire transcript"
            for claim in claims
        ))

    def test_coordinated_biomedical_clauses_have_separate_subjects(self) -> None:
        claims = extract_candidates(
            "Simvastatin plasma concentration increased 30 times in this patient "
            "and statin induced muscle toxicity is related to the concentration "
            "of the statin in blood."
        )
        triples = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertIn(("Simvastatin plasma concentration", "increased", "30 times in this patient"), triples)
        self.assertIn(("statin", "induced", "muscle toxicity"), triples)

    def test_biomedical_mechanism_keeps_agent_for_by_clause(self) -> None:
        claims = extract_candidates(
            "KLF4 activates repair by facilitating DNA binding."
        )
        triples = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertIn(("KLF4", "activates", "repair"), triples)
        self.assertIn(("KLF4", "facilitates", "DNA binding"), triples)

    def test_biomedical_subject_uses_named_gene_without_descriptor(self) -> None:
        claims = extract_candidates(
            "The AHR target gene scinderin activates the WNT pathway by "
            "facilitating the nuclear translocation of β-catenin."
        )
        self.assertTrue(any(item.subject == "scinderin" and
                            item.predicate == "activates" for item in claims))
        self.assertTrue(any(item.subject == "scinderin" and
                            item.predicate == "facilitates" for item in claims))

    def test_biographical_relative_clause_uses_person(self) -> None:
        claims = extract_candidates(
            'Wilfried "Willi" Schneider (born 13 March 1963 in Mediaș, '
            'Transylvania) is a German skeleton racer who competed from '
            '1992 to 2002.'
        )
        self.assertTrue(any(
            item.subject == "Wilfried Willi Schneider"
            and item.predicate == "competed_from"
            and item.object == "1992 to 2002" for item in claims
        ))
        self.assertFalse(any(
            item.predicate == "competed_from"
            and item.subject != "Wilfried Willi Schneider" for item in claims
        ))

    def test_album_coreference_and_split_recording_credits(self) -> None:
        text = (
            "North Star is an album by Ada Reed. It was released in 2011 less "
            "than a month after her death and just two weeks shy of her 50th "
            "birthday. The other six tracks were recorded at Studio Nine in "
            "Canada by Nora Finch and Ravi Shah."
        )
        claims = extract_candidates(text)
        actual = {(item.subject, item.predicate, item.object): item for item in claims}
        self.assertIn(("North Star album", "album_by", "Ada Reed"), actual)
        self.assertEqual(actual[("North Star album", "released_after",
                                 "Ada Reed's death")].condition, "less than a month")
        self.assertIn(("Nora Finch", "recorded", "other six tracks of North Star"),
                      actual)
        self.assertIn(("Ravi Shah", "recorded", "other six tracks of North Star"),
                      actual)

    def test_medal_results_keep_count_and_each_year(self) -> None:
        claims = extract_candidates(
            'Wilfried "Willi" Schneider (born 13 March 1963 in Mediaș, '
            'Transylvania) is a German skeleton racer who competed from '
            "1992 to 2002. He won two medals in the men's skeleton event "
            'at the FIBT World Championships with a gold in 1998 and a '
            'bronze in 1999.'
        )
        wins = {item.object for item in claims if item.predicate == "won"}
        self.assertEqual(wins, {
            "two medals in the men's skeleton event at the FIBT World Championships",
            "gold medal in 1998 at the FIBT World Championships",
            "bronze medal in 1999 at the FIBT World Championships",
        })

    def test_shared_biomedical_object_keeps_common_complement(self) -> None:
        claims = extract_candidates(
            "Factor Q promotes invasion and metastasis of tumor cells and "
            "predicts the outcome of patients."
        )
        triples = {(item.subject, item.predicate, item.object) for item in claims}
        self.assertIn(("Factor Q", "promotes", "invasion of tumor cells"), triples)
        self.assertIn(("Factor Q", "promotes", "metastasis of tumor cells"), triples)
        self.assertIn(("Factor Q", "predicts", "outcome of patients"), triples)

    def test_eighth_amendment_elliptical_prohibitions_share_negation(self) -> None:
        claims = extract_candidates(
            "Amendment VIII\nExcessive bail shall not be required, nor "
            "excessive fines imposed, nor cruel and unusual punishments inflicted."
        )
        self.assertEqual(
            {(item.subject, item.predicate, item.object) for item in claims},
            {
                ("Excessive bail", "has_status", "required"),
                ("excessive fines", "has_status", "imposed"),
                ("cruel and unusual punishments", "has_status", "inflicted"),
            },
        )
        self.assertTrue(all(item.modality == "shall" and
                            item.polarity == "negative" for item in claims))

    def test_ninth_amendment_parallel_verb_keeps_shared_object(self) -> None:
        claims = extract_candidates(
            "Amendment IX\nThe enumeration in the Constitution, of certain "
            "rights, shall not be construed to deny or disparage others "
            "retained by the people."
        )
        self.assertEqual(
            {item.object for item in claims if item.predicate == "construed_to"},
            {"deny others retained by the people",
             "disparage others retained by the people"},
        )

    def test_shared_enforcement_power_keeps_both_actors(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XVIII\nSection 2.\nThe Congress and the several States "
            "shall have concurrent power to enforce this article by "
            "appropriate legislation."
        )
        self.assertEqual(
            {item.subject for item in claims if item.predicate == "authorized_to"},
            {"Congress", "several States"},
        )
        self.assertTrue(all(item.object.startswith("concurrently enforce")
                            for item in claims))

    def test_succession_condition_is_not_dropped(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XXV\nSection 1.\nIn case of the removal of the "
            "President from office or of his death or resignation, the Vice "
            "President shall become President."
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(
            claims[0].condition,
            "In case of the removal of the President from office or of his "
            "death or resignation",
        )

    def test_second_amendment_preserves_right_and_infringement_negation(self) -> None:
        claims = extract_candidates(
            "Amendment II\nA well regulated Militia, being necessary to the "
            "security of a free State, the right of the people to keep and bear "
            "Arms, shall not be infringed."
        )
        self.assertEqual(len(claims), 4)
        self.assertEqual(
            {(item.predicate, item.object) for item in claims
             if item.subject == "people"},
            {("has_right_to", "keep Arms"), ("has_right_to", "bear Arms")},
        )
        infringement = next(item for item in claims if item.object == "infringed")
        self.assertEqual(infringement.polarity, "negative")
        self.assertEqual(infringement.modality, "shall")

    def test_thirteenth_amendment_splits_locations_and_keeps_exception(self) -> None:
        claims = extract_candidates(
            "AMENDMENT XIII\nSection 1.\nNeither slavery nor involuntary "
            "servitude, except as a punishment for crime whereof the party "
            "shall have been duly convicted, shall exist within the United "
            "States, or any place subject to their jurisdiction."
        )
        self.assertEqual(len(claims), 4)
        self.assertEqual({item.subject for item in claims},
                         {"slavery", "involuntary servitude"})
        self.assertEqual({item.object for item in claims},
                         {"United States", "place subject to their jurisdiction"})
        self.assertTrue(all(item.polarity == "negative" and item.condition ==
                            "except as a punishment for crime whereof the party "
                            "shall have been duly convicted" for item in claims))

    def test_house_initial_allocations_keep_all_thirteen_states(self) -> None:
        claims = extract_candidates(
            "Article. I.\nSection. 2.\nThe Number of Representatives shall "
            "not exceed one for every thirty Thousand, but each State shall "
            "have at Least one Representative; and until such enumeration "
            "shall be made, the State of New Hampshire shall be entitled to "
            "chuse three, Massachusetts eight, Rhode-Island and Providence "
            "Plantations one, Connecticut five, New-York six, New Jersey four, "
            "Pennsylvania eight, Delaware one, Maryland six, Virginia ten, "
            "North Carolina five, South Carolina five, and Georgia three."
        )
        allocations = {
            item.subject: item.object for item in claims
            if item.predicate == "entitled_to_choose"
        }
        self.assertEqual(len(allocations), 13)
        self.assertEqual(allocations["State of New Hampshire"], "three Representatives")
        self.assertEqual(allocations["Rhode-Island and Providence Plantations"],
                         "one Representative")
        self.assertEqual(allocations["Georgia"], "three Representatives")
        self.assertTrue(all(item.condition == "until such enumeration shall be made"
                            for item in claims if item.predicate == "entitled_to_choose"))

    def test_house_representative_qualifications_are_three_distinct_rules(self) -> None:
        claims = extract_candidates(
            "Article. I.\nSection. 2.\nNo Person shall be a Representative "
            "who shall not have attained to the Age of twenty five Years, "
            "and been seven Years a Citizen of the United States, and who "
            "shall not, when elected, be an Inhabitant of that State in "
            "which he shall be chosen."
        )
        self.assertEqual(
            {(item.predicate, item.object) for item in claims},
            {("has_minimum_age_years", "25"),
             ("has_minimum_citizenship_years", "7"),
             ("inhabits", "State in which chosen")},
        )
        self.assertEqual(next(item for item in claims if item.predicate == "inhabits").condition,
                         "when elected")

    def test_biomedical_intervention_keeps_measured_cell_conditions(self) -> None:
        frames = extract_frames(
            "The upregulation of GENE1 induced a significant increase of early "
            "apoptosis in A1 cells (2% to 9%) and B2 cells (3% to 8%). "
            "The upregulation of GENE1 activated caspase 3 and caspase 9 "
            "in A1 and B2 cells."
        )
        findings = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in frames if frame.origin == "semantic"
        }
        self.assertIn(("GENE1 upregulation", "increased", "early apoptosis",
                       "in A1 cells; 2% to 9%"), findings)
        self.assertIn(("GENE1 upregulation", "increased", "early apoptosis",
                       "in B2 cells; 3% to 8%"), findings)
        self.assertIn(("GENE1 upregulation", "activated", "caspase 3",
                       "in A1 and B2 cells"), findings)
        self.assertIn(("GENE1 upregulation", "activated", "caspase 9",
                       "in A1 and B2 cells"), findings)
        self.assertEqual(len(frames), 4)

    def test_biomedical_intervention_splits_arms_and_opposite_directions(self) -> None:
        frames = extract_frames(
            "The overexpression of KLF4 alone or in A1/sh-OTHER cells "
            "upregulated the expression of MARKER1 and reduced the expression "
            "of MARKER2."
        )
        findings = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in frames if frame.origin == "semantic"
        }
        self.assertEqual(
            {(subject, predicate, target) for subject, predicate, target, _ in findings},
            {(subject, predicate, target)
             for subject in ("KLF4 overexpression alone",
                             "KLF4 overexpression in A1/sh-OTHER cells")
             for predicate, target in (("increased", "MARKER1 expression"),
                                       ("decreased", "MARKER2 expression"))},
        )
        self.assertTrue(all(condition for _, _, _, condition in findings))
        self.assertEqual(len(frames), 4)

    def test_biomedical_passive_knockdown_recovers_causal_anchor(self) -> None:
        frames = extract_frames(
            "Moreover, the expression of ACTB, as well as the pathway genes "
            "MYC, and FOS were significantly induced in KLF4-knockdown cells."
        )
        findings = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in frames if frame.origin == "semantic"
        }
        self.assertEqual(findings, {
            ("KLF4 knockdown", "increased", f"{target} expression",
             "in KLF4-knockdown cells")
            for target in ("ACTB", "MYC", "FOS")
        })
        self.assertEqual(len(frames), 3)

    def test_biomedical_expression_comparison_keeps_tissue_and_cell_line_baselines(self) -> None:
        frames = extract_frames(
            "Using AtlasOne, GENE1 was significantly downregulated in diseased "
            "tissues compared with adjacent normal tissues. "
            "The expression level of GENE1 in the aggressive cell lines A1, B2, "
            "and C3 was significantly decreased compared with indolent cell "
            "lines D4, E5 and F6."
        )
        findings = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in frames if frame.origin == "semantic"
        }
        self.assertIn(
            ("GENE1 expression", "decreased_in", "diseased tissues",
             "relative to adjacent normal tissues; AtlasOne analysis"), findings)
        self.assertIn(
            ("GENE1 expression", "lower_in", "A1, B2, and C3 cells",
             "compared with D4, E5, and F6; aggressive cell lines versus "
             "indolent cell lines"), findings)

    def test_biomedical_sample_group_comparisons_recover_perturbation(self) -> None:
        frames = extract_frames(
            "Xenograft tumours formed in sh-GENE2 group were larger than those "
            "in the control group. Tumours growth in the sh-GENE2 group was "
            "more rapid than that in the control group. The percentage of cells "
            "in G2/M phase in A1/oe-GENE2 (15% ± 1) was higher than that in "
            "A1/Vector cells (8% ± 1)."
        )
        findings = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in frames if frame.origin == "semantic"
        }
        self.assertIn(
            ("GENE2 knockdown", "increased", "xenograft tumour size",
             "sh-GENE2 xenograft group versus control mice"), findings)
        self.assertIn(
            ("GENE2 knockdown", "increased", "xenograft tumour growth rate",
             "sh-GENE2 xenograft group versus control mice"), findings)
        self.assertIn(
            ("GENE2 overexpression", "increased", "G2/M-phase cell fraction",
             "A1 cells; 15% ± 1 versus Vector 8% ± 1"), findings)

    def test_biomedical_organ_ratios_remain_separate_findings(self) -> None:
        frames = extract_frames(
            "We counted nodules in each liver and lung, and found that GENE3 "
            "knockdown increased the number of metastatic nodules compared to "
            "the control cells (lung: 4:1; live: 2:0)."
        )
        findings = {
            (frame.subject_options[0], frame.predicate_options[0],
             frame.object_options[0], frame.condition)
            for frame in frames if frame.origin == "semantic"
        }
        self.assertEqual(
            {(subject, predicate, target, condition) for subject, predicate,
              target, condition in findings if target == "metastatic nodule count"},
            {("GENE3 knockdown", "increased", "metastatic nodule count",
              "lung nodules; GENE3 knockdown versus control cells; 4:1"),
             ("GENE3 knockdown", "increased", "metastatic nodule count",
              "liver nodules; GENE3 knockdown versus control cells; 2:0")},
        )
        self.assertIn(("researchers", "counted", "nodules in each liver and lung", None),
                      findings)
        self.assertFalse(any(frame.origin != "semantic" and
                             frame.predicate_options[0] in {"counted", "founded"}
                             for frame in frames))

    def test_biomedical_intervention_preserves_a_second_distinct_effect(self) -> None:
        frames = extract_frames(
            "The upregulation of GENE1 activated caspase 3 in A1 cells and "
            "inhibited MARKER2 in B2 cells."
        )
        self.assertEqual(
            {(frame.subject_options[0], frame.predicate_options[0],
              frame.object_options[0], frame.condition) for frame in frames},
            {("GENE1 upregulation", "activated", "caspase 3", "in A1 cells"),
             ("GENE1 upregulation", "inhibited", "MARKER2", "in B2 cells")},
        )

    def test_biomedical_reported_intervention_has_named_actor_and_scope(self) -> None:
        frames = extract_frames(
            "These results indicated that the overexpression of GENE1 "
            "induces cell-cycle arrest and apoptosis in A1 cells."
        )
        self.assertEqual(
            {(frame.subject_options[0], frame.predicate_options[0],
              frame.object_options[0], frame.condition) for frame in frames},
            {("GENE1 overexpression", "induced", "cell-cycle arrest", "in A1 cells"),
             ("GENE1 overexpression", "induced", "apoptosis", "in A1 cells")},
        )

    def test_molecular_interaction_uses_result_and_hedge_not_assay_actor(self) -> None:
        source = (
            "LincQ specifically binds to ReceptorR. "
            "RNA immunoprecipitation assays demonstrated that ReceptorR Ab "
            "precipitated the lncRNA-LincQ while IgG Ab could not. "
            "Biotin RNA pull-down assay was performed, suggesting that LincQ "
            "directly interacted with ReceptorR."
        )
        frames = extract_frames(source)
        observed = {(f.subject_options[0], f.predicate_options[0],
                     f.object_options[0]): f for f in frames}
        self.assertIsNone(observed[("LincQ", "bound_to", "ReceptorR")].condition)
        self.assertEqual(observed[("LincQ", "associated_with", "ReceptorR")].condition,
                         "ReceptorR antibody RIP positive; IgG control negative")
        direct = observed[("LincQ", "directly_interacted_with", "ReceptorR")]
        self.assertEqual((direct.modality, direct.condition),
                         ("suggested", "Biotin RNA pull-down assay"))
        self.assertFalse(any(f.origin != "semantic" for f in frames))
        self.assertFalse(any(f.predicate_options[0] == "bound_to" for f in
                             extract_frames(
                                 "RIP assays showed ReceptorR Ab precipitated "
                                 "LincQ while IgG Ab could not."
                             )))

    def test_catalyzed_hydrolysis_has_molecule_actor_product_and_citation(self) -> None:
        frames = extract_frames(
            "ProteinA would be hydrolyzed and consecutively release DomainB "
            "(intracellular domain) when catalyzed by EnzymeC [17]."
        )
        observed = {(f.subject_options[0], f.predicate_options[0],
                     f.object_options[0]): f for f in frames}
        self.assertEqual(set(observed), {
            ("EnzymeC", "catalyzed", "ProteinA hydrolysis"),
            ("ProteinA hydrolysis", "released", "DomainB"),
        })
        self.assertTrue(all(f.modality == "general_mechanism" and
                            f.condition == "EnzymeC catalysis; cited prior report [17]"
                            for f in frames))
        self.assertTrue(all(f.attribution == "cited prior report [17]" for f in frames))

    def test_molecular_complex_keeps_members_location_and_cell_setting(self) -> None:
        frames = extract_frames(
            "DomainX is one of the components of PathwayY. "
            "DomainX colocalized with FactorA and β-UnitB to form a nuclear "
            "protein complex, leading to gene transcription [18]. "
            "In CellLine9 cells which showed the formation of DomainX and "
            "β-UnitB complex."
        )
        observed = {(f.subject_options[0], f.predicate_options[0],
                     f.object_options[0]): f for f in frames}
        self.assertIn(("DomainX", "component_of", "PathwayY"), observed)
        self.assertIn(("DomainX", "colocalized_with", "FactorA"), observed)
        self.assertIn(("DomainX", "colocalized_with", "β-UnitB"), observed)
        complex_name = "DomainX–FactorA–β-UnitB complex"
        self.assertIn((complex_name, "formed_in", "nucleus"), observed)
        self.assertIn((complex_name, "promoted", "gene transcription"), observed)
        prior_frames = [
            frame for frame in frames
            if frame.predicate_options[0] in {"colocalized_with", "formed_in", "promoted"}
        ]
        self.assertTrue(all(frame.attribution == "cited prior report [18]"
                            for frame in prior_frames))
        self.assertEqual(observed[("DomainX", "formed_complex_with", "β-UnitB")].condition,
                         "CellLine9 cells")
        self.assertIsNone(observed[("DomainX", "formed_complex_with", "β-UnitB")].attribution)
        self.assertFalse(any(f.origin != "semantic" for f in frames))
        self.assertFalse(any(
            f.predicate_options[0] == "formed_complex_with"
            for f in extract_frames(
                "The assay did not show the formation of DomainX and β-UnitB complex."
            )
        ))


if __name__ == "__main__":
    unittest.main()

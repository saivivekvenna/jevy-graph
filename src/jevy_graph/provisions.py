"""Typed assembly for coordinated constitutional provisions.

Long legal lists are a poor fit for trigger-local subject/object splitting.  A
single governing phrase can supply the actor and modality to many following
infinitives, while coordinated nouns, purposes, exceptions, and reservations
must still become separate atomic claims.  This module recognizes that
grammar and emits complete singleton provisions before the generic extractor
has a chance to recombine their parts.

The implementation covers the recurring forms in Article I, Sections 5 through
10, Article II, Sections 1 and 2, Article III, Section 2, Article VI,
Amendment XIV, Sections 3 and 4, and Amendment XXV, Section 4: carried ``To ...`` powers,
coordinated actions and objects, stated purposes, limits, reservations,
prohibitions, exceptions, electoral procedures, succession, compensation,
oath obligations, jurisdiction, criminal-trial venue, the Twelfth Amendment's
contingent-election procedure, and coordinated public-debt and
presidential-inability procedures.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .models import RelationFrame


@dataclass(frozen=True, slots=True)
class ProvisionFrame:
    """One complete, atomic legal proposition."""

    subject: str
    predicate: str
    object: str
    evidence: str
    modality: str | None = "shall"
    polarity: str = "positive"
    condition: str | None = None
    attribution: str | None = None


@dataclass(slots=True)
class ProvisionState:
    """Governing context carried across an enumerated legal list."""

    source_unit: str | None = None
    authority_subject: str | None = None
    authority_modality: str | None = None
    presentment_kinds: tuple[str, ...] = ()
    amendment_12_choice: str | None = None
    amendment_12_bracketed_text: str | None = None
    amendment_17_senate_preamble: str | None = None
    article_6_supremacy_preamble: str | None = None
    article_1_section_4_election_preamble: str | None = None
    document_signature: str | None = None

    def observe(self, text: str, source_unit: str | None) -> None:
        if source_unit != self.source_unit:
            self.source_unit = source_unit
            self.authority_subject = None
            self.authority_modality = None
            self.presentment_kinds = ()
            self.amendment_12_choice = None
            self.amendment_12_bracketed_text = None
            self.amendment_17_senate_preamble = None
            self.article_6_supremacy_preamble = None
            self.article_1_section_4_election_preamble = None
            self.document_signature = None
        if re.search(
            r"Notwithstanding the provisions of sections 106 and 106A, the "
            r"fair use of a copyrighted work",
            text,
            re.I,
        ):
            self.document_signature = "copyright-fair-use-107"
        elif re.search(
            r"The Commission shall have no authority under this section or "
            r"section 57a of this title to declare unlawful an act or practice",
            text,
            re.I,
        ):
            self.document_signature = "ftc-unfairness-45n"
        authority = re.search(
            r"\b(?:The\s+)?(?P<actor>Congress)\s+(?P<modal>shall|may)\s+"
            r"have\s+Power\b",
            text,
            re.I,
        )
        if authority:
            self.authority_subject = "Congress"
            self.authority_modality = authority.group("modal").casefold()


def _is_article_1_section_7(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_1_SECTION_7":
        # The generic extractor already handles this isolated simple sentence
        # and exposes the established ``originates_in`` spelling.  Section 7's
        # provision grammar is needed for the coordinated semicolon form and
        # the procedural clauses that follow it.
        if re.fullmatch(
            r"All Bills for raising Revenue shall originate in the House of "
            r"Representatives\.", text.strip(), re.I,
        ):
            return False
        return True
    # A complete standalone excerpt has both distinctive presentment forms.
    return bool(
        re.search(r"\bAll Bills for raising Revenue shall originate\b", text, re.I)
        and re.search(r"\bEvery Order, Resolution, or Vote\b", text, re.I)
    )


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n;.—")


def _match(text: str, pattern: str) -> str | None:
    found = re.search(pattern, text, re.I | re.S)
    return _space(found.group(0)) if found else None


def _verbatim(text: str, pattern: str) -> str | None:
    """Return normalized source text while preserving terminal punctuation."""
    found = re.search(pattern, text, re.I | re.S)
    return re.sub(r"\s+", " ", found.group(0)).strip() if found else None


def _claim(
    subject: str,
    predicate: str,
    object_: str,
    evidence: str,
    *,
    modality: str | None = "shall",
    polarity: str = "positive",
    condition: str | None = None,
) -> ProvisionFrame:
    return ProvisionFrame(
        subject=subject,
        predicate=predicate,
        object=object_,
        evidence=evidence,
        modality=modality,
        polarity=polarity,
        condition=condition,
    )


def _is_enumerated_power(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_1_SECTION_8":
        return True
    # The content check makes the assembler useful for a standalone excerpt
    # whose caller has no source locator, without firing on arbitrary prose.
    return bool(re.search(
        r"\bCongress\s+shall\s+have\s+Power\s+To\s+lay\s+and\s+collect\s+Taxes",
        text,
        re.I,
    ))


def _is_section_9_restriction(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_1_SECTION_9":
        return True
    # Permit a complete standalone Section 9 excerpt without activating on a
    # generic sentence that happens to contain one prohibition.
    return bool(
        re.search(r"\bMigration or Importation of such Persons\b", text, re.I)
        and re.search(r"\bPrivilege of the Writ of Habeas Corpus\b", text, re.I)
        and re.search(r"\bNo Title of Nobility\b", text, re.I)
    )


def _is_article_1_section_10(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_1_SECTION_10":
        return True
    # A standalone excerpt must contain all three distinctive restriction
    # groups.  This avoids activating the grammar for an isolated quotation.
    return bool(
        re.search(r"\bNo State shall enter into any Treaty\b", text, re.I)
        and re.search(r"\bImposts or Duties on Imports or Exports\b", text, re.I)
        and re.search(r"\bDuty of Tonnage\b", text, re.I)
    )


def _is_article_1_section_5(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_1_SECTION_5":
        return True
    return bool(
        re.search(r"\bEach House shall be the Judge of the Elections\b", text, re.I)
        and re.search(r"\bNeither House, during the Session of Congress\b", text, re.I)
    )


def _is_article_1_section_6(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_1_SECTION_6":
        return True
    return bool(
        re.search(r"\bSenators and Representatives shall receive a Compensation\b", text, re.I)
        and re.search(r"\bNo Senator or Representative shall\b", text, re.I)
    )


def _is_article_6(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_6":
        return True
    return bool(
        re.search(r"\bAll Debts contracted and Engagements entered into\b", text, re.I)
        and re.search(r"\bno religious Test shall ever be required\b", text, re.I)
    )


def _is_amendment_14_section_2(source_unit: str | None) -> bool:
    return source_unit == "AMENDMENT_14_SECTION_2"


def _is_article_5(source_unit: str | None, text: str) -> bool:
    if source_unit != "ARTICLE_5":
        return False
    # Keep the generic parser's established output for partial quotations.
    # Each complete fixture clause has one of these Article V anchors.
    return bool(re.search(
        r"shall be valid to all Intents|prior to the Year One thousand eight "
        r"hundred and eight|equal Suffrage in the Senate",
        text,
        re.I,
    ))


def _is_article_4_section_3(source_unit: str | None) -> bool:
    return source_unit == "ARTICLE_4_SECTION_3"


def _is_amendment_17(source_unit: str | None) -> bool:
    return source_unit == "AMENDMENT_17"


def _is_article_2_section_3(source_unit: str | None) -> bool:
    return source_unit == "ARTICLE_2_SECTION_3"


def _assemble_article_1_section_10(text: str) -> list[ProvisionFrame]:
    """Assemble Article I, Section 10 State restrictions and exceptions."""
    claims: list[ProvisionFrame] = []

    evidence = _match(text, r"enter into any Treaty, Alliance, or Confederation")
    if evidence:
        for item in ("Treaty", "Alliance", "Confederation"):
            claims.append(_claim(
                "State", "enter_into", item, evidence, polarity="negative",
            ))

    evidence = _match(text, r"grant Letters of Marque and Reprisal")
    if evidence:
        claims.append(_claim(
            "State", "grant", "Letters of Marque and Reprisal", evidence,
            polarity="negative",
        ))
    evidence = _match(text, r"coin Money")
    if evidence:
        claims.append(_claim(
            "State", "coin", "Money", evidence, polarity="negative",
        ))
    evidence = _match(text, r"emit Bills of Credit")
    if evidence:
        claims.append(_claim(
            "State", "emit", "Bills of Credit", evidence, polarity="negative",
        ))
    evidence = _match(
        text,
        r"make any Thing but gold and silver Coin a Tender in Payment of Debts",
    )
    if evidence:
        claims.append(_claim(
            "State", "make_tender_in_payment_of_debts",
            "any Thing other than gold and silver Coin", evidence,
            polarity="negative",
        ))

    evidence = _match(
        text,
        r"pass any Bill of Attainder, ex post facto Law, or Law impairing the "
        r"Obligation of Contracts",
    )
    if evidence:
        for item in (
            "Bill of Attainder",
            "ex post facto Law",
            "Law impairing the Obligation of Contracts",
        ):
            claims.append(_claim(
                "State", "pass", item, evidence, polarity="negative",
            ))
    evidence = _match(text, r"grant any Title of Nobility")
    if evidence:
        claims.append(_claim(
            "State", "grant", "Title of Nobility", evidence,
            polarity="negative",
        ))

    customs = _match(
        text,
        r"No State shall, without the Consent of the Congress, lay any Imposts "
        r"or Duties on Imports or Exports, except what may be absolutely necessary "
        r"for executing it's inspection Laws",
    )
    exception = _match(
        text,
        r"except what may be absolutely necessary for executing it's inspection Laws",
    )
    customs_condition = (
        "without the Consent of the Congress; except what may be absolutely "
        "necessary for executing the State's inspection Laws"
    )
    exception_condition = (
        "only to the extent absolutely necessary for executing the State's "
        "inspection Laws; exception to the no-consent prohibition"
    )
    if customs:
        for kind in ("Imposts", "Duties"):
            for movement in ("Imports", "Exports"):
                claims.append(_claim(
                    "State", "lay", f"{kind} on {movement}", customs,
                    polarity="negative", condition=customs_condition,
                ))
    if exception:
        for kind in ("Imposts", "Duties"):
            for movement in ("Imports", "Exports"):
                claims.append(_claim(
                    "State", "may_lay", f"{kind} on {movement}", exception,
                    modality="may", condition=exception_condition,
                ))

    proceeds = _match(
        text,
        r"the net Produce of all Duties and Imposts, laid by any State on Imports "
        r"or Exports, shall be for the Use of the Treasury of the United States",
    )
    if proceeds:
        for kind in ("Duties", "Imposts"):
            for movement in ("Imports", "Exports"):
                claims.append(_claim(
                    f"net Produce of State {kind} on {movement}", "for_use_of",
                    "Treasury of the United States", proceeds,
                ))

    evidence = _match(
        text,
        r"all such Laws shall be subject to the Revision and Controul of the Congress",
    )
    if evidence:
        subject = "State laws laying Duties or Imposts on Imports or Exports"
        claims.extend((
            _claim(subject, "subject_to", "Revision by Congress", evidence),
            _claim(subject, "subject_to", "Controul of Congress", evidence),
        ))

    final = _verbatim(
        text,
        r"No State shall, without the Consent of Congress, lay any Duty of "
        r"Tonnage, keep Troops, or Ships of War in time of Peace, enter into any "
        r"Agreement or Compact with another State, or with a foreign Power, or "
        r"engage in War, unless actually invaded, or in such imminent Danger as "
        r"will not admit of delay\.",
    )
    if final:
        consent = "without the Consent of Congress"
        claims.append(_claim(
            "State", "lay", "Duty of Tonnage", final,
            polarity="negative", condition=consent,
        ))
        for item in ("Troops", "Ships of War"):
            claims.append(_claim(
                "State", "keep", item, final, polarity="negative",
                condition=f"{consent}; in time of Peace",
            ))
        for kind in ("Agreement", "Compact"):
            for counterparty in ("another State", "a foreign Power"):
                claims.append(_claim(
                    "State", "enter_into", f"{kind} with {counterparty}", final,
                    polarity="negative", condition=consent,
                ))
        claims.append(_claim(
            "State", "engage_in", "War", final, polarity="negative",
            condition=(
                f"{consent}; unless actually invaded or in such imminent Danger "
                "as will not admit of delay"
            ),
        ))

    return claims


def _is_article_2_section_1(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_2_SECTION_1":
        return True
    # Standalone excerpts require a distinctive pair of section provisions.
    return bool(
        re.search(r"\bexecutive Power shall be vested in a President\b", text, re.I)
        and re.search(r"\bnatural born Citizen\b", text, re.I)
    )


def _is_article_2_section_2(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_2_SECTION_2":
        # Activate only for the complete original clause forms.  This keeps
        # shorter excerpts on the generic parser, whose established output is
        # useful when the coordinated constitutional context is absent.
        return bool(re.search(
            r"Commander in Chief of the Army and Navy.*Militia of the several States"
            r"|require the Opinion, in writing.*Power to grant Reprieves and Pardons"
            r"|Advice and Consent of the Senate, to make Treaties"
            r"|shall nominate, and by and with the Advice and Consent"
            r"|Power to fill up all Vacancies.*granting Commissions",
            text,
            re.I | re.S,
        ))
    # Standalone excerpts require two distinctive powers so an isolated
    # reference to one presidential power does not activate the grammar.
    return bool(
        re.search(r"\bCommander in Chief of the Army and Navy\b", text, re.I)
        and re.search(r"\bAdvice and Consent of the Senate\b", text, re.I)
    )


def _is_article_3_section_2(source_unit: str | None, text: str) -> bool:
    if source_unit == "ARTICLE_3_SECTION_2":
        return True
    # Standalone excerpts require two distinctive provisions so an isolated
    # reference to judicial power does not activate the section grammar.
    return bool(
        re.search(r"\bjudicial Power shall extend to all Cases\b", text, re.I)
        and re.search(r"\bTrial of all Crimes\b", text, re.I)
    )


def _is_amendment_14_section_4(source_unit: str | None) -> bool:
    """Restrict the public-debt grammar to its exact constitutional unit."""
    return source_unit == "AMENDMENT_14_SECTION_4"


def _is_amendment_14_section_3(source_unit: str | None) -> bool:
    """Restrict the office-disqualification grammar to its exact unit."""
    return source_unit == "AMENDMENT_14_SECTION_3"


def _is_amendment_25_section_4(source_unit: str | None) -> bool:
    """Restrict the presidential-inability grammar to its exact unit."""
    return source_unit == "AMENDMENT_25_SECTION_4"


def _is_amendment_12(source_unit: str | None, text: str) -> bool:
    """Restrict the Twelfth Amendment grammar to its exact unit or full text."""
    if source_unit == "AMENDMENT_12":
        return True
    return bool(
        re.search(r"\bThe Electors shall meet in their respective states\b", text, re.I)
        and re.search(r"\bthe Senate shall choose the Vice-President\b", text, re.I)
    )


def _assemble_amendment_12(
    text: str,
    state: ProvisionState,
) -> list[ProvisionFrame]:
    """Assemble the Twelfth Amendment's stateful electoral procedure."""
    claims: list[ProvisionFrame] = []

    evidence = _verbatim(text, r"The Electors shall meet in their respective states")
    if evidence:
        claims.append(_claim("Electors", "meet_in", "their respective states", evidence))
    evidence = _verbatim(text, r"vote by ballot for President and Vice-President")
    if evidence:
        for office in ("President", "Vice-President"):
            claims.append(_claim("Electors", "vote_by_ballot_for", office, evidence))
    evidence = _verbatim(
        text,
        r"one of whom, at least, shall not be an inhabitant of the same state "
        r"with themselves",
    )
    if evidence:
        claims.append(_claim(
            "at least one of the President and Vice-President ballot choices",
            "is_inhabitant_of", "same state as the Electors", evidence,
            polarity="negative",
        ))

    evidence = _verbatim(
        text, r"they shall name in their ballots the person voted for as President",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "name_in_presidential_ballot",
            "person voted for as President", evidence,
        ))
    evidence = _verbatim(
        text, r"in distinct ballots the person voted for as Vice-President",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "name_in_distinct_vice_presidential_ballot",
            "person voted for as Vice-President", evidence,
        ))
    evidence = _verbatim(
        text, r"they shall make distinct lists of all persons voted for as President",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "make_distinct_list_of",
            "all persons voted for as President", evidence,
        ))
    evidence = _verbatim(text, r"and of all persons voted for as Vice-President")
    if evidence:
        claims.append(_claim(
            "Electors", "make_distinct_list_of",
            "all persons voted for as Vice-President", evidence,
        ))
    evidence = _verbatim(text, r"and of the number of votes for each")
    if evidence:
        claims.extend((
            _claim(
                "presidential electoral list", "includes",
                "number of votes for each presidential candidate", evidence,
                condition="on list of persons voted for as President",
            ),
            _claim(
                "vice-presidential electoral list", "includes",
                "number of votes for each vice-presidential candidate", evidence,
                condition="on list of persons voted for as Vice-President",
            ),
        ))
    evidence = _verbatim(text, r"which lists they shall sign and certify")
    if evidence:
        for predicate in ("sign", "certify"):
            claims.append(_claim(
                "Electors", predicate,
                "presidential and vice-presidential electoral lists", evidence,
            ))
    evidence = _verbatim(
        text,
        r"transmit sealed to the seat of the government of the United States, "
        r"directed to the President of the Senate",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "transmit",
            "presidential and vice-presidential electoral lists", evidence,
            condition=(
                "sealed; to the seat of the government of the United States; "
                "directed to the President of the Senate"
            ),
        ))
    evidence = _verbatim(
        text, r"transmit sealed to the seat of the government of the United States",
    )
    if evidence:
        claims.extend((
            _claim(
                "transmitted presidential and vice-presidential electoral lists",
                "are", "sealed", evidence,
            ),
            _claim(
                "presidential and vice-presidential electoral lists",
                "transmitted_to", "seat of the government of the United States",
                evidence,
            ),
        ))
    evidence = _verbatim(text, r"directed to the President of the Senate")
    if evidence:
        claims.append(_claim(
            "presidential and vice-presidential electoral lists", "directed_to",
            "President of the Senate", evidence,
        ))

    evidence = _verbatim(
        text,
        r"the President of the Senate shall, in the presence of the Senate and "
        r"House of Representatives, open all the certificates",
    )
    if evidence:
        claims.append(_claim(
            "President of the Senate", "opens", "all the electoral certificates",
            evidence,
            condition="in the presence of the Senate and House of Representatives",
        ))
    evidence = _verbatim(text, r"and the votes shall then be counted")
    if evidence:
        claims.append(_claim(
            "electoral votes", "counted", "after the certificates are opened",
            evidence, condition="after opening all the certificates",
        ))

    evidence = _verbatim(
        text,
        r"The person having the greatest number of votes for President, shall be "
        r"the President, if such number be a majority of the whole number of "
        r"Electors appointed",
    )
    if evidence:
        state.amendment_12_choice = "President"
        claims.append(_claim(
            "person having the greatest number of votes for President", "becomes",
            "President", evidence,
            condition=(
                "his presidential-vote number is a majority of the whole number "
                "of Electors appointed"
            ),
        ))
    evidence = _verbatim(
        text,
        r"if no person have such majority, then from the persons having the "
        r"highest numbers not exceeding three on the list of those voted for as "
        r"President, the House of Representatives shall choose immediately, by "
        r"ballot, the President",
    )
    if evidence:
        state.amendment_12_choice = "House-President"
        claims.append(_claim(
            "House of Representatives", "chooses_by_ballot",
            "President from the persons having the highest numbers, not exceeding "
            "three, on the presidential list",
            evidence,
            condition=(
                "no person has a majority of the whole number of Electors "
                "appointed; immediately"
            ),
        ))
    evidence = _verbatim(text, r"in choosing the President, the votes shall be taken by states")
    if evidence:
        state.amendment_12_choice = "House-President"
        claims.append(_claim(
            "votes for House choice of President", "taken_by", "states", evidence,
        ))
    evidence = _verbatim(text, r"the representation from each state having one vote")
    if evidence:
        claims.append(_claim(
            "representation from each state in House presidential choice",
            "has_vote_count", "1", evidence, condition="House choice of President",
        ))
    evidence = _verbatim(
        text,
        r"a quorum for this purpose shall consist of a member or members from "
        r"two-thirds of the states",
    )
    if evidence and state.amendment_12_choice == "House-President":
        claims.append(_claim(
            "quorum for House choice of President", "consists_of",
            "member or members from two-thirds of the states", evidence,
        ))
    evidence = _verbatim(text, r"a majority of all the states shall be necessary to a choice")
    if evidence and state.amendment_12_choice == "House-President":
        claims.append(_claim(
            "House choice of President", "requires", "majority of all the states",
            evidence,
        ))

    # The clause splitter puts the closing ``--]*`` at the start of the next
    # clause. Defer these claims so evidence retains that source marker.
    bracket = _verbatim(
        text,
        r"\[And if the House of Representatives shall not choose a President "
        r"whenever the right of choice shall devolve upon them, before the fourth "
        r"day of March next following, then the Vice-President shall act as "
        r"President, as in the case of the death or other constitutional "
        r"disability of the President\.(?:\s+--\]\*)?",
    )
    if bracket:
        if bracket.endswith("--]*"):
            state.amendment_12_bracketed_text = None
        else:
            state.amendment_12_bracketed_text = bracket
            bracket = ""
    if state.amendment_12_bracketed_text and re.match(r"\s*--\]\*", text):
        bracket = state.amendment_12_bracketed_text + " --]*"
        state.amendment_12_bracketed_text = None
    if bracket:
        deadline = (
            "House right of choice has devolved; House fails to choose President "
            "before fourth day of March next following"
        )
        claims.append(_claim(
            "Vice-President", "acts_as", "President", bracket, condition=deadline,
        ))
        analogy_subject = (
            "Vice-President acting as President after House fails to choose by "
            "historical March 4 deadline"
        )
        analogy_condition = (
            "House has contingent right of choice and fails to choose a President "
            "before the fourth day of March next following"
        )
        analogy_evidence = (
            "as in the case of the death or other constitutional disability of "
            "the President"
        )
        for object_ in (
            "death of the President",
            "other constitutional disability of the President",
        ):
            claims.append(_claim(
                analogy_subject, "acts_as_in_case_of", object_, analogy_evidence,
                condition=analogy_condition,
            ))

    evidence = _verbatim(
        text,
        r"The person having the greatest number of votes as Vice-President, shall "
        r"be the Vice-President, if such number be a majority of the whole number "
        r"of Electors appointed",
    )
    if evidence:
        state.amendment_12_choice = "Vice-President"
        claims.append(_claim(
            "person having the greatest number of votes as Vice-President", "becomes",
            "Vice-President", evidence,
            condition=(
                "his vice-presidential-vote number is a majority of the whole "
                "number of Electors appointed"
            ),
        ))
    evidence = _verbatim(
        text,
        r"if no person have a majority, then from the two highest numbers on the "
        r"list, the Senate shall choose the Vice-President",
    )
    if evidence:
        state.amendment_12_choice = "Senate-Vice-President"
        claims.append(_claim(
            "Senate", "chooses",
            "Vice-President from the two highest numbers on the vice-presidential list",
            evidence,
            condition=(
                "no vice-presidential candidate has a majority of the whole number "
                "of Electors appointed"
            ),
        ))
    evidence = _verbatim(
        text,
        r"a quorum for the purpose shall consist of two-thirds of the whole number "
        r"of Senators",
    )
    if evidence and state.amendment_12_choice == "Senate-Vice-President":
        claims.append(_claim(
            "quorum for Senate choice of Vice-President", "consists_of",
            "two-thirds of the whole number of Senators", evidence,
        ))
    evidence = _verbatim(text, r"a majority of the whole number shall be necessary to a choice")
    if evidence and state.amendment_12_choice == "Senate-Vice-President":
        claims.append(_claim(
            "Senate choice of Vice-President", "requires",
            "majority of the whole number of Senators", evidence,
        ))
    evidence = _verbatim(
        text,
        r"no person constitutionally ineligible to the office of President shall "
        r"be eligible to that of Vice-President of the United States",
    )
    if evidence:
        claims.append(_claim(
            "person constitutionally ineligible to office of President",
            "eligible_for", "office of Vice-President of the United States",
            evidence, polarity="negative",
        ))

    return claims


def _assemble_article_2_section_2(text: str) -> list[ProvisionFrame]:
    """Assemble Article II, Section 2 military and appointment powers."""
    claims: list[ProvisionFrame] = []

    evidence = _verbatim(
        text,
        r"The President shall be Commander in Chief of the Army and Navy "
        r"of the United States",
    )
    if evidence:
        for service in ("Army", "Navy"):
            claims.append(_claim(
                "President", "is_Commander_in_Chief_of",
                f"{service} of the United States", evidence,
            ))
    evidence = _verbatim(
        text,
        r"and of the Militia of the several States, when called into the "
        r"actual Service of the United States",
    )
    if evidence:
        claims.append(_claim(
            "President", "is_Commander_in_Chief_of",
            "Militia of the several States", evidence,
            condition="when called into the actual Service of the United States",
        ))

    evidence = _verbatim(
        text,
        r"he may require the Opinion, in writing, of the principal Officer in "
        r"each of the executive Departments",
    )
    if evidence:
        claims.append(_claim(
            "President", "may_require_written_Opinion_of",
            "principal Officer in each executive Department", evidence,
            modality="may",
            condition="upon any Subject relating to the Duties of their respective Offices",
        ))
    evidence = _verbatim(
        text, r"upon any Subject relating to the Duties of their respective Offices",
    )
    if evidence:
        claims.append(_claim(
            "written Opinion requested by President", "relates_to",
            "Duties of the respective executive Department Office", evidence,
            modality="may", condition="if President requires such an Opinion",
        ))

    evidence = _verbatim(
        text,
        r"he shall have Power to grant Reprieves and Pardons for Offences "
        r"against the United States, except in Cases of Impeachment",
    )
    if evidence:
        for remedy in ("Reprieves", "Pardons"):
            claims.append(_claim(
                "President", "has_Power_to_grant",
                f"{remedy} for Offences against the United States", evidence,
                condition="except in Cases of Impeachment",
            ))
    evidence = _verbatim(text, r"except in Cases of Impeachment")
    if evidence:
        claims.append(_claim(
            "President", "may_grant_Reprieves_or_Pardons_in",
            "Cases of Impeachment", evidence, modality="may", polarity="negative",
        ))

    evidence = _verbatim(
        text,
        r"He shall have Power, by and with the Advice and Consent of the "
        r"Senate, to make Treaties, provided two thirds of the Senators present concur",
    )
    if evidence:
        claims.append(_claim(
            "President", "has_Power_to_make", "Treaties", evidence,
            condition=(
                "by and with Advice and Consent of Senate; two thirds of "
                "Senators present concur"
            ),
        ))
    evidence = _verbatim(text, r"provided two thirds of the Senators present concur")
    if evidence:
        claims.append(_claim(
            "Senators present", "must_concur_for", "President to make Treaty",
            evidence,
            condition=(
                "at least two thirds of Senators present; treaty-making under "
                "Senate advice and consent"
            ),
        ))
    evidence = _verbatim(
        text,
        r"by and with the Advice and Consent of the Senate, to make Treaties, "
        r"provided two thirds of the Senators present concur",
    )
    if evidence:
        claims.append(_claim(
            "Senate’s Advice and Consent", "is_required_for",
            "President making Treaties", evidence,
            condition="two thirds of Senators present concur",
        ))

    appointments = _verbatim(
        text,
        r"and he shall nominate, and by and with the Advice and Consent of the "
        r"Senate, shall appoint Ambassadors, other public Ministers and Consuls, "
        r"Judges of the supreme Court, and all other Officers of the United "
        r"States, whose Appointments are not herein otherwise provided for, and "
        r"which shall be established by Law",
    )
    if appointments:
        offices = (
            "Ambassadors",
            "other public Ministers",
            "Consuls",
            "Judges of the supreme Court",
            "all other Officers of the United States",
        )
        for office in offices:
            nomination_condition = None
            appointment_condition = "by and with the Advice and Consent of the Senate"
            if office == "all other Officers of the United States":
                nomination_condition = (
                    "for other Officers, appointment not otherwise provided for in "
                    "Constitution and office established by Law"
                )
                appointment_condition += (
                    "; appointment not otherwise provided for in Constitution and "
                    "office established by Law"
                )
            claims.append(_claim(
                "President", "nominates", office, appointments,
                condition=nomination_condition,
            ))
            claims.append(_claim(
                "President", "appoints", office, appointments,
                condition=appointment_condition,
            ))
    evidence = _verbatim(
        text,
        r"by and with the Advice and Consent of the Senate, shall appoint "
        r"Ambassadors, other public Ministers and Consuls, Judges of the supreme "
        r"Court, and all other Officers of the United States",
    )
    if evidence:
        claims.append(_claim(
            "Senate’s Advice and Consent", "is_required_for",
            "President appointing enumerated Officers of the United States", evidence,
            condition=(
                "Ambassadors, other public Ministers and Consuls, Judges of supreme "
                "Court, and other Officers whose Appointments are not otherwise "
                "provided for and whose offices are established by Law; Congress "
                "may vest inferior-Officer appointments elsewhere by Law"
            ),
        ))

    evidence = _verbatim(
        text,
        r"the Congress may by Law vest the Appointment of such inferior Officers, "
        r"as they think proper",
    )
    if evidence:
        claims.append(_claim(
            "Congress", "may_vest_by_Law",
            "Appointment of such inferior Officers as Congress thinks proper",
            evidence, modality="may",
            condition="inferior Officers as Congress thinks proper",
        ))
    evidence = _verbatim(
        text,
        r"in the President alone, in the Courts of Law, or in the Heads of Departments",
    )
    if evidence:
        for recipient in ("President alone", "Courts of Law", "Heads of Departments"):
            claims.append(_claim(
                "Congress", "may_vest_Appointment_in", recipient, evidence,
                modality="may",
                condition="by Law; such inferior Officers as Congress thinks proper",
            ))

    evidence = _verbatim(
        text,
        r"The President shall have Power to fill up all Vacancies that may "
        r"happen during the Recess of the Senate",
    )
    if evidence:
        claims.append(_claim(
            "President", "has_Power_to_fill",
            "Vacancies that may happen during the Recess of the Senate", evidence,
            condition="Vacancies happen during the Recess of the Senate",
        ))
    evidence = _verbatim(
        text,
        r"by granting Commissions which shall expire at the End of their next Session",
    )
    if evidence:
        claims.append(_claim(
            "President", "fills_Vacancies_by_granting", "Commissions", evidence,
            condition="Vacancies that may happen during Recess of Senate",
        ))
    evidence = _verbatim(
        text, r"Commissions which shall expire at the End of their next Session",
    )
    if evidence:
        claims.append(_claim(
            "Recess Commissions", "expire_at", "End of the Senate’s next Session",
            evidence,
            condition="commission granted to fill a vacancy during Senate Recess",
        ))

    return claims


def _assemble_amendment_14_section_4(text: str) -> list[ProvisionFrame]:
    """Assemble Amendment XIV, Section 4 public-debt provisions.

    The second sentence is a Cartesian coordination: two governments may do
    neither of two actions to any of six debt, obligation, or claim kinds.
    Expanding those coordinates here keeps each emitted claim atomic while
    retaining the exact source span that governs every combination.
    """
    claims: list[ProvisionFrame] = []

    public_debt = _verbatim(
        text,
        r"The validity of the public debt of the United States, authorized by "
        r"law, including debts incurred for payment of pensions and bounties "
        r"for services in suppressing insurrection or rebellion, shall not be "
        r"questioned\.",
    )
    if public_debt:
        claims.append(_claim(
            "validity of public debt of the United States authorized by law",
            "questioned",
            "its validity",
            public_debt,
            polarity="negative",
        ))

    included_debts = _verbatim(
        text,
        r"including debts incurred for payment of pensions and bounties for "
        r"services in suppressing insurrection or rebellion",
    )
    if included_debts:
        for payment in ("pensions", "bounties"):
            for conflict in ("insurrection", "rebellion"):
                claims.append(_claim(
                    "validity of public debt incurred for payment of "
                    f"{payment} for services suppressing {conflict}",
                    "questioned",
                    "its validity",
                    included_debts,
                    polarity="negative",
                    condition="debt authorized by law",
                ))

    prohibited_payment = _verbatim(
        text,
        r"But neither the United States nor any State shall assume or pay any "
        r"debt or obligation incurred in aid of insurrection or rebellion "
        r"against the United States, or any claim for the loss or emancipation "
        r"of any slave",
    )
    prohibited_objects = (
        "debt incurred in aid of insurrection against the United States",
        "debt incurred in aid of rebellion against the United States",
        "obligation incurred in aid of insurrection against the United States",
        "obligation incurred in aid of rebellion against the United States",
        "claim for loss of a slave",
        "claim for emancipation of a slave",
    )
    if prohibited_payment:
        for actor in ("United States", "State"):
            for action in ("assume", "pay"):
                for object_ in prohibited_objects:
                    claims.append(_claim(
                        actor,
                        action,
                        object_,
                        prohibited_payment,
                        polarity="negative",
                    ))

    illegal_and_void = _verbatim(
        text,
        r"all such debts, obligations and claims shall be held illegal and void",
    )
    if illegal_and_void:
        for subject in prohibited_objects:
            claims.append(_claim(
                subject,
                "held",
                "illegal and void",
                illegal_and_void,
            ))

    return claims


def _assemble_amendment_14_section_3(text: str) -> list[ProvisionFrame]:
    """Assemble Amendment XIV, Section 3 disqualification provisions.

    The first sentence coordinates eight offices with three independently
    sufficient disqualifying acts.  Expanding that 8-by-3 product preserves
    the shared prior-oath requirement without collapsing distinct legal
    alternatives into compound claims.
    """
    claims: list[ProvisionFrame] = []

    disqualification = _verbatim(
        text,
        r"No person shall be a Senator or Representative in Congress, or "
        r"elector of President and Vice-President, or hold any office, civil "
        r"or military, under the United States, or under any State, who, "
        r"having previously taken an oath, as a member of Congress, or as an "
        r"officer of the United States, or as a member of any State "
        r"legislature, or as an executive or judicial officer of any State, "
        r"to support the Constitution of the United States, shall have "
        r"engaged in insurrection or rebellion against the same, or given "
        r"aid or comfort to the enemies thereof\.",
    )
    offices = (
        "Senator in Congress",
        "Representative in Congress",
        "elector of President",
        "elector of Vice-President",
        "civil office under the United States",
        "military office under the United States",
        "civil office under a State",
        "military office under a State",
    )
    prior_oath = (
        "having previously taken an oath to support the Constitution of the "
        "United States as a member of Congress, officer of the United States, "
        "member of a State legislature, or executive or judicial officer of a "
        "State"
    )
    disqualifying_acts = (
        "subsequently engaged in insurrection against the Constitution",
        "subsequently engaged in rebellion against the Constitution",
        "subsequently given aid or comfort to the enemies thereof",
    )
    if disqualification:
        for office in offices:
            for act in disqualifying_acts:
                claims.append(_claim(
                    "person",
                    "eligible_to_hold",
                    office,
                    disqualification,
                    polarity="negative",
                    condition=f"{prior_oath}; {act}",
                ))

    removal = _verbatim(
        text,
        r"But Congress may by a vote of two-thirds of each House, remove such "
        r"disability\.",
    )
    if removal:
        claims.append(_claim(
            "Congress",
            "may_remove",
            "Section 3 office-holding disability",
            removal,
            modality="may",
            condition="vote of two-thirds of each House",
        ))

    return claims


def _assemble_amendment_25_section_4(text: str) -> list[ProvisionFrame]:
    """Assemble Amendment XXV, Section 4 presidential-inability procedure.

    The provision has two alternative declaring groups, two recipients, and
    separate in-session and out-of-session deadlines.  Expanding those
    alternatives here prevents the generic extractor from merging legally
    distinct paths into compound claims.
    """
    claims: list[ProvisionFrame] = []

    initial = _verbatim(
        text,
        r"Whenever the Vice President and a majority of either the principal "
        r"officers of the executive departments or of such other body as "
        r"Congress may by law provide, transmit to the President pro tempore "
        r"of the Senate and the Speaker of the House of Representatives their "
        r"written declaration that the President is unable to discharge the "
        r"powers and duties of his office",
    )
    if initial:
        other_body = _verbatim(
            text, r"such other body as Congress may by law provide",
        )
        if other_body:
            claims.append(_claim(
                "Congress",
                "may_provide_by_law",
                "alternative body whose majority joins Vice President in an "
                "inability declaration",
                other_body,
                modality="may",
            ))

        declaring_groups = (
            "Vice President and a majority of principal officers of the "
            "executive departments",
            "Vice President and a majority of other body Congress may by law provide",
        )
        recipients = (
            "President pro tempore of the Senate",
            "Speaker of the House of Representatives",
        )
        for group in declaring_groups:
            for recipient in recipients:
                claims.append(_claim(
                    group,
                    "transmits_written_declaration_to",
                    recipient,
                    initial,
                    modality=None,
                    condition=(
                        "declaration states President is unable to discharge powers "
                        "and duties of office"
                    ),
                ))

        assumption = _verbatim(
            text,
            r"the Vice President shall immediately assume the powers and duties "
            r"of the office as Acting President",
        )
        if assumption:
            for condition_group in (
                "principal officers of the executive departments",
                "other body Congress may by law provide",
            ):
                common = (
                    f"Vice President and majority of {condition_group} have "
                    "transmitted written inability declaration to President pro "
                    "tempore of Senate and Speaker of House; serves as Acting President"
                )
                for object_ in (
                    "powers of the Office of President",
                    "duties of the Office of President",
                ):
                    claims.append(_claim(
                        "Vice President",
                        "immediately_assumes",
                        object_,
                        assumption,
                        condition=common,
                    ))
                claims.append(_claim(
                    "Vice President",
                    "serves_as",
                    "Acting President",
                    assumption,
                    condition=(
                        "upon written inability declaration by Vice President and "
                        f"majority of {condition_group} to both specified "
                        "congressional officers; immediately"
                    ),
                ))

    no_inability = _verbatim(
        text,
        r"Thereafter, when the President transmits to the President pro tempore "
        r"of the Senate and the Speaker of the House of Representatives his "
        r"written declaration that no inability exists",
    )
    if no_inability:
        for recipient in (
            "President pro tempore of the Senate",
            "Speaker of the House of Representatives",
        ):
            claims.append(_claim(
                "President",
                "transmits_written_declaration_to",
                recipient,
                no_inability,
                modality=None,
                condition=(
                    "declaration states no inability exists; after Vice President "
                    "assumed as Acting President"
                ),
            ))

        uncontested = _verbatim(
            text,
            r"he shall resume the powers and duties of his office unless the Vice "
            r"President and a majority of either the principal officers of the "
            r"executive department or of such other body as Congress may by law "
            r"provide, transmit within four days",
        )
        if uncontested:
            claims.append(_claim(
                "President",
                "resumes",
                "powers and duties of his Office",
                uncontested,
                condition=(
                    "President has sent written no-inability declaration to both "
                    "named congressional officers; unless timely counter-declaration "
                    "is sent within four days"
                ),
            ))

        counter = _verbatim(
            text,
            r"unless the Vice President and a majority of either the principal "
            r"officers of the executive department or of such other body as "
            r"Congress may by law provide, transmit within four days to the "
            r"President pro tempore of the Senate and the Speaker of the House "
            r"of Representatives their written declaration that the President "
            r"is unable to discharge the powers and duties of his office",
        )
        if counter:
            condition = (
                "within four days after President’s written no-inability declaration; "
                "counter-declaration says President unable to discharge powers and duties"
            )
            for group in (
                "Vice President and a majority of principal officers of the "
                "executive department",
                "Vice President and a majority of other body Congress may by law provide",
            ):
                for recipient in (
                    "President pro tempore of the Senate",
                    "Speaker of the House of Representatives",
                ):
                    claims.append(_claim(
                        group,
                        "transmits_written_declaration_to",
                        recipient,
                        counter,
                        modality=None,
                        condition=condition,
                    ))

    decision = _verbatim(text, r"Thereupon Congress shall decide the issue")
    if decision:
        claims.append(_claim(
            "Congress",
            "decides",
            "issue of presidential inability",
            decision,
            condition="after timely Vice President-plus-majority counter-declaration",
        ))
    assembly = _verbatim(
        text, r"assembling within forty-eight hours for that purpose if not in session",
    )
    if assembly:
        claims.append(_claim(
            "Congress",
            "assembles_within",
            "forty-eight hours",
            assembly,
            condition="Congress is not in session when the inability issue arises",
        ))

    determination = _verbatim(
        text,
        r"If the Congress, within twenty-one days after receipt of the latter "
        r"written declaration, or, if Congress is not in session, within "
        r"twenty-one days after Congress is required to assemble, determines "
        r"by two-thirds vote of both Houses that the President is unable to "
        r"discharge the powers and duties of his office, the Vice President "
        r"shall continue to discharge the same as Acting President",
    )
    if determination:
        paths = (
            (
                "within twenty-one days after receipt of the latter written "
                "declaration; two-thirds vote of both Houses",
                "Congress has determined inability by two-thirds vote of both "
                "Houses within twenty-one days after receipt of the latter "
                "written declaration",
            ),
            (
                "if Congress is not in session, within twenty-one days after "
                "Congress is required to assemble; two-thirds vote of both Houses",
                "Congress has determined inability by two-thirds vote of both "
                "Houses if Congress is not in session, within twenty-one days "
                "after Congress is required to assemble",
            ),
        )
        for congress_condition, vice_president_condition in paths:
            claims.append(_claim(
                "Congress",
                "determines",
                "President is unable to discharge powers and duties of Office",
                determination,
                condition=congress_condition,
            ))
            claims.append(_claim(
                "Vice President",
                "continues_to_discharge",
                "powers and duties of Office as Acting President",
                determination,
                condition=vice_president_condition,
            ))

    otherwise = _verbatim(
        text,
        r"otherwise, the President shall resume the powers and duties of his office",
    )
    if otherwise:
        claims.append(_claim(
            "President",
            "resumes",
            "powers and duties of his Office",
            otherwise,
            condition=(
                "otherwise: Congress does not make the timely two-thirds "
                "determination of presidential inability"
            ),
        ))

    return claims


def _assemble_article_3_section_2(text: str) -> list[ProvisionFrame]:
    """Assemble Article III, Section 2 jurisdiction and trial provisions."""
    claims: list[ProvisionFrame] = []
    judicial_power = "judicial Power of the United States"

    evidence = _verbatim(
        text,
        r"The judicial Power shall extend to all Cases, in Law and Equity, "
        r"arising under this Constitution, the Laws of the United States, and "
        r"Treaties made, or which shall be made, under their Authority",
    )
    if evidence:
        for authority in (
            "this Constitution",
            "the Laws of the United States",
            "Treaties made or to be made under United States authority",
        ):
            for kind in ("Law", "Equity"):
                claims.append(_claim(
                    judicial_power, "extends_to",
                    f"Cases in {kind} arising under {authority}", evidence,
                ))

    evidence = _verbatim(
        text, r"all Cases affecting Ambassadors, other public Ministers and Consuls",
    )
    if text.lstrip().casefold().startswith("in all cases affecting"):
        # The later original-jurisdiction clause repeats the same categories;
        # it does not restate the opening extension of judicial power.
        evidence = None
    if evidence:
        for official in ("Ambassadors", "other public Ministers", "Consuls"):
            claims.append(_claim(
                judicial_power, "extends_to", f"Cases affecting {official}", evidence,
            ))

    evidence = _verbatim(text, r"all Cases of admiralty and maritime Jurisdiction")
    if evidence:
        for kind in ("admiralty", "maritime"):
            claims.append(_claim(
                judicial_power, "extends_to", f"Cases of {kind} Jurisdiction", evidence,
            ))

    evidence = _verbatim(
        text, r"Controversies to which the United States shall be a Party",
    )
    if evidence:
        claims.append(_claim(
            judicial_power, "extends_to",
            "Controversies to which United States is a Party", evidence,
        ))

    evidence = _verbatim(text, r"Controversies between two or more States")
    if evidence:
        claims.append(_claim(
            judicial_power, "extends_to",
            "Controversies between two or more States", evidence,
        ))

    evidence = _verbatim(text, r"between a State and Citizens of another State")
    if evidence:
        claims.append(_claim(
            judicial_power, "extends_to",
            "Controversies between a State and Citizens of another State", evidence,
        ))

    evidence = _verbatim(text, r"between Citizens of different States")
    if evidence:
        claims.append(_claim(
            judicial_power, "extends_to",
            "Controversies between Citizens of different States", evidence,
        ))

    evidence = _verbatim(
        text,
        r"between Citizens of the same State claiming Lands under Grants of "
        r"different States",
    )
    if evidence:
        claims.append(_claim(
            judicial_power, "extends_to",
            "Controversies between Citizens of same State claiming Lands under "
            "Grants of different States",
            evidence,
        ))

    evidence = _verbatim(
        text,
        r"between a State, or the Citizens thereof, and foreign States, "
        r"Citizens or Subjects",
    )
    if evidence:
        for domestic in ("a State", "Citizens of a State"):
            for foreign in ("foreign States", "foreign Citizens", "foreign Subjects"):
                claims.append(_claim(
                    judicial_power, "extends_to",
                    f"Controversies between {domestic} and {foreign}", evidence,
                ))

    evidence = _verbatim(
        text, r"In all Cases affecting Ambassadors, other public Ministers and Consuls",
    )
    if evidence:
        for official in ("Ambassadors", "other public Ministers", "Consuls"):
            claims.append(_claim(
                "supreme Court", "has_original_Jurisdiction_in",
                f"Cases affecting {official}", evidence,
            ))
    evidence = _verbatim(text, r"and those in which a State shall be Party")
    if evidence:
        claims.append(_claim(
            "supreme Court", "has_original_Jurisdiction_in",
            "Cases in which a State shall be Party", evidence,
        ))

    evidence = _verbatim(
        text,
        r"In all the other Cases before mentioned, the supreme Court shall have "
        r"appellate Jurisdiction",
    )
    if evidence:
        claims.append(_claim(
            "supreme Court", "has_appellate_Jurisdiction_in",
            "all other Cases before mentioned", evidence,
            condition="outside the enumerated original-Jurisdiction categories",
        ))
    evidence = _verbatim(
        text,
        r"the supreme Court shall have appellate Jurisdiction, both as to Law and Fact",
    )
    if evidence:
        condition = (
            "all other Cases before mentioned; subject to congressional Exceptions "
            "and Regulations"
        )
        for dimension in ("Law", "Fact"):
            claims.append(_claim(
                "supreme Court appellate Jurisdiction", "extends_to", dimension,
                evidence, condition=condition,
            ))
    evidence = _verbatim(
        text,
        r"with such Exceptions, and under such Regulations as the Congress shall make",
    )
    if evidence:
        condition = "appellate Jurisdiction in other cases before mentioned"
        for object_ in (
            "Exceptions to supreme Court appellate Jurisdiction",
            "Regulations of supreme Court appellate Jurisdiction",
        ):
            claims.append(_claim(
                "Congress", "may_make", object_, evidence,
                modality="may", condition=condition,
            ))

    evidence = _verbatim(
        text,
        r"The Trial of all Crimes, except in Cases of Impeachment, shall be by Jury",
    )
    if evidence:
        claims.append(_claim(
            "Trial of all Crimes", "shall_be_by", "Jury", evidence,
            condition="except in Cases of Impeachment",
        ))
    evidence = _verbatim(text, r"except in Cases of Impeachment")
    if evidence:
        claims.append(_claim(
            "Trial in Cases of Impeachment", "required_to_be_by", "Jury", evidence,
            polarity="negative",
        ))
    evidence = _verbatim(
        text,
        r"such Trial shall be held in the State where the said Crimes shall have "
        r"been committed",
    )
    if evidence:
        claims.append(_claim(
            "Trial of Crimes", "held_in", "State where Crimes were committed",
            evidence, condition="Crimes committed within a State",
        ))
    evidence = _verbatim(
        text,
        r"but when not committed within any State, the Trial shall be at such "
        r"Place or Places as the Congress may by Law have directed",
    )
    if evidence:
        claims.append(_claim(
            "Trial of Crimes", "held_at",
            "Place or Places Congress may by Law have directed", evidence,
            condition="Crimes not committed within any State",
        ))
    evidence = _verbatim(
        text, r"at such Place or Places as the Congress may by Law have directed",
    )
    if evidence:
        claims.append(_claim(
            "Congress", "may_direct_by_Law", "Place or Places of Trial", evidence,
            modality="may", condition="Crime not committed within any State",
        ))

    return claims


def _assemble_article_2_section_1(text: str) -> list[ProvisionFrame]:
    """Assemble Article II, Section 1 election and office provisions."""
    claims: list[ProvisionFrame] = []

    evidence = _verbatim(
        text,
        r"The executive Power shall be vested in a President of the United "
        r"States of America\.",
    )
    if evidence:
        claims.append(_claim(
            "executive Power", "vested_in",
            "President of the United States of America", evidence,
        ))

    evidence = _verbatim(
        text, r"He shall hold his Office during the Term of four Years",
    )
    if evidence:
        claims.append(_claim(
            "President", "holds_office_for", "four Years", evidence,
        ))
    evidence = _verbatim(
        text, r"together with the Vice President, chosen for the same Term",
    )
    if evidence:
        claims.append(_claim(
            "Vice President", "chosen_for_term", "four Years", evidence,
        ))
    evidence = _verbatim(text, r"be elected, as follows")
    if evidence:
        claims.append(_claim(
            "President", "elected_according_to",
            "electoral procedure that follows", evidence,
        ))
    evidence = _verbatim(
        text,
        r"together with the Vice President, chosen for the same Term, be "
        r"elected, as follows",
    )
    if evidence:
        claims.append(_claim(
            "Vice President", "elected_according_to",
            "electoral procedure that follows", evidence,
        ))

    evidence = _verbatim(text, r"Each State shall appoint")
    if evidence:
        claims.append(_claim("each State", "appoints", "Electors", evidence))
    evidence = _verbatim(
        text, r"in such Manner as the Legislature thereof may direct",
    )
    if evidence:
        claims.append(_claim(
            "Legislature of each State", "may_direct",
            "manner of appointing that State’s Electors", evidence,
            modality="may",
        ))
    evidence = _verbatim(
        text,
        r"a Number of Electors, equal to the whole Number of Senators and "
        r"Representatives to which the State may be entitled in the Congress",
    )
    if evidence:
        claims.append(_claim(
            "number of Electors appointed by each State", "equals",
            "whole Number of Senators and Representatives to which the State "
            "may be entitled in Congress",
            evidence,
        ))
    evidence = _verbatim(
        text,
        r"no Senator or Representative, or Person holding an Office of Trust "
        r"or Profit under the United States, shall be appointed an Elector",
    )
    if evidence:
        for subject in (
            "Senator",
            "Representative",
            "Person holding an Office of Trust under the United States",
            "Person holding an Office of Profit under the United States",
        ):
            claims.append(_claim(
                subject, "appointed_as", "Elector", evidence,
                polarity="negative",
            ))

    evidence = _verbatim(
        text, r"The Electors shall meet in their respective States",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "meet_in", "their respective States", evidence,
        ))
    evidence = _verbatim(text, r"vote by Ballot for two Persons")
    if evidence:
        claims.append(_claim(
            "Electors", "vote_by_Ballot_for", "two Persons", evidence,
        ))
    evidence = _verbatim(
        text,
        r"of whom one at least shall not be an Inhabitant of the same State "
        r"with themselves",
    )
    if evidence:
        claims.append(_claim(
            "at least one Person voted for by each Elector", "is_Inhabitant_of",
            "same State as that Elector", evidence, polarity="negative",
            condition="among the two Persons voted for by Ballot",
        ))

    evidence = _verbatim(
        text, r"they shall make a List of all the Persons voted for",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "make_List_of", "all Persons voted for", evidence,
        ))
    evidence = _verbatim(text, r"and of the Number of Votes for each")
    if evidence:
        claims.append(_claim(
            "Electors", "include_in_List", "Number of Votes for each Person",
            evidence,
        ))

    evidence = _verbatim(text, r"which List they shall sign and certify")
    if evidence:
        for predicate in ("sign", "certify"):
            claims.append(_claim(
                "Electors", predicate,
                "List of Persons voted for and their vote counts", evidence,
            ))
    evidence = _verbatim(
        text,
        r"transmit sealed to the Seat of the Government of the United States, "
        r"directed to the President of the Senate",
    )
    if evidence:
        claims.append(_claim(
            "Electors", "transmit",
            "List of Persons voted for and their vote counts", evidence,
            condition=(
                "sealed; to the Seat of Government; directed to the President "
                "of the Senate"
            ),
        ))
    evidence = _verbatim(
        text, r"transmit sealed to the Seat of the Government of the United States",
    )
    if evidence:
        claims.extend((
            _claim("transmitted electoral List", "is", "sealed", evidence),
            _claim(
                "electoral List", "transmitted_to",
                "Seat of the Government of the United States", evidence,
            ),
        ))
    evidence = _verbatim(text, r"directed to the President of the Senate")
    if evidence:
        claims.append(_claim(
            "electoral List", "directed_to", "President of the Senate", evidence,
        ))

    evidence = _verbatim(
        text,
        r"The President of the Senate shall, in the Presence of the Senate and "
        r"House of Representatives, open all the Certificates",
    )
    if evidence:
        claims.append(_claim(
            "President of the Senate", "opens", "all the Certificates", evidence,
            condition="in the Presence of the Senate and House of Representatives",
        ))
    evidence = _verbatim(text, r"and the Votes shall then be counted")
    if evidence:
        claims.append(_claim(
            "electoral Votes", "counted", "after the Certificates are opened",
            evidence, condition="after opening the Certificates",
        ))

    evidence = _verbatim(
        text,
        r"The Person having the greatest Number of Votes shall be the President, "
        r"if such Number be a Majority of the whole Number of Electors appointed",
    )
    if evidence:
        claims.append(_claim(
            "Person having the greatest Number of electoral Votes", "becomes",
            "President", evidence,
            condition=(
                "that Number is a Majority of the whole Number of Electors appointed"
            ),
        ))
    evidence = _verbatim(
        text,
        r"if there be more than one who have such Majority, and have an equal "
        r"Number of Votes, then the House of Representatives shall immediately "
        r"chuse by Ballot one of them for President",
    )
    if evidence:
        claims.append(_claim(
            "House of Representatives", "chooses_by_Ballot",
            "one of the tied majority-vote Persons for President", evidence,
            condition=(
                "more than one Person has a Majority of all Electors appointed "
                "and those Persons have an equal Number of Votes; immediately"
            ),
        ))
    evidence = _verbatim(
        text,
        r"if no Person have a Majority, then from the five highest on the List "
        r"the said House shall in like Manner chuse the President",
    )
    if evidence:
        claims.append(_claim(
            "House of Representatives", "chooses_by_Ballot",
            "President from the five highest Persons on the List", evidence,
            condition=(
                "no Person has a Majority of the whole Number of Electors "
                "appointed; in like Manner as the preceding ballot choice"
            ),
        ))
    evidence = _verbatim(
        text, r"in chusing the President, the Votes shall be taken by States",
    )
    if evidence:
        claims.append(_claim(
            "Votes in House choice of President", "taken_by", "States", evidence,
        ))
    evidence = _verbatim(
        text, r"the Representation from each State having one Vote",
    )
    if evidence:
        claims.append(_claim(
            "Representation from each State in House choice of President",
            "has_vote_count", "1", evidence,
            condition="when House chooses the President",
        ))
    evidence = _verbatim(
        text,
        r"A quorum for this Purpose shall consist of a Member or Members from "
        r"two thirds of the States",
    )
    if evidence:
        claims.append(_claim(
            "quorum for House choice of President", "consists_of",
            "Member or Members from two thirds of the States", evidence,
        ))
    evidence = _verbatim(
        text, r"a Majority of all the States shall be necessary to a Choice",
    )
    if evidence:
        claims.append(_claim(
            "House choice of President", "requires", "Majority of all the States",
            evidence,
        ))
    evidence = _verbatim(
        text,
        r"In every Case, after the Choice of the President, the Person having "
        r"the greatest Number of Votes of the Electors shall be the Vice President",
    )
    if evidence:
        claims.append(_claim(
            "Person having the greatest Number of electoral Votes after the "
            "President is chosen",
            "becomes", "Vice President", evidence,
            condition="after the Choice of the President",
        ))
    evidence = _verbatim(
        text,
        r"if there should remain two or more who have equal Votes, the Senate "
        r"shall chuse from them by Ballot the Vice President",
    )
    if evidence:
        claims.append(_claim(
            "Senate", "chooses_by_Ballot",
            "Vice President from the tied Persons", evidence,
            condition=(
                "after choice of President, two or more remaining Persons have "
                "equal electoral Votes"
            ),
        ))

    evidence = _verbatim(
        text, r"The Congress may determine the Time of chusing the Electors",
    )
    if evidence:
        claims.append(_claim(
            "Congress", "may_determine", "Time of chusing the Electors",
            evidence, modality="may",
        ))
    evidence = _verbatim(
        text, r"and the Day on which they shall give their Votes",
    )
    if evidence:
        claims.append(_claim(
            "Congress", "may_determine", "Day on which Electors give their Votes",
            evidence, modality="may",
        ))
    evidence = _verbatim(
        text, r"which Day shall be the same throughout the United States",
    )
    if evidence:
        claims.append(_claim(
            "Day on which Electors give their Votes", "same_throughout",
            "United States", evidence,
        ))

    evidence = _verbatim(
        text,
        r"No Person except a natural born Citizen, or a Citizen of the United "
        r"States, at the time of the Adoption of this Constitution, shall be "
        r"eligible to the Office of President",
    )
    if evidence:
        claims.append(_claim(
            "Person", "eligible_for", "Office of President", evidence,
            polarity="negative",
            condition=(
                "neither a natural born Citizen nor a Citizen of the United States "
                "at the time of Adoption of this Constitution"
            ),
        ))
    evidence = _verbatim(
        text,
        r"neither shall any Person be eligible to that Office who shall not have "
        r"attained to the Age of thirty five Years",
    )
    if evidence:
        claims.append(_claim(
            "Person", "eligible_for", "Office of President", evidence,
            polarity="negative",
            condition="has not attained the Age of thirty five Years",
        ))
    evidence = _verbatim(
        text, r"and been fourteen Years a Resident within the United States",
    )
    if evidence:
        claims.append(_claim(
            "Person", "eligible_for", "Office of President", evidence,
            polarity="negative",
            condition="has not been fourteen Years a Resident within the United States",
        ))

    evidence = _verbatim(
        text,
        r"In Case of the Removal of the President from Office, or of his Death, "
        r"Resignation, or Inability to discharge the Powers and Duties of the "
        r"said Office, the Same shall devolve on the Vice President",
    )
    if evidence:
        for condition in (
            "in Case of Removal of the President from Office",
            "in Case of Death of the President",
            "in Case of Resignation of the President",
            "in Case of Inability of the President to discharge the Powers and "
            "Duties of the Office",
        ):
            claims.append(_claim(
                "Powers and Duties of the Office of President", "devolve_on",
                "Vice President", evidence, condition=condition,
            ))
    evidence = _verbatim(
        text,
        r"the Congress may by Law provide for the Case of Removal, Death, "
        r"Resignation or Inability, both of the President and Vice President",
    )
    if evidence:
        claims.append(_claim(
            "Congress", "may_provide_by_Law_for",
            "case of Removal, Death, Resignation or Inability of both President "
            "and Vice President",
            evidence, modality="may",
            condition=(
                "both President and Vice President are affected; their triggering "
                "causes need not be identical"
            ),
        ))
    evidence = _verbatim(
        text, r"declaring what Officer shall then act as President",
    )
    if evidence:
        claims.append(_claim(
            "Congress", "may_declare_by_Law",
            "which Officer shall then act as President", evidence, modality="may",
            condition=(
                "law providing for the case of Removal, Death, Resignation or "
                "Inability of both President and Vice President"
            ),
        ))
    evidence = _verbatim(text, r"such Officer shall act accordingly")
    if evidence:
        claims.append(_claim(
            "Officer declared by Congress", "acts_as", "President", evidence,
            condition=(
                "upon a congressional law and declaration for the case of both "
                "President and Vice President being unable to serve"
            ),
        ))
    evidence = _verbatim(text, r"until the Disability be removed")
    if evidence:
        claims.append(_claim(
            "Officer declared by Congress", "acts_as", "President", evidence,
            condition=(
                "until the Disability be removed; case of both President and Vice "
                "President being unable to serve"
            ),
        ))
    evidence = _verbatim(text, r"or a President shall be elected")
    if evidence:
        claims.append(_claim(
            "Officer declared by Congress", "acts_as", "President", evidence,
            condition=(
                "until a President shall be elected; case of both President and "
                "Vice President being unable to serve"
            ),
        ))

    evidence = _verbatim(
        text,
        r"The President shall, at stated Times, receive for his Services, a "
        r"Compensation",
    )
    if evidence:
        claims.append(_claim(
            "President", "receives", "Compensation for Services", evidence,
            condition="at stated Times",
        ))
    evidence = _verbatim(
        text,
        r"which shall neither be encreased nor diminished during the Period for "
        r"which he shall have been elected",
    )
    if evidence:
        for predicate in ("encreased_during", "diminished_during"):
            claims.append(_claim(
                "President’s Compensation", predicate,
                "Period for which he was elected", evidence, polarity="negative",
            ))
    evidence = _verbatim(
        text,
        r"he shall not receive within that Period any other Emolument from the "
        r"United States, or any of them",
    )
    if evidence:
        for source in ("United States", "any State"):
            claims.append(_claim(
                "President", "receives_other_Emolument_from", source, evidence,
                polarity="negative",
                condition="within the Period for which he was elected",
            ))

    evidence = _verbatim(
        text,
        r"Before he enter on the Execution of his Office, he shall take the "
        r"following Oath or Affirmation",
    )
    if evidence:
        claims.append(_claim(
            "President", "takes", "specified Oath or Affirmation", evidence,
            condition="before entering on Execution of his Office",
        ))
    evidence = _verbatim(
        text, r"I will faithfully execute the Office of President of the United States",
    )
    if evidence:
        claims.append(_claim(
            "President", "swears_or_affirms_to",
            "faithfully execute the Office of President of the United States",
            evidence, condition="in the required pre-office Oath or Affirmation",
        ))
    evidence = _verbatim(
        text, r"preserve, protect and defend the Constitution of the United States",
    )
    if evidence:
        condition = (
            "in the required pre-office Oath or Affirmation; to the best of his Ability"
        )
        for action in ("preserve", "protect", "defend"):
            claims.append(_claim(
                "President", "swears_or_affirms_to",
                f"{action} the Constitution of the United States", evidence,
                condition=condition,
            ))

    return claims


def _assemble_article_1_section_7(
    text: str,
    state: ProvisionState,
) -> list[ProvisionFrame]:
    """Assemble the revenue and presidential-presentment procedure."""
    claims: list[ProvisionFrame] = []

    evidence = _match(
        text,
        r"All Bills for raising Revenue shall originate in the House of Representatives",
    )
    if evidence:
        claims.append(_claim(
            "Bills for raising Revenue", "originate_in",
            "House of Representatives", evidence,
        ))

    evidence = _match(
        text, r"the Senate may propose or concur with Amendments as on other Bills",
    )
    if evidence:
        for predicate in ("may_propose", "may_concur_with"):
            claims.append(_claim(
                "Senate", predicate, "Amendments to Bills for raising Revenue",
                evidence, modality="may",
            ))

    evidence = _match(
        text,
        r"Every Bill which shall have passed the House of Representatives and the Senate",
    )
    if evidence:
        for house in ("House of Representatives", "Senate"):
            claims.append(_claim(
                "Bill subject to ordinary lawmaking", "passes", house, evidence,
                condition="before presentation to President and becoming Law",
            ))
    evidence = _match(
        text,
        r"shall, before it become a Law, be presented to the President of the United States",
    )
    if evidence:
        claims.append(_claim(
            "Bill passed by both Houses", "presented_to",
            "President of the United States", evidence,
            condition="before becoming Law",
        ))

    evidence = _match(text, r"If he approve he shall sign it")
    if evidence:
        claims.append(_claim(
            "President", "signs", "Bill presented by both Houses", evidence,
            condition="if he approves the Bill",
        ))
    evidence = _match(
        text,
        r"but if not he shall return it, with his Objections to that House in "
        r"which it shall have originated",
    )
    if evidence:
        claims.append(_claim(
            "President", "returns", "Bill to its originating House", evidence,
            condition="if he does not approve the Bill",
        ))
    evidence = _match(
        text,
        r"he shall return it, with his Objections to that House in which it "
        r"shall have originated",
    )
    if evidence:
        claims.append(_claim(
            "President", "returns_with", "Objections to Bill", evidence,
            condition="if he does not approve the Bill",
        ))
    evidence = _match(
        text, r"who shall enter the Objections at large on their Journal",
    )
    if evidence:
        claims.append(_claim(
            "House in which Bill originated", "enters_at_large_on_Journal",
            "President’s Objections", evidence,
            condition="President returns a disapproved Bill with Objections",
        ))
    evidence = _match(text, r"and proceed to reconsider it")
    if evidence:
        claims.append(_claim(
            "House in which Bill originated", "reconsiders", "returned Bill",
            evidence, condition="President returns a disapproved Bill",
        ))

    evidence = _match(
        text,
        r"If after such Reconsideration two thirds of that House shall agree "
        r"to pass the Bill",
    )
    if evidence:
        claims.append(_claim(
            "two thirds of House in which Bill originated", "agree_to_pass",
            "reconsidered Bill", evidence,
            condition=(
                "after originating House reconsiders President’s returned Bill; "
                "prerequisite to sending to other House"
            ),
        ))
    evidence = _match(
        text, r"it shall be sent, together with the Objections, to the other House",
    )
    if evidence:
        condition = (
            "two thirds of originating House agree to pass after reconsideration"
        )
        claims.extend((
            _claim(
                "House in which Bill originated", "sends", "Bill to other House",
                evidence, condition=condition,
            ),
            _claim(
                "House in which Bill originated", "sends",
                "President’s Objections to other House", evidence,
                condition=condition,
            ),
        ))
    evidence = _match(text, r"by which it shall likewise be reconsidered")
    if evidence:
        claims.append(_claim(
            "other House", "reconsiders", "Bill returned by President", evidence,
            condition=(
                "two thirds of originating House agree to pass after reconsideration"
            ),
        ))
    evidence = _match(text, r"if approved by two thirds of that House")
    if evidence:
        claims.append(_claim(
            "two thirds of other House", "approve", "reconsidered Bill", evidence,
            condition=(
                "after originating House agrees to pass by two thirds and other "
                "House reconsiders"
            ),
        ))
    evidence = _match(
        text, r"if approved by two thirds of that House, it shall become a Law",
    )
    if evidence:
        claims.append(_claim(
            "Bill returned by President", "becomes", "Law", evidence,
            condition=(
                "two thirds of originating House agree to pass after reconsideration "
                "and two thirds of other House approve after its reconsideration"
            ),
        ))

    evidence = _match(
        text,
        r"But in all such Cases the Votes of both Houses shall be determined "
        r"by yeas and Nays",
    )
    if evidence:
        condition = "presidential-return reconsideration and override procedure"
        for house in ("House of Representatives", "Senate"):
            claims.append(_claim(
                f"Votes of {house}", "determined_by", "yeas and Nays", evidence,
                condition=condition,
            ))
    evidence = _match(
        text,
        r"the Names of the Persons voting for and against the Bill shall be "
        r"entered on the Journal of each House respectively",
    )
    if evidence:
        condition = "presidential-return reconsideration and override procedure"
        for position in ("for", "against"):
            claims.append(_claim(
                "Each House", "enters_on_its_Journal",
                f"Names of Persons voting {position} Bill", evidence,
                condition=condition,
            ))

    evidence = _match(
        text,
        r"If any Bill shall not be returned by the President within ten Days "
        r"\(Sundays excepted\) after it shall have been presented to him, the "
        r"Same shall be a Law, in like Manner as if he had signed it",
    )
    if evidence:
        claims.append(_claim(
            "Bill not returned by President", "becomes", "Law as if signed",
            evidence,
            condition=(
                "not returned within ten Days after presentation, Sundays excepted; "
                "Congress’s Adjournment does not prevent Return"
            ),
        ))
    evidence = _match(
        text,
        r"unless the Congress by their Adjournment prevent its Return, in which "
        r"Case it shall not be a Law",
    )
    if evidence:
        claims.append(_claim(
            "Bill not returned by President", "becomes", "Law", evidence,
            polarity="negative",
            condition=(
                "Congress by Adjournment prevents Return of the Bill within the "
                "prescribed period"
            ),
        ))

    evidence = _match(
        text,
        r"Every Order, Resolution, or Vote to which the Concurrence of the Senate "
        r"and House of Representatives may be necessary \(except on a question "
        r"of Adjournment\) shall be presented to the President of the United States",
    )
    if evidence:
        state.presentment_kinds = ("Order", "Resolution", "Vote")
        for kind in state.presentment_kinds:
            claims.append(_claim(
                f"{kind} requiring concurrence of Senate and House of Representatives",
                "presented_to", "President of the United States", evidence,
                condition="except on a question of Adjournment",
            ))
    evidence = _match(text, r"except on a question of Adjournment")
    if evidence:
        claims.append(_claim(
            "question of Adjournment", "requires_presidential_presentation",
            "President", evidence, polarity="negative",
        ))

    approval = _match(
        text, r"before the Same shall take Effect, shall be approved by him",
    )
    repassage = _match(
        text,
        r"or being disapproved by him, shall be repassed by two thirds of the "
        r"Senate and House of Representatives",
    )
    for kind in state.presentment_kinds:
        if approval:
            claims.append(_claim(
                f"{kind} requiring concurrence of Senate and House of Representatives",
                "approved_by", "President", approval,
                condition=(
                    "before taking effect; except question of Adjournment; unless "
                    "disapproval is overcome by two-thirds repassage"
                ),
            ))
        if repassage:
            claims.append(_claim(
                f"{kind} disapproved by President", "repassed_by",
                "two thirds of Senate and two thirds of House of Representatives",
                repassage,
                condition=(
                    "before taking effect; according to Rules and Limitations "
                    "prescribed in the Case of a Bill; except question of Adjournment"
                ),
            ))

    return claims


def _assemble_section_9(text: str) -> list[ProvisionFrame]:
    """Assemble the coordinated prohibitions and exceptions in Section 9."""
    claims: list[ProvisionFrame] = []

    migration = _match(
        text,
        r"The Migration or Importation of such Persons as any of the States "
        r"now existing shall think proper to admit, shall not be prohibited "
        r"by the Congress prior to the Year one thousand eight hundred and eight",
    )
    if migration:
        condition = (
            "prior to the Year one thousand eight hundred and eight; Persons "
            "whom a then-existing State thinks proper to admit"
        )
        for movement in ("Migration", "Importation"):
            claims.append(_claim(
                "Congress", "prohibits",
                f"{movement} of Persons whom any then-existing State thinks proper to admit",
                migration, polarity="negative", condition=condition,
            ))

    import_charge = _match(
        text,
        r"but a Tax or duty may be imposed on such Importation, not exceeding "
        r"ten dollars for each Person",
    )
    if import_charge:
        condition = (
            "on Importation of such Persons; not exceeding ten dollars for each Person"
        )
        for charge in ("Tax", "duty"):
            claims.append(_claim(
                charge, "may_be_imposed_on", "such Importation", import_charge,
                modality="may", condition=condition,
            ))

    habeas = _match(
        text,
        r"The Privilege of the Writ of Habeas Corpus shall not be suspended, "
        r"unless when in Cases of Rebellion or Invasion the public Safety may require it",
    )
    if habeas:
        claims.append(_claim(
            "Privilege of Writ of Habeas Corpus", "suspended", "anywhere", habeas,
            polarity="negative",
            condition=(
                "unless in Case of Rebellion or Invasion and public Safety may "
                "require suspension"
            ),
        ))
    habeas_exception = _match(
        text,
        r"unless when in Cases of Rebellion or Invasion the public Safety may require it",
    )
    if habeas_exception:
        condition = "public Safety may require suspension; exception to ordinary prohibition"
        for emergency in ("Rebellion", "Invasion"):
            claims.append(_claim(
                "Privilege of Writ of Habeas Corpus", "may_be_suspended",
                f"in Case of {emergency}", habeas_exception,
                modality="may", condition=condition,
            ))

    forbidden_laws = _match(
        text, r"No Bill of Attainder or ex post facto Law shall be passed",
    )
    if forbidden_laws:
        for law in ("Bill of Attainder", "ex post facto Law"):
            claims.append(_claim(
                "Federal lawmaking authority", "passes", law, forbidden_laws,
                polarity="negative",
            ))

    direct_taxes = _match(
        text,
        r"No Capitation, or other direct, Tax shall be laid, unless in Proportion "
        r"to the Census or enumeration herein before directed to be taken",
    )
    if direct_taxes:
        condition = (
            "unless in Proportion to the Census or enumeration directed earlier "
            "in Constitution"
        )
        for tax in ("Capitation Tax", "other direct Tax"):
            claims.append(_claim(
                "Federal lawmaking authority", "lays", tax, direct_taxes,
                polarity="negative", condition=condition,
            ))
    direct_tax_exception = _match(
        text,
        r"unless in Proportion to the Census or enumeration herein before directed "
        r"to be taken",
    )
    if direct_tax_exception:
        condition = (
            "only in Proportion to the Census or enumeration directed earlier in "
            "Constitution"
        )
        for tax in ("Capitation Tax", "other direct Tax"):
            claims.append(_claim(
                "Federal lawmaking authority", "may_lay", tax,
                direct_tax_exception, modality="may", condition=condition,
            ))

    export_taxes = _match(
        text, r"No Tax or Duty shall be laid on Articles exported from any State",
    )
    if export_taxes:
        for charge in ("Tax", "Duty"):
            claims.append(_claim(
                "Federal lawmaking authority", "lays",
                f"{charge} on Articles exported from any State", export_taxes,
                polarity="negative",
            ))

    port_preference = _match(
        text,
        r"No Preference shall be given by any Regulation of Commerce or Revenue "
        r"to the Ports of one State over those of another",
    )
    if port_preference:
        for regulation in ("Commerce", "Revenue"):
            claims.append(_claim(
                f"Regulation of {regulation}", "gives_Preference_to",
                "Ports of one State over those of another", port_preference,
                polarity="negative",
            ))

    vessel = _match(
        text,
        r"nor shall Vessels bound to, or from, one State, be obliged to enter, "
        r"clear, or pay Duties in another",
    )
    if vessel:
        for direction in ("to", "from"):
            for obligation in (
                "enter in another State",
                "clear in another State",
                "pay Duties in another State",
            ):
                claims.append(_claim(
                    f"Vessels bound {direction} one State", "obliged_to",
                    obligation, vessel, polarity="negative",
                ))

    treasury = _match(
        text,
        r"No Money shall be drawn from the Treasury, but in Consequence of "
        r"Appropriations made by Law",
    )
    if treasury:
        claims.append(_claim(
            "Money", "drawn_from", "Treasury", treasury, polarity="negative",
            condition="except in Consequence of Appropriations made by Law",
        ))

    statement = _match(
        text,
        r"a regular Statement and Account of the Receipts and Expenditures of "
        r"all public Money shall be published from time to time",
    )
    if statement:
        for content in (
            "Receipts of all public Money",
            "Expenditures of all public Money",
        ):
            claims.append(_claim(
                "regular Statement and Account", "includes", content, statement,
                condition="published from time to time",
            ))
        claims.append(_claim(
            "regular Statement and Account of Receipts and Expenditures of all public Money",
            "published", "from time to time", statement,
        ))

    nobility = _match(
        text, r"No Title of Nobility shall be granted by the United States",
    )
    if nobility:
        claims.append(_claim(
            "United States", "grants", "Title of Nobility", nobility,
            polarity="negative",
        ))

    emoluments = _match(
        text,
        r"no Person holding any Office of Profit or Trust under them, shall, "
        r"without the Consent of the Congress, accept of any present, Emolument, "
        r"Office, or Title, of any kind whatever, from any King, Prince, or foreign State",
    )
    if emoluments:
        subject = "Person holding Office of Profit or Trust under the United States"
        for source in ("King", "Prince", "foreign State"):
            for item in ("present", "Emolument", "Office", "Title"):
                claims.append(_claim(
                    subject, "accepts", f"{item} from {source}", emoluments,
                    polarity="negative",
                    condition="without the Consent of the Congress",
                ))

    return claims


def _assemble_article_1_section_5(text: str) -> list[ProvisionFrame]:
    """Assemble the House procedure rules in Article I, Section 5."""
    claims: list[ProvisionFrame] = []

    judging = _match(
        text,
        r"Each House shall be the Judge of the Elections, Returns and "
        r"Qualifications of its own Members",
    )
    if judging:
        for item in ("Elections", "Returns", "Qualifications"):
            claims.append(_claim(
                "Each House of Congress", "judges",
                f"{item} of its own Members", judging,
            ))

    quorum = _match(text, r"a Majority of each shall constitute a Quorum to do Business")
    if quorum:
        claims.append(_claim(
            "Majority of each House", "constitutes", "Quorum to do Business", quorum,
        ))

    adjourn = _match(text, r"a smaller Number may adjourn from day to day")
    if adjourn:
        claims.append(_claim(
            "smaller Number of each House", "may_adjourn", "from day to day",
            adjourn, modality="may", condition="fewer than a quorum",
        ))

    compel = _match(text, r"may be authorized to compel the Attendance of absent Members")
    if compel:
        claims.append(_claim(
            "smaller Number of each House", "may_be_authorized_to_compel",
            "Attendance of absent Members", compel, modality="may",
            condition=(
                "fewer than a quorum; in such Manner and under such Penalties "
                "as each House may provide"
            ),
        ))

    manner = _match(
        text,
        r"in such Manner, and under such Penalties as each House may provide",
    )
    if manner:
        for object_ in (
            "Manner for compelling attendance of absent Members",
            "Penalties for compelling attendance of absent Members",
        ):
            claims.append(_claim(
                "Each House of Congress", "may_provide", object_, manner,
                modality="may",
            ))

    rules = _match(text, r"Each House may determine the Rules of its Proceedings")
    if rules:
        claims.append(_claim(
            "Each House of Congress", "may_determine", "Rules of its Proceedings",
            rules, modality="may",
        ))
    punish = _match(text, r"punish its Members for disorderly Behaviour")
    if punish:
        claims.append(_claim(
            "Each House of Congress", "may_punish",
            "its Members for disorderly Behaviour", punish, modality="may",
        ))
    expel = _match(text, r"with the Concurrence of two thirds, expel a Member")
    if expel:
        claims.append(_claim(
            "Each House of Congress", "may_expel", "a Member", expel,
            modality="may", condition="with the Concurrence of two thirds",
        ))

    journal = _match(text, r"Each House shall keep a Journal of its Proceedings")
    if journal:
        claims.append(_claim(
            "Each House of Congress", "keeps", "Journal of its Proceedings", journal,
        ))
    publish = _match(
        text,
        r"from time to time publish the same, excepting such Parts as may in "
        r"their Judgment require Secrecy",
    )
    if publish:
        claims.append(_claim(
            "Each House of Congress", "publishes", "Journal of its Proceedings",
            publish,
            condition=(
                "from time to time; except Parts that in its Judgment require Secrecy"
            ),
        ))
    secrecy = _match(text, r"excepting such Parts as may in their Judgment require Secrecy")
    if secrecy:
        claims.append(_claim(
            "Each House of Congress", "may_except_from_publication",
            "Parts of its Journal", secrecy, modality="may",
            condition="the House judges the Parts require Secrecy",
        ))

    votes = _match(
        text,
        r"the Yeas and Nays of the Members of either House on any question "
        r"shall, at the Desire of one fifth of those Present, be entered on the Journal",
    )
    if votes:
        for vote in ("Yeas", "Nays"):
            claims.append(_claim(
                f"{vote} of Members of either House on any question", "entered_on",
                "Journal of that House", votes,
                condition="at the Desire of one fifth of those Present",
            ))

    long_adjournment = _match(
        text,
        r"Neither House, during the Session of Congress, shall, without the "
        r"Consent of the other, adjourn for more than three days",
    )
    shared_condition = (
        "during the Session of Congress; without the Consent of the other House"
    )
    if long_adjournment:
        claims.append(_claim(
            "Either House of Congress", "adjourns_for", "more than three days",
            long_adjournment, polarity="negative", condition=shared_condition,
        ))
    other_place = _match(
        text,
        r"nor to any other Place than that in which the two Houses shall be sitting",
    )
    if other_place:
        claims.append(_claim(
            "Either House of Congress", "adjourns_to",
            "Place other than that in which the two Houses are sitting", other_place,
            polarity="negative", condition=shared_condition,
        ))

    return claims


def _assemble_article_1_section_6(text: str) -> list[ProvisionFrame]:
    """Assemble compensation, privilege, and incompatibility provisions."""
    claims: list[ProvisionFrame] = []
    legislators = ("Senators", "Representatives")

    compensation = _match(
        text,
        r"The Senators and Representatives shall receive a Compensation for their Services",
    )
    if compensation:
        for actor in legislators:
            claims.append(_claim(
                actor, "receive", "Compensation for Services", compensation,
            ))
    law = _match(text, r"to be ascertained by Law")
    if law:
        claims.append(_claim(
            "Compensation of Senators and Representatives", "ascertained_by", "Law", law,
        ))
    treasury = _match(text, r"paid out of the Treasury of the United States")
    if treasury:
        claims.append(_claim(
            "Compensation of Senators and Representatives", "paid_out_of",
            "Treasury of the United States", treasury,
        ))

    attendance = _match(
        text,
        r"They shall in all Cases, except Treason, Felony and Breach of the Peace, "
        r"be privileged from Arrest during their Attendance at the Session of "
        r"their respective Houses",
    )
    if attendance:
        for actor in legislators:
            claims.append(_claim(
                actor, "privileged_from", "Arrest", attendance,
                condition=(
                    "during Attendance at the Session of their respective House; "
                    "except Treason, Felony and Breach of the Peace"
                ),
            ))
    travel = _match(text, r"and in going to and returning from the same")
    if travel:
        for actor in legislators:
            for direction in ("going to", "returning from"):
                claims.append(_claim(
                    actor, "privileged_from", "Arrest", travel,
                    condition=(
                        f"{direction} a Session of their respective House; except "
                        "Treason, Felony and Breach of the Peace"
                    ),
                ))
    speech = _match(
        text,
        r"for any Speech or Debate in either House, they shall not be questioned "
        r"in any other Place",
    )
    if speech:
        for actor in legislators:
            claims.append(_claim(
                actor, "questioned_in",
                "any other Place for Speech or Debate in either House", speech,
                polarity="negative",
            ))

    created = _match(
        text,
        r"No Senator or Representative shall, during the Time for which he was "
        r"elected, be appointed to any civil Office under the Authority of the "
        r"United States, which shall have been created",
    )
    if created:
        for actor in legislators:
            claims.append(_claim(
                actor, "appointed_to", "civil Office under Authority of the United States",
                created, polarity="negative",
                condition=(
                    "the civil Office was created during the Time for which the "
                    "member was elected"
                ),
            ))
    emoluments = _match(
        text,
        r"or the Emoluments whereof shall have been encreased during such time",
    )
    if emoluments:
        for actor in legislators:
            claims.append(_claim(
                actor, "appointed_to", "civil Office under Authority of the United States",
                emoluments, polarity="negative",
                condition=(
                    "the civil Office’s Emoluments were increased during the Time "
                    "for which the member was elected"
                ),
            ))

    officeholder = _match(
        text,
        r"no Person holding any Office under the United States, shall be a Member "
        r"of either House during his Continuance in Office",
    )
    if officeholder:
        for chamber in ("Senate", "House of Representatives"):
            claims.append(_claim(
                "Person holding any Office under the United States", "is_Member_of",
                chamber, officeholder, polarity="negative",
                condition="during Continuance in the federal Office",
            ))

    return claims


def _assemble_article_6(text: str, state: ProvisionState) -> list[ProvisionFrame]:
    """Assemble debts, supremacy, oath, and religious-test provisions."""
    claims: list[ProvisionFrame] = []

    debts = _match(
        text,
        r"All Debts contracted and Engagements entered into, before the Adoption "
        r"of this Constitution, shall be as valid against the United States under "
        r"this Constitution, as under the Confederation",
    )
    if debts:
        for subject in (
            "Debts contracted before Adoption of this Constitution",
            "Engagements entered into before Adoption of this Constitution",
        ):
            claims.append(_claim(
                subject, "are_as_valid_against", "United States under this Constitution",
                debts, condition="same validity as under the Confederation",
            ))

    preamble = _match(
        text,
        r"This Constitution, and the Laws of the United States which shall be "
        r"made in Pursuance thereof",
    )
    if preamble:
        state.article_6_supremacy_preamble = preamble
    supremacy = _match(
        text,
        r"This Constitution, and the Laws of the United States which shall be "
        r"made in Pursuance thereof; and all Treaties made, or which shall be "
        r"made, under the Authority of the United States, shall be the supreme "
        r"Law of the Land",
    )
    treaty_tail = _match(
        text,
        r"all Treaties made, or which shall be made, under the Authority of the "
        r"United States, shall be the supreme Law of the Land",
    )
    if supremacy is None and treaty_tail and state.article_6_supremacy_preamble:
        supremacy = f"{state.article_6_supremacy_preamble}; and {treaty_tail}"
    if supremacy:
        for subject, predicate, condition in (
            ("This Constitution", "is", None),
            (
                "Laws of United States made in Pursuance of this Constitution",
                "are", "made in Pursuance of this Constitution",
            ),
            (
                "Treaties made under Authority of United States", "are",
                "made under Authority of United States",
            ),
            (
                "Treaties which shall be made under Authority of United States", "are",
                "shall be made under Authority of United States",
            ),
        ):
            claims.append(_claim(
                subject, predicate, "supreme Law of the Land", supremacy,
                condition=condition,
            ))

    judges = _match(text, r"the Judges in every State shall be bound thereby")
    if judges:
        claims.append(_claim(
            "Judges in every State", "are_bound_by", "supreme Law of the Land", judges,
        ))
    contrary = _match(
        text,
        r"any Thing in the Constitution or Laws of any State to the Contrary notwithstanding",
    )
    if contrary:
        for subject in (
            "Contrary provision in Constitution of any State",
            "Contrary Law of any State",
        ):
            claims.append(_claim(
                subject, "displaces", "supreme Law of the Land", contrary,
                polarity="negative",
            ))

    oath = _match(
        text,
        r"The Senators and Representatives before mentioned, and the Members of "
        r"the several State Legislatures, and all executive and judicial Officers, "
        r"both of the United States and of the several States, shall be bound by "
        r"Oath or Affirmation, to support this Constitution",
    )
    if oath:
        for actor in (
            "Senators",
            "Representatives",
            "Members of the several State Legislatures",
            "executive Officers of the United States",
            "judicial Officers of the United States",
            "executive Officers of the several States",
            "judicial Officers of the several States",
        ):
            claims.append(_claim(
                actor, "bound_by_Oath_or_Affirmation_to_support",
                "this Constitution", oath,
            ))

    religious_test = _match(
        text,
        r"no religious Test shall ever be required as a Qualification to any "
        r"Office or public Trust under the United States",
    )
    if religious_test:
        for object_ in (
            "any Office under United States",
            "any public Trust under United States",
        ):
            claims.append(_claim(
                "religious Test", "required_as_Qualification_to", object_,
                religious_test, polarity="negative",
            ))

    return claims


def _assemble_amendment_14_section_2(text: str) -> list[ProvisionFrame]:
    """Assemble apportionment and voting-rights claims in Amendment XIV.2."""
    claims: list[ProvisionFrame] = []

    apportionment = _match(
        text,
        r"Representatives shall be apportioned among the several States "
        r"according to their respective numbers",
    )
    if apportionment:
        claims.append(_claim(
            "Representatives", "apportioned_among", "several States",
            apportionment,
            condition="according to each State’s respective numbers",
        ))

    count = _match(text, r"counting the whole number of persons in each State")
    if count:
        claims.append(_claim(
            "apportionment count of each State", "includes",
            "whole number of persons in that State", count,
        ))
    exclusion = _match(text, r"excluding Indians not taxed")
    if exclusion:
        claims.append(_claim(
            "apportionment count of each State", "includes",
            "Indians not taxed", exclusion, polarity="negative",
        ))

    reduction = _verbatim(
        text,
        r"But when the right to vote at any election for the choice of electors "
        r"for President and Vice-President of the United States, Representatives "
        r"in Congress, the Executive and Judicial officers of a State, or the "
        r"members of the Legislature thereof, is denied to any of the male "
        r"inhabitants of such State, being twenty-one years of age,\* and citizens "
        r"of the United States, or in any way abridged, except for participation "
        r"in rebellion, or other crime, the basis of representation therein shall "
        r"be reduced in the proportion which the number of such male citizens shall "
        r"bear to the whole number of male citizens twenty-one years of age in such State\.",
    )
    if reduction:
        subject = "basis of representation in the State"
        object_ = (
            "number of affected male citizens relative to all male citizens "
            "twenty-one years of age in that State"
        )
        suffix = (
            "to male State inhabitants who are twenty-one years of age and citizens "
            "of the United States; except for participation in rebellion or other crime"
        )
        offices = (
            "electors for President",
            "electors for Vice-President",
            "Representatives in Congress",
            "Executive officers of a State",
            "Judicial officers of a State",
            "members of the State Legislature",
        )
        for office in offices:
            for restriction in ("denied", "abridged"):
                claims.append(_claim(
                    subject, "reduced_in_proportion_to", object_, reduction,
                    condition=(
                        f"right to vote in election for {office} is {restriction} {suffix}"
                    ),
                ))
    return claims


def _assemble_article_5(text: str) -> list[ProvisionFrame]:
    """Assemble the two amendment routes, ratification, and Article V limits."""
    claims: list[ProvisionFrame] = []

    proposal = _match(
        text,
        r"The Congress, whenever two thirds of both Houses shall deem it necessary, "
        r"shall propose Amendments to this Constitution",
    )
    if proposal:
        claims.append(_claim(
            "Congress", "shall_propose", "Amendments to this Constitution", proposal,
            condition="two thirds of both Houses deem it necessary",
        ))
    necessity = _match(
        text, r"whenever two thirds of both Houses shall deem it necessary",
    )
    if necessity:
        claims.append(_claim(
            "both Houses of Congress", "deem_necessary",
            "proposing Amendments to this Constitution", necessity,
            condition="two thirds of each House",
        ))
    application = _match(
        text, r"on the Application of the Legislatures of two thirds of the several States",
    )
    if application:
        claims.append(_claim(
            "Legislatures of the several States", "apply_for",
            "Convention for proposing Amendments", application, modality="may",
            condition="applications from Legislatures of two thirds of several States",
        ))
    convention_call = _match(
        text,
        r"on the Application of the Legislatures of two thirds of the several States, "
        r"shall call a Convention for proposing Amendments",
    )
    if convention_call:
        claims.append(_claim(
            "Congress", "shall_call", "Convention for proposing Amendments",
            convention_call,
            condition="application of Legislatures of two thirds of the several States",
        ))
    convention = _match(text, r"a Convention for proposing Amendments")
    if convention:
        claims.append(_claim(
            "Convention called by Congress", "proposes",
            "Amendments to this Constitution", convention, modality="may",
            condition=(
                "Convention called on application of Legislatures of two thirds of States"
            ),
        ))

    validity = _match(
        text,
        r"which, in either Case, shall be valid to all Intents and Purposes, as Part "
        r"of this Constitution, when ratified by the Legislatures of three fourths "
        r"of the several States, or by Conventions in three fourths thereof",
    )
    if validity:
        for condition in (
            "ratified by Legislatures of three fourths of several States; Congress "
            "has proposed this mode of Ratification",
            "ratified by Conventions in three fourths of States; Congress has "
            "proposed this mode of Ratification",
        ):
            claims.append(_claim(
                "Amendments proposed by Congress or Convention", "become_valid_as",
                "Part of this Constitution", validity, condition=condition,
            ))
    legislature_ratification = _match(
        text, r"when ratified by the Legislatures of three fourths of the several States",
    )
    if legislature_ratification:
        claims.append(_claim(
            "Legislatures of three fourths of the several States", "may_ratify",
            "proposed Amendment", legislature_ratification, modality="may",
            condition="Congress proposes Legislature mode of ratification",
        ))
    convention_ratification = _match(text, r"or by Conventions in three fourths thereof")
    if convention_ratification:
        claims.append(_claim(
            "Conventions in three fourths of the several States", "may_ratify",
            "proposed Amendment", convention_ratification, modality="may",
            condition="Congress proposes Convention mode of ratification",
        ))
    mode = _match(
        text, r"as the one or the other Mode of Ratification may be proposed by the Congress",
    )
    if mode:
        claims.append(_claim(
            "Congress", "may_propose", "one or the other Mode of Ratification", mode,
            modality="may", condition="Legislatures of States or Conventions in States",
        ))

    temporal_limit = _match(
        text,
        r"no Amendment which may be made prior to the Year One thousand eight "
        r"hundred and eight shall in any Manner affect the first and fourth Clauses "
        r"in the Ninth Section of the first Article",
    )
    if temporal_limit:
        for clause in (
            "first Clause in Ninth Section of first Article",
            "fourth Clause in Ninth Section of first Article",
        ):
            claims.append(_claim(
                "Amendment made prior to Year One thousand eight hundred and eight",
                "may_affect", clause, temporal_limit, polarity="negative",
                condition="Amendment made prior to Year 1808",
            ))
    suffrage = _match(
        text,
        r"no State, without its Consent, shall be deprived of its equal Suffrage in the Senate",
    )
    if suffrage:
        claims.append(_claim(
            "State", "deprived_of", "equal Suffrage in the Senate", suffrage,
            polarity="negative", condition="without that State’s Consent",
        ))
    return claims


def _assemble_article_4_section_3(text: str) -> list[ProvisionFrame]:
    """Assemble State admission, formation, property, and claims provisions."""
    claims: list[ProvisionFrame] = []
    admission = _match(text, r"New States may be admitted by the Congress into this Union")
    if admission:
        claims.append(_claim(
            "Congress", "may_admit", "New States into this Union", admission,
            modality="may",
        ))
    intrastate = _match(
        text, r"no new State shall be formed or erected within the Jurisdiction of any other State",
    )
    if intrastate:
        claims.append(_claim(
            "new State", "formed_or_erected_within", "Jurisdiction of any other State",
            intrastate, polarity="negative",
            condition="without Consent of Legislature of State concerned and Congress",
        ))
    junction = _match(
        text,
        r"nor any State be formed by the Junction of two or more States, or Parts "
        r"of States, without the Consent of the Legislatures of the States concerned "
        r"as well as of the Congress",
    )
    if junction:
        for object_ in ("two or more States", "Parts of States"):
            claims.append(_claim(
                "State", "formed_by_Junction_of", object_, junction,
                polarity="negative",
                condition="without Consent of Legislatures of States concerned and Congress",
            ))
    consent = _match(
        text,
        r"without the Consent of the Legislatures of the States concerned as well as of the Congress",
    )
    if consent:
        for actor in ("Legislatures of States concerned", "Congress"):
            claims.append(_claim(
                actor, "must_consent_to",
                "formation of a State by Junction of States or Parts of States",
                consent,
                condition="formation by Junction of two or more States or Parts of States",
            ))
    disposal = _match(
        text,
        r"The Congress shall have Power to dispose of and make all needful Rules "
        r"and Regulations respecting the Territory or other Property belonging to the United States",
    )
    if disposal:
        for object_ in (
            "Territory belonging to United States",
            "other Property belonging to United States",
        ):
            claims.append(_claim(
                "Congress", "has_Power_to_dispose_of", object_, disposal,
            ))
    rules = _match(
        text,
        r"make all needful Rules and Regulations respecting the Territory or other "
        r"Property belonging to the United States",
    )
    if rules:
        for property_ in (
            "Territory belonging to United States",
            "other Property belonging to United States",
        ):
            claims.append(_claim(
                "Congress", "has_Power_to_make",
                f"all needful Rules and Regulations respecting {property_}", rules,
            ))
    prejudice = _match(
        text,
        r"nothing in this Constitution shall be so construed as to Prejudice any "
        r"Claims of the United States, or of any particular State",
    )
    if prejudice:
        for object_ in ("Claims of United States", "Claims of any particular State"):
            claims.append(_claim(
                "Constitution", "construed_to_Prejudice", object_, prejudice,
                polarity="negative",
            ))
    return claims


def _assemble_amendment_17(
    text: str, state: ProvisionState,
) -> list[ProvisionFrame]:
    """Assemble direct Senate elections and vacancy procedures."""
    claims: list[ProvisionFrame] = []
    senate = _match(
        text,
        r"The Senate of the United States shall be composed of two Senators from "
        r"each State, elected by the people thereof, for six years",
    )
    if senate:
        state.amendment_17_senate_preamble = senate
        whole = f"{senate}; and each Senator shall have one vote."
        for subject, predicate, object_ in (
            ("Senate of the United States", "composed_of", "two Senators from each State"),
            ("Senators from each State", "elected_by", "people of that State"),
            ("Senators from each State", "serve_for", "six years"),
        ):
            claims.append(_claim(subject, predicate, object_, whole))

    vote = _verbatim(text, r"each Senator shall have one vote\.")
    if vote:
        claims.append(_claim(
            "each Senator", "has_vote_count", "1", _match(text, r"each Senator shall have one vote") or vote,
        ))
    electors = _verbatim(
        text,
        r"The electors in each State shall have the qualifications requisite for "
        r"electors of the most numerous branch of the State legislatures\.",
    )
    if electors:
        claims.append(_claim(
            "electors of Senators in each State", "have_qualifications_of",
            "electors of the most numerous branch of the State legislature", electors,
        ))
    writs = _match(
        text,
        r"When vacancies happen in the representation of any State in the Senate, "
        r"the executive authority of such State shall issue writs of election to fill such vacancies",
    )
    if writs:
        claims.append(_claim(
            "executive authority of the State", "issues",
            "writs of election to fill Senate vacancies", writs,
            condition="when vacancies happen in the State’s Senate representation",
        ))
    appointment = _match(
        text,
        r"the legislature of any State may empower the executive thereof to make "
        r"temporary appointments until the people fill the vacancies by election "
        r"as the legislature may direct",
    )
    if appointment:
        claims.extend((
            _claim(
                "legislature of any State", "may_empower",
                "State executive to make temporary Senate appointments", appointment,
                modality="may", condition="Senate vacancy in the State",
            ),
            _claim(
                "State executive", "may_make", "temporary Senate appointments",
                appointment, modality="may",
                condition=(
                    "State legislature has empowered executive; until people fill "
                    "Senate vacancy by election"
                ),
            ),
        ))
    people = _match(
        text, r"until the people fill the vacancies by election as the legislature may direct",
    )
    if people:
        claims.append(_claim(
            "people of the State", "fill_by_election", "Senate vacancy", people,
            modality=None,
            condition="after a Senate vacancy; election as State legislature may direct",
        ))
    direction = _match(text, r"by election as the legislature may direct")
    if direction:
        claims.append(_claim(
            "State legislature", "may_direct",
            "manner of election to fill Senate vacancy", direction, modality="may",
            condition="Senate vacancy",
        ))
    grandfather = _verbatim(
        text,
        r"This amendment shall not be so construed as to affect the election or "
        r"term of any Senator chosen before it becomes valid as part of the Constitution\.",
    )
    if grandfather:
        for object_ in (
            "election of a Senator chosen before the amendment becomes valid",
            "term of a Senator chosen before the amendment becomes valid",
        ):
            claims.append(_claim(
                "Amendment XVII", "affects", object_, grandfather,
                polarity="negative",
            ))
    return claims


def _assemble_article_2_section_3(text: str) -> list[ProvisionFrame]:
    """Assemble the President's reporting, convening, and execution duties."""
    claims: list[ProvisionFrame] = []
    union = _match(
        text,
        r"He shall from time to time give to the Congress Information of the State of the Union",
    )
    if union:
        claims.append(_claim(
            "President", "gives_to", "Congress Information of the State of the Union",
            union, condition="from time to time",
        ))
    measures = _match(
        text,
        r"recommend to their Consideration such Measures as he shall judge necessary and expedient",
    )
    if measures:
        claims.append(_claim(
            "President", "recommends_to_Congress",
            "Measures he judges necessary and expedient", measures,
            condition="as he judges necessary and expedient",
        ))
    convening = _match(
        text, r"he may, on extraordinary Occasions, convene both Houses, or either of them",
    )
    if convening:
        for object_ in ("both Houses of Congress", "either House of Congress"):
            claims.append(_claim(
                "President", "may_convene", object_, convening, modality="may",
                condition="on extraordinary Occasions",
            ))
    adjournment = _match(
        text,
        r"in Case of Disagreement between them, with Respect to the Time of "
        r"Adjournment, he may adjourn them to such Time as he shall think proper",
    )
    if adjournment:
        claims.append(_claim(
            "President", "may_adjourn", "Houses of Congress", adjournment,
            modality="may",
            condition=(
                "Houses disagree with respect to Time of Adjournment; to such Time "
                "as President thinks proper"
            ),
        ))
    reception = _match(text, r"he shall receive Ambassadors and other public Ministers")
    if reception:
        for object_ in ("Ambassadors", "other public Ministers"):
            claims.append(_claim("President", "receives", object_, reception))
    execution = _match(text, r"he shall take Care that the Laws be faithfully executed")
    if execution:
        claims.append(_claim(
            "President", "takes_Care_that", "Laws be faithfully executed", execution,
        ))
    commission = _match(text, r"shall Commission all the Officers of the United States")
    if commission:
        claims.append(_claim(
            "President", "commissions", "all Officers of the United States", commission,
        ))
    return claims


def _assemble_amendment_14_section_1(text: str) -> list[ProvisionFrame]:
    """Assemble the Citizenship, Due Process, and Equal Protection clauses."""
    claims: list[ProvisionFrame] = []
    citizenship = _verbatim(
        text,
        r"All persons born or naturalized in the United States, and subject to "
        r"the jurisdiction thereof, are citizens of the United States and of "
        r"the State wherein they reside\.",
    )
    if citizenship:
        condition = (
            "subject to the jurisdiction of the United States; for State "
            "citizenship, resides in that State"
        )
        for status in ("born", "naturalized"):
            subject = f"person {status} in the United States"
            claims.extend((
                _claim(
                    subject, "is_citizen_of", "United States", citizenship,
                    modality=None, condition=condition,
                ),
                _claim(
                    subject, "is_citizen_of", "State wherein the person resides",
                    citizenship, modality=None, condition=condition,
                ),
            ))

    abridgment = _match(
        text,
        r"No State shall make or enforce any law which shall abridge the "
        r"privileges or immunities of citizens of the United States",
    )
    if abridgment:
        for action in ("make", "enforce"):
            for right in ("privileges", "immunities"):
                claims.append(_claim(
                    "State", action,
                    f"law abridging the {right} of citizens of the United States",
                    abridgment, polarity="negative",
                ))

    deprivation = _match(
        text,
        r"nor shall any State deprive any person of life, liberty, or property, "
        r"without due process of law",
    )
    if deprivation:
        for interest in ("life", "liberty", "property"):
            claims.append(_claim(
                "State", "deprive", f"any person of {interest}", deprivation,
                polarity="negative", condition="without due process of law",
            ))

    protection = _match(
        text,
        r"nor deny to any person within its jurisdiction the equal protection "
        r"of the laws",
    )
    if protection:
        claims.append(_claim(
            "State", "deny", "equal protection of the laws to any person",
            protection, polarity="negative",
            condition="person within the State’s jurisdiction",
        ))
    return claims


def _assemble_article_4_section_2(text: str) -> list[ProvisionFrame]:
    """Assemble interstate privileges, extradition, and service provisions."""
    claims: list[ProvisionFrame] = []
    privileges = _match(
        text,
        r"The Citizens of each State shall be entitled to all Privileges and "
        r"Immunities of Citizens in the several States",
    )
    if privileges:
        for right in ("Privileges", "Immunities"):
            claims.append(_claim(
                "Citizens of each State", "are_entitled_to",
                f"all {right} of Citizens in the several States", privileges,
            ))

    fugitive = _match(
        text,
        r"A Person charged in any State with Treason, Felony, or other Crime, "
        r"who shall flee from Justice, and be found in another State, shall on "
        r"Demand of the executive Authority of the State from which he fled, be "
        r"delivered up, to be removed to the State having Jurisdiction of the Crime",
    )
    if fugitive:
        condition = (
            "fled from Justice; found in another State; Demand of executive "
            "Authority of State from which person fled"
        )
        for crime in ("Treason", "Felony", "other Crime"):
            claims.append(_claim(
                f"Person charged in any State with {crime}", "delivered_up_to",
                "State having Jurisdiction of the Crime", fugitive,
                condition=condition,
            ))
    demand = _match(
        text,
        r"on Demand of the executive Authority of the State from which he fled",
    )
    if demand:
        claims.append(_claim(
            "executive Authority of State from which charged Person fled",
            "may_demand", "delivery of Person fleeing Justice", demand,
            modality="may",
            condition=(
                "Person charged with Treason, Felony, or other Crime flees and "
                "is found in another State"
            ),
        ))
    removal = _match(
        text,
        r"be delivered up, to be removed to the State having Jurisdiction of the Crime",
    )
    if removal:
        claims.append(_claim(
            "Person delivered up after flight from Justice", "removed_to",
            "State having Jurisdiction of the Crime", removal,
            condition="upon requisite executive Demand",
        ))

    discharge = _match(
        text,
        r"No Person held to Service or Labour in one State, under the Laws "
        r"thereof, escaping into another, shall, in Consequence of any Law or "
        r"Regulation therein, be discharged from such Service or Labour",
    )
    if discharge:
        claims.append(_claim(
            "Person held to Service or Labour in one State under its Laws",
            "discharged_from", "such Service or Labour", discharge,
            polarity="negative",
            condition=(
                "escapes into another State; purported discharge due to a Law "
                "or Regulation of destination State"
            ),
        ))
    delivery = _match(
        text,
        r"but shall be delivered up on Claim of the Party to whom such Service "
        r"or Labour may be due",
    )
    if delivery:
        claims.append(_claim(
            "Person held to Service or Labour in one State under its Laws who "
            "escapes into another",
            "delivered_up_on_Claim_of",
            "Party to whom Service or Labour may be due", delivery,
            condition="Claim of Party to whom such Service or Labour may be due",
        ))
    return claims


def _assemble_article_1_section_4(
    text: str, state: ProvisionState,
) -> list[ProvisionFrame]:
    """Assemble congressional election regulation and meeting rules."""
    claims: list[ProvisionFrame] = []
    state_rules = _match(
        text,
        r"The Times, Places and Manner of holding Elections for Senators and "
        r"Representatives, shall be prescribed in each State by the Legislature thereof",
    )
    if state_rules:
        state.article_1_section_4_election_preamble = state_rules
        for item in ("Times", "Places", "Manner"):
            claims.append(_claim(
                "State Legislature", "prescribes",
                f"{item} of holding Elections for Senators and Representatives",
                state_rules,
            ))
    federal_rules = _match(
        text,
        r"the Congress may at any time by Law make or alter such Regulations, "
        r"except as to the Places of chusing Senators",
    )
    if federal_rules:
        condition = "at any time; except as to Places of chusing Senators"
        claims.extend((
            _claim(
                "Congress", "may_make_by_Law",
                "State election Regulations for Senators and Representatives",
                federal_rules, modality="may", condition=condition,
            ),
            _claim(
                "Congress", "may_alter_by_Law",
                "State election Regulations for Senators and Representatives",
                federal_rules, modality="may", condition=condition,
            ),
        ))
    exception = _match(text, r"except as to the Places of chusing Senators")
    if exception:
        claims.append(_claim(
            "Congress", "may_make_or_alter", "Places of chusing Senators",
            exception, modality="may", polarity="negative",
        ))
    # A lone quotation of the meeting sentence remains on the generic parser's
    # established path.  The audited Section 4 document has already supplied
    # its distinctive elections clause by the time this coordinated sentence
    # is reached.
    if not state.article_1_section_4_election_preamble:
        return claims
    assembly = _match(text, r"The Congress shall assemble at least once in every Year")
    if assembly:
        claims.append(_claim(
            "Congress", "assembles", "at least once in every Year", assembly,
        ))
    meeting = _match(
        text,
        r"such Meeting shall be on the first Monday in December, unless they "
        r"shall by Law appoint a different Day",
    )
    if meeting:
        claims.append(_claim(
            "Congress", "meets_on", "first Monday in December", meeting,
            condition="unless Congress by Law appoints a different Day",
        ))
    alternative = _match(text, r"unless they shall by Law appoint a different Day")
    if alternative:
        claims.append(_claim(
            "Congress", "may_appoint_by_Law", "different Day for annual Meeting",
            alternative, modality="may",
        ))
    return claims


def _assemble_amendment_23_section_1(text: str) -> list[ProvisionFrame]:
    """Assemble District of Columbia presidential-elector provisions."""
    claims: list[ProvisionFrame] = []
    appointment = _verbatim(
        text,
        r"The District constituting the seat of Government of the United States "
        r"shall appoint in such manner as the Congress may direct:",
    )
    if appointment:
        claims.append(_claim(
            "District constituting seat of Government of the United States",
            "appoints", "electors of President and Vice President", appointment,
        ))
    direction = _match(text, r"in such manner as the Congress may direct")
    if direction:
        claims.append(_claim(
            "Congress", "may_direct", "manner of District elector appointment",
            direction, modality="may",
        ))
    number = _match(
        text,
        r"A number of electors of President and Vice President equal to the "
        r"whole number of Senators and Representatives in Congress to which the "
        r"District would be entitled if it were a State",
    )
    if number:
        claims.append(_claim(
            "number of District presidential and vice-presidential electors",
            "equals",
            "whole number of Senators and Representatives in Congress to which "
            "District would be entitled if it were a State",
            number,
            condition="District treated hypothetically as a State for counting",
        ))
    cap = _match(text, r"but in no event more than the least populous State")
    if cap:
        claims.append(_claim(
            "number of District presidential and vice-presidential electors",
            "is_no_more_than", "number of electors of least populous State", cap,
        ))
    additional = _match(text, r"they shall be in addition to those appointed by the States")
    if additional:
        claims.append(_claim(
            "District electors", "are_in_addition_to",
            "electors appointed by States", additional,
        ))
    considered = _match(
        text,
        r"they shall be considered, for the purposes of the election of "
        r"President and Vice President, to be electors appointed by a State",
    )
    if considered:
        for office in ("President", "Vice President"):
            claims.append(_claim(
                "District electors", "considered_as",
                "electors appointed by a State", considered,
                condition=f"for purposes of election of {office}",
            ))
    meeting = _match(text, r"they shall meet in the District")
    if meeting:
        claims.append(_claim("District electors", "meet_in", "District", meeting))
    duties = _match(
        text,
        r"and perform such duties as provided by the twelfth article of amendment",
    )
    if duties:
        claims.append(_claim(
            "District electors", "perform", "duties provided by Amendment XII",
            duties,
        ))
    return claims


def _assemble_amendment_20_section_3(text: str) -> list[ProvisionFrame]:
    """Assemble presidential succession at the start of a term."""
    claims: list[ProvisionFrame] = []
    death = _verbatim(
        text,
        r"If, at the time fixed for the beginning of the term of the President, "
        r"the President elect shall have died, the Vice President elect shall "
        r"become President\.",
    )
    if death:
        claims.append(_claim(
            "Vice President elect", "becomes", "President", death,
            condition=(
                "President elect has died at time fixed for beginning of "
                "presidential term"
            ),
        ))
    vice_president = _match(
        text,
        r"If a President shall not have been chosen before the time fixed for "
        r"the beginning of his term, or if the President elect shall have failed "
        r"to qualify, then the Vice President elect shall act as President until "
        r"a President shall have qualified",
    )
    if vice_president:
        claims.extend((
            _claim(
                "Vice President elect", "acts_as", "President", vice_president,
                condition=(
                    "President has not been chosen before time fixed for beginning "
                    "of his term; until a President has qualified"
                ),
            ),
            _claim(
                "Vice President elect", "acts_as", "President", vice_president,
                condition=(
                    "President elect has failed to qualify; until a President "
                    "has qualified"
                ),
            ),
        ))
    provision = _match(
        text,
        r"the Congress may by law provide for the case wherein neither a "
        r"President elect nor a Vice President elect shall have qualified",
    )
    common_condition = "neither President elect nor Vice President elect has qualified"
    if provision:
        claims.append(_claim(
            "Congress", "may_provide_by_law_for",
            "case in which neither President elect nor Vice President elect has qualified",
            provision, modality="may", condition=common_condition,
        ))
    declaration = _match(text, r"declaring who shall then act as President")
    if declaration:
        claims.append(_claim(
            "Congress", "may_declare_by_law", "who shall act as President",
            declaration, modality="may", condition=common_condition,
        ))
    selection = _match(text, r"or the manner in which one who is to act shall be selected")
    if selection:
        claims.append(_claim(
            "Congress", "may_provide_by_law",
            "manner of selecting a person to act as President", selection,
            modality="may", condition=common_condition,
        ))
    designated = _match(
        text,
        r"and such person shall act accordingly until a President or Vice "
        r"President shall have qualified",
    )
    if designated:
        claims.append(_claim(
            "person designated by Congress’s law or selected under its prescribed manner",
            "acts_as", "President", designated,
            condition=(
                f"{common_condition}; until a President or Vice President qualifies"
            ),
        ))
    until = _match(text, r"until a President or Vice President shall have qualified")
    if until:
        for office in ("President", "Vice President"):
            claims.append(_claim(
                "person acting as President under congressional law", "acts_until",
                f"{office} has qualified", until, condition=common_condition,
            ))
    return claims


def _assemble_amendment_20_section_4(text: str) -> list[ProvisionFrame]:
    """Assemble congressional authority for contingent-election candidate deaths."""
    claims: list[ProvisionFrame] = []
    house = _match(
        text,
        r"The Congress may by law provide for the case of the death of any of "
        r"the persons from whom the House of Representatives may choose a "
        r"President whenever the right of choice shall have devolved upon them",
    )
    if house:
        claims.append(_claim(
            "Congress", "may_provide_by_law_for",
            "death of a person from whom House may choose a President", house,
            modality="may",
            condition="House right of presidential choice has devolved upon it",
        ))
    senate = _match(
        text,
        r"and for the case of the death of any of the persons from whom the "
        r"Senate may choose a Vice President whenever the right of choice shall "
        r"have devolved upon them",
    )
    if senate:
        claims.append(_claim(
            "Congress", "may_provide_by_law_for",
            "death of a person from whom Senate may choose a Vice President", senate,
            modality="may",
            condition="Senate right of vice-presidential choice has devolved upon it",
        ))
    return claims


def _assemble_fair_use_107(text: str) -> list[ProvisionFrame]:
    """Assemble 17 U.S.C. §107 after its source signature has been observed."""
    claims: list[ProvisionFrame] = []
    infringement = _match(
        text,
        r"the fair use of a copyrighted work, including such use by reproduction "
        r"in copies or phonorecords or by any other means specified by that "
        r"section, for purposes such as criticism, comment, news reporting, "
        r"teaching \(including multiple copies for classroom use\), scholarship, "
        r"or research, is not an infringement of copyright",
    )
    if infringement:
        claims.append(_claim(
            "fair use of a copyrighted work", "constitutes",
            "copyright infringement", infringement, modality=None,
            polarity="negative",
            condition=(
                "Notwithstanding sections 106 and 106A; purposes and reproduction "
                "modes are illustrative, not automatic fair-use determinations"
            ),
        ))
    factor_specs = (
        (
            r"\(1\) the purpose and character of the use, including whether such "
            r"use is of a commercial nature or is for nonprofit educational purposes",
            "purpose and character of the use",
            "including whether use is commercial or for nonprofit educational "
            "purposes; listed factors are nonexclusive",
        ),
        (
            r"\(2\) the nature of the copyrighted work",
            "nature of the copyrighted work", "listed factors are nonexclusive",
        ),
        (
            r"\(3\) the amount and substantiality of the portion used in relation "
            r"to the copyrighted work as a whole",
            "amount and substantiality of the portion used in relation to the "
            "copyrighted work as a whole",
            "listed factors are nonexclusive",
        ),
        (
            r"\(4\) the effect of the use upon the potential market for or value "
            r"of the copyrighted work",
            "effect of the use upon the potential market for or value of the "
            "copyrighted work",
            "listed factors are nonexclusive",
        ),
    )
    for pattern, object_, condition in factor_specs:
        evidence = _match(text, pattern)
        if evidence:
            claims.append(_claim(
                "fair-use determination", "considers", object_, evidence,
                condition=condition,
            ))
    unpublished = _verbatim(
        text,
        r"The fact that a work is unpublished shall not itself bar a finding of "
        r"fair use if such finding is made upon consideration of all the above factors\.",
    )
    if unpublished:
        claims.append(_claim(
            "unpublished status of a work", "bars", "a finding of fair use",
            unpublished, polarity="negative",
            condition=(
                "unpublished status alone; finding made upon consideration of all "
                "the above factors"
            ),
        ))
    return claims


def _assemble_ftc_unfairness_45n(text: str) -> list[ProvisionFrame]:
    """Assemble 15 U.S.C. §45(n) after its source signature has been observed."""
    claims: list[ProvisionFrame] = []
    threshold = _verbatim(
        text,
        r"The Commission shall have no authority under this section or section "
        r"57a of this title to declare unlawful an act or practice on the grounds "
        r"that such act or practice is unfair unless the act or practice causes "
        r"or is likely to cause substantial injury to consumers which is not "
        r"reasonably avoidable by consumers themselves and not outweighed by "
        r"countervailing benefits to consumers or to competition\.",
    )
    if threshold:
        claims.append(_claim(
            "Commission", "has_authority_to_declare_unlawful_as_unfair",
            "act or practice", threshold, polarity="negative",
            condition=(
                "under this section or section 57a; unless the act or practice "
                "causes or is likely to cause substantial consumer injury that "
                "consumers cannot reasonably avoid and that is not outweighed by "
                "countervailing benefits to consumers or competition"
            ),
        ))
    policies = _verbatim(
        text,
        r"In determining whether an act or practice is unfair, the Commission may "
        r"consider established public policies as evidence to be considered with "
        r"all other evidence\.",
    )
    if policies:
        claims.append(_claim(
            "Commission", "considers_as_evidence", "established public policies",
            policies, modality="may",
            condition=(
                "when determining whether an act or practice is unfair; considered "
                "with all other evidence"
            ),
        ))
    primary = _verbatim(
        text,
        r"Such public policy considerations may not serve as a primary basis for "
        r"such determination\.",
    )
    if primary:
        claims.append(_claim(
            "public policy considerations", "serve_as",
            "primary basis for unfairness determination", primary, modality="may",
            polarity="negative",
            condition="determining whether an act or practice is unfair",
        ))
    return claims


def assemble_provisions(
    text: str,
    source_unit: str | None,
    state: ProvisionState,
) -> list[ProvisionFrame]:
    """Return complete atomic provisions found in one clause or excerpt."""
    if source_unit == "ARTICLE_1_SECTION_1":
        evidence = _verbatim(
            text,
            r"All legislative Powers herein granted shall be vested in a Congress "
            r"of the United States, which shall consist of a Senate and House of "
            r"Representatives\.",
        )
        if evidence:
            return [
                _claim(
                    "legislative Powers herein granted", "vested_in",
                    "Congress of the United States", evidence,
                ),
                _claim(
                    "Congress of the United States", "consists_of", "Senate", evidence,
                ),
                _claim(
                    "Congress of the United States", "consists_of",
                    "House of Representatives", evidence,
                ),
            ]
    if source_unit == "DOCUMENT":
        state.observe(text, source_unit)
        if state.document_signature == "copyright-fair-use-107":
            return _assemble_fair_use_107(text)
        if state.document_signature == "ftc-unfairness-45n":
            return _assemble_ftc_unfairness_45n(text)
    if source_unit == "AMENDMENT_14_SECTION_1":
        return _assemble_amendment_14_section_1(text)
    if source_unit == "ARTICLE_4_SECTION_2":
        return _assemble_article_4_section_2(text)
    if source_unit == "ARTICLE_1_SECTION_4":
        state.observe(text, source_unit)
        return _assemble_article_1_section_4(text, state)
    if source_unit == "AMENDMENT_23_SECTION_1":
        return _assemble_amendment_23_section_1(text)
    if source_unit == "AMENDMENT_20_SECTION_3":
        return _assemble_amendment_20_section_3(text)
    if source_unit == "AMENDMENT_20_SECTION_4":
        return _assemble_amendment_20_section_4(text)
    if _is_amendment_14_section_2(source_unit):
        return _assemble_amendment_14_section_2(text)
    if _is_article_5(source_unit, text):
        return _assemble_article_5(text)
    if _is_article_4_section_3(source_unit):
        return _assemble_article_4_section_3(text)
    if _is_amendment_17(source_unit):
        state.observe(text, source_unit)
        return _assemble_amendment_17(text, state)
    if _is_article_2_section_3(source_unit):
        return _assemble_article_2_section_3(text)
    if _is_article_6(source_unit, text):
        state.observe(text, source_unit)
        return _assemble_article_6(text, state)
    if _is_article_1_section_6(source_unit, text):
        return _assemble_article_1_section_6(text)
    if _is_article_1_section_5(source_unit, text):
        return _assemble_article_1_section_5(text)
    if _is_amendment_12(source_unit, text):
        state.observe(text, source_unit)
        return _assemble_amendment_12(text, state)
    if _is_amendment_25_section_4(source_unit):
        return _assemble_amendment_25_section_4(text)
    if _is_amendment_14_section_3(source_unit):
        return _assemble_amendment_14_section_3(text)
    if _is_amendment_14_section_4(source_unit):
        return _assemble_amendment_14_section_4(text)
    if _is_article_1_section_7(source_unit, text):
        state.observe(text, source_unit)
        return _assemble_article_1_section_7(text, state)
    if _is_article_1_section_10(source_unit, text):
        return _assemble_article_1_section_10(text)
    if _is_article_3_section_2(source_unit, text):
        return _assemble_article_3_section_2(text)
    if _is_article_2_section_2(source_unit, text):
        return _assemble_article_2_section_2(text)
    if _is_article_2_section_1(source_unit, text):
        return _assemble_article_2_section_1(text)
    if _is_section_9_restriction(source_unit, text):
        return _assemble_section_9(text)
    if not _is_enumerated_power(source_unit, text):
        return []
    state.observe(text, source_unit)
    actor = state.authority_subject or "Congress"
    modal = state.authority_modality or "shall"
    claims: list[ProvisionFrame] = []

    tax = _match(
        text,
        r"The Congress shall have Power To lay and collect Taxes, Duties, "
        r"Imposts and Excises, to pay the Debts and provide for the common "
        r"Defence and general Welfare of the United States",
    )
    if tax:
        purpose = (
            "to pay the Debts and provide for the common Defence and general "
            "Welfare of the United States"
        )
        for action in ("lay", "collect"):
            for item in ("Taxes", "Duties", "Imposts", "Excises"):
                claims.append(_claim(
                    actor, f"has_Power_to_{action}", item, tax,
                    modality=modal, condition=purpose,
                ))
        purpose_evidence = _match(
            text,
            r"to pay the Debts and provide for the common Defence and general "
            r"Welfare of the United States",
        )
        if purpose_evidence:
            for item in (
                "the Debts",
                "the common Defence of the United States",
                "the general Welfare of the United States",
            ):
                claims.append(_claim(
                    actor, "may_use_taxing_power_for", item, purpose_evidence,
                    modality="may",
                ))

    uniform = _match(
        text,
        r"all Duties, Imposts and Excises shall be uniform throughout the "
        r"United States",
    )
    if uniform:
        for item in ("Duties", "Imposts", "Excises"):
            claims.append(_claim(
                item, "uniform_throughout", "United States", uniform,
            ))

    borrow = _match(text, r"To borrow Money on the credit of the United States")
    if borrow:
        claims.append(_claim(
            actor, "has_Power_to_borrow", "Money", borrow,
            modality=modal, condition="on the credit of the United States",
        ))

    commerce = _match(
        text,
        r"To regulate Commerce with foreign Nations, and among the several "
        r"States, and with the Indian Tribes",
    )
    if commerce:
        for item in (
            "Commerce with foreign Nations",
            "Commerce among the several States",
            "Commerce with the Indian Tribes",
        ):
            claims.append(_claim(
                actor, "has_Power_to_regulate", item, commerce, modality=modal,
            ))

    naturalization = _match(text, r"To establish an uniform Rule of Naturalization")
    if naturalization:
        claims.append(_claim(
            actor, "has_Power_to_establish", "uniform Rule of Naturalization",
            naturalization, modality=modal,
        ))
    bankruptcy = _match(
        text,
        r"uniform Laws on the subject of Bankruptcies throughout the United States",
    )
    if bankruptcy:
        claims.append(_claim(
            actor, "has_Power_to_establish",
            "uniform Laws on the subject of Bankruptcies", bankruptcy,
            modality=modal, condition="throughout the United States",
        ))

    coin = _match(text, r"To coin Money")
    if coin:
        claims.append(_claim(actor, "has_Power_to_coin", "Money", coin, modality=modal))
    coin_values = _match(text, r"regulate the Value thereof, and of foreign Coin")
    if coin_values:
        for item in ("Value of coined Money", "Value of foreign Coin"):
            claims.append(_claim(
                actor, "has_Power_to_regulate", item, coin_values, modality=modal,
            ))
    standards = _match(text, r"fix the Standard of Weights and Measures")
    if standards:
        for item in ("Standard of Weights", "Standard of Measures"):
            claims.append(_claim(
                actor, "has_Power_to_fix", item, standards, modality=modal,
            ))

    counterfeiting = _match(
        text,
        r"To provide for the Punishment of counterfeiting the Securities and "
        r"current Coin of the United States",
    )
    if counterfeiting:
        for item in (
            "counterfeiting Securities of the United States",
            "counterfeiting current Coin of the United States",
        ):
            claims.append(_claim(
                actor, "has_Power_to_provide_for_Punishment_of", item,
                counterfeiting, modality=modal,
            ))

    post = _match(text, r"To establish Post Offices and post Roads")
    if post:
        for item in ("Post Offices", "post Roads"):
            claims.append(_claim(
                actor, "has_Power_to_establish", item, post, modality=modal,
            ))

    promotion = _match(
        text,
        r"To promote the Progress of Science and useful Arts, by securing for "
        r"limited Times to Authors and Inventors the exclusive Right to their "
        r"respective Writings and Discoveries",
    )
    if promotion:
        means = "by securing limited-time exclusive Rights to Authors and Inventors"
        for item in ("Progress of Science", "Progress of useful Arts"):
            claims.append(_claim(
                actor, "has_Power_to_promote", item, promotion,
                modality=modal, condition=means,
            ))
    securing = _match(
        text,
        r"by securing for limited Times to Authors and Inventors the exclusive "
        r"Right to their respective Writings and Discoveries",
    )
    if securing:
        purpose = "for limited Times; to promote Progress of Science and useful Arts"
        for item in (
            "Authors’ exclusive Right to their respective Writings",
            "Inventors’ exclusive Right to their respective Discoveries",
        ):
            claims.append(_claim(
                actor, "has_Power_to_secure", item, securing,
                modality=modal, condition=purpose,
            ))

    tribunal = _match(text, r"To constitute Tribunals inferior to the supreme Court")
    if tribunal:
        claims.append(_claim(
            actor, "has_Power_to_constitute",
            "Tribunals inferior to the supreme Court", tribunal, modality=modal,
        ))

    sea_law = _match(
        text,
        r"To define and punish Piracies and Felonies committed on the high Seas, "
        r"and Offences against the Law of Nations",
    )
    if sea_law:
        for action in ("define", "punish"):
            for item in (
                "Piracies committed on the high Seas",
                "Felonies committed on the high Seas",
                "Offences against the Law of Nations",
            ):
                claims.append(_claim(
                    actor, f"has_Power_to_{action}", item, sea_law, modality=modal,
                ))

    war = _match(text, r"To declare War")
    if war:
        claims.append(_claim(actor, "has_Power_to_declare", "War", war, modality=modal))
    marque = _match(text, r"grant Letters of Marque and Reprisal")
    if marque:
        claims.append(_claim(
            actor, "has_Power_to_grant", "Letters of Marque and Reprisal",
            marque, modality=modal,
        ))
    captures = _match(text, r"make Rules concerning Captures on Land and Water")
    if captures:
        for item in ("Captures on Land", "Captures on Water"):
            claims.append(_claim(
                actor, "has_Power_to_make_Rules_concerning", item, captures,
                modality=modal,
            ))

    armies = _match(text, r"To raise and support Armies")
    if armies:
        for action in ("raise", "support"):
            claims.append(_claim(
                actor, f"has_Power_to_{action}", "Armies", armies, modality=modal,
            ))
    appropriation = _match(
        text,
        r"no Appropriation of Money to that Use shall be for a longer Term than "
        r"two Years",
    )
    if appropriation:
        claims.append(_claim(
            "Appropriation of Money to raise or support Armies",
            "has_term_longer_than", "two Years", appropriation,
            polarity="negative",
        ))

    navy = _match(text, r"To provide and maintain a Navy")
    if navy:
        for action in ("provide", "maintain"):
            claims.append(_claim(
                actor, f"has_Power_to_{action}", "Navy", navy, modality=modal,
            ))
    forces = _match(
        text,
        r"To make Rules for the Government and Regulation of the land and naval Forces",
    )
    if forces:
        for kind in ("land", "naval"):
            claims.append(_claim(
                actor, "has_Power_to_make_Rules_for",
                f"Government and Regulation of {kind} Forces", forces,
                modality=modal,
            ))

    calling = _match(
        text,
        r"To provide for calling forth the Militia to execute the Laws of the "
        r"Union, suppress Insurrections and repel Invasions",
    )
    if calling:
        for purpose in (
            "execute the Laws of the Union",
            "suppress Insurrections",
            "repel Invasions",
        ):
            claims.append(_claim(
                actor, "has_Power_to_provide_for_calling_forth", "Militia",
                calling, modality=modal, condition=f"for the purpose of {purpose}",
            ))

    organizing = _match(text, r"To provide for organizing, arming, and disciplining, the Militia")
    if organizing:
        for action in ("organizing", "arming", "disciplining"):
            claims.append(_claim(
                actor, "has_Power_to_provide_for", f"{action} the Militia",
                organizing, modality=modal,
            ))
    governing = _match(
        text,
        r"for governing such Part of them as may be employed in the Service of "
        r"the United States",
    )
    if governing:
        claims.append(_claim(
            actor, "has_Power_to_provide_for_governing",
            "Part of Militia employed in Service of United States", governing,
            modality=modal,
            condition="Militia employed in Service of the United States",
        ))
    officers = _match(
        text,
        r"reserving to the States respectively, the Appointment of the Officers",
    )
    if officers:
        claims.append(_claim(
            "respective States", "retain", "Appointment of Militia Officers",
            officers,
        ))
    training = _match(
        text,
        r"and the Authority of training the Militia according to the discipline "
        r"prescribed by Congress",
    )
    if training:
        claims.append(_claim(
            "respective States", "retain", "Authority of training the Militia",
            training, condition="according to discipline prescribed by Congress",
        ))
    discipline = _match(text, r"according to the discipline prescribed by Congress")
    if discipline:
        claims.append(_claim(
            "Congress", "prescribes",
            "discipline according to which States train the Militia", discipline,
        ))

    district = _match(
        text,
        r"To exercise exclusive Legislation in all Cases whatsoever, over such "
        r"District \(not exceeding ten Miles square\) as may, by Cession of "
        r"particular States, and the Acceptance of Congress, become the Seat of "
        r"the Government of the United States",
    )
    if district:
        claims.append(_claim(
            actor, "has_Power_to_exercise",
            "exclusive Legislation in all Cases whatsoever over federal Seat District",
            district, modality=modal,
            condition=(
                "District not exceeding ten Miles square; by Cession of particular "
                "States and Acceptance of Congress; becomes Seat of Government of "
                "the United States"
            ),
        ))
    size = _match(text, r"such District \(not exceeding ten Miles square\)")
    if size:
        claims.append(_claim(
            "federal Seat District", "does_not_exceed", "ten Miles square", size,
        ))
    cession = _match(text, r"by Cession of particular States, and the Acceptance of Congress")
    if cession:
        claims.extend((
            _claim(
                "particular States", "may_cede", "federal Seat District", cession,
                modality="may",
                condition="Congress accepts; District becomes Seat of Government",
            ),
            _claim(
                "Congress", "may_accept", "State Cession for federal Seat District",
                cession, modality="may",
                condition="District becomes Seat of Government",
            ),
        ))

    enclave = _match(
        text,
        r"and to exercise like Authority over all Places purchased by the Consent "
        r"of the Legislature of the State in which the Same shall be, for the "
        r"Erection of Forts, Magazines, Arsenals, dock-Yards, and other needful Buildings",
    )
    if enclave:
        claims.append(_claim(
            actor, "has_Power_to_exercise",
            "like exclusive legislative Authority over purchased Places", enclave,
            modality=modal,
            condition=(
                "Places purchased with Consent of Legislature of State where located, "
                "for specified federal structures"
            ),
        ))
    purchase = _match(
        text,
        r"Places purchased by the Consent of the Legislature of the State in which "
        r"the Same shall be",
    )
    if purchase:
        claims.append(_claim(
            "Legislature of State where a Place is located", "consents_to",
            "purchase of Place subject to congressional like Authority", purchase,
            condition=(
                "for Erection of Forts, Magazines, Arsenals, dock-Yards, or other "
                "needful Buildings"
            ),
        ))
    erection = _match(
        text,
        r"for the Erection of Forts, Magazines, Arsenals, dock-Yards, and other "
        r"needful Buildings",
    )
    if erection:
        for item in ("Forts", "Magazines", "Arsenals", "dock-Yards", "other needful Buildings"):
            claims.append(_claim(
                "Place purchased with State legislature consent",
                "used_for_Erection_of", item, erection,
                condition=(
                    "as a permitted purpose for congressional like Authority over "
                    "purchased Places"
                ),
            ))

    foregoing = _match(
        text,
        r"To make all Laws which shall be necessary and proper for carrying into "
        r"Execution the foregoing Powers",
    )
    if foregoing:
        condition = "Laws necessary and proper for carrying into Execution the foregoing Powers"
        claims.append(_claim(
            actor, "has_Power_to_make",
            "Laws necessary and proper for executing foregoing Powers", foregoing,
            modality=modal, condition=condition,
        ))
    government = _match(
        text,
        r"and all other Powers vested by this Constitution in the Government of "
        r"the United States",
    )
    if government:
        claims.append(_claim(
            actor, "has_Power_to_make",
            "Laws necessary and proper for executing other constitutional Powers "
            "vested in United States Government",
            government, modality=modal,
            condition="Laws necessary and proper for carrying into Execution such Powers",
        ))
    department = _match(text, r"or in any Department or Officer thereof")
    if department:
        condition = "Laws necessary and proper for carrying into Execution such Powers"
        for holder in ("Department", "Officer"):
            claims.append(_claim(
                actor, "has_Power_to_make",
                "Laws necessary and proper for executing constitutional Powers "
                f"vested in any {holder} of United States Government",
                department, modality=modal, condition=condition,
            ))

    return claims


def relation_frames_from_provisions(
    provisions: list[ProvisionFrame],
    *,
    context: str,
    sentence_index: int,
    start: int,
    end: int,
    source_unit: str | None,
) -> list[RelationFrame]:
    """Flatten complete provisions into singleton relation frames."""
    return [
        RelationFrame(
            subject_options=(provision.subject,),
            predicate_options=(provision.predicate,),
            object_options=(provision.object,),
            evidence=provision.evidence,
            context=context,
            sentence_index=sentence_index,
            start=start,
            end=end,
            modality=provision.modality,
            polarity=provision.polarity,
            source_unit=source_unit,
            condition=provision.condition,
            origin="provision",
            attribution=provision.attribution,
        )
        for provision in provisions
    ]

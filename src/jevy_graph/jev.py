from __future__ import annotations

import http.client
import json
import math
import random
import re
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from functools import lru_cache
from threading import Lock, local
from typing import TypeVar
from urllib.parse import urlsplit

from .models import CandidateTriple, GraphIntent, RelationFrame, VerifiedTriple
from .normalize import canonical_entity, canonical_label, graphable_node, object_kind

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
# Conservative transport budget, not a token estimate. Oversized questions are
# handled by the API; multi-question batches split without dropping candidates.
MAX_REQUEST_BYTES = 120_000
T = TypeVar("T")
R = TypeVar("R")


class JevError(RuntimeError):
    pass


@dataclass
class Usage:
    requests: int = 0
    retries: int = 0
    request_bytes: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    """Independent quality scores for one selected graph claim."""

    candidate: CandidateTriple
    support: float
    boundaries: float
    qualifiers: float
    atomicity: float

    def passes(
        self,
        *,
        support: float = 0.5,
        boundaries: float = 0.5,
        qualifiers: float = 0.5,
        atomicity: float = 0.5,
    ) -> bool:
        """Return whether every independent quality floor is met."""
        return (
            self.support >= support
            and self.boundaries >= boundaries
            and self.qualifiers >= qualifiers
            and self.atomicity >= atomicity
        )

    def scores(self) -> dict[str, float]:
        """Return the score mapping used by benchmark scripts."""
        return {
            "support": self.support,
            "boundaries": self.boundaries,
            "qualifiers": self.qualifiers,
            "atomicity": self.atomicity,
        }


def _request_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _http_error_message(status: int) -> str:
    if status == 402:
        return "Jev has no available credits. Add credits in the TypeSafe console, then retry."
    return f"Jev request failed with HTTP {status}"


def _candidate(frame: RelationFrame, triple: tuple[str, str, str]) -> CandidateTriple:
    subject, predicate, object_ = triple
    return CandidateTriple(
        subject=subject,
        predicate=predicate,
        object=object_,
        evidence=frame.evidence,
        sentence_index=frame.sentence_index,
        start=frame.start,
        end=frame.end,
        modality=frame.modality,
        polarity=frame.polarity,
        object_kind=object_kind(object_),
        source_unit=frame.source_unit,
        source_locator=frame.source_locator,
        source_page=frame.source_page,
        condition=frame.condition,
        origin=frame.origin,
        context=frame.context,
        attribution=frame.attribution,
        claim_type=frame.claim_type,
        comparison=frame.comparison,
        conditions=frame.conditions,
        measurements=frame.measurements,
    )


def _normalize_components(
    subject: str, predicate: str, object_: str
) -> tuple[str, str, str] | None:
    subject = canonical_entity(subject)
    subject = re.sub(
        r"\s+(?:do|does|did|can|could|will|would|shall|may|might|must|should|"
        r"has|have|had|is|are|was|were|be|been|being)$",
        "",
        subject,
        flags=re.I,
    )
    subject = re.sub(
        r"\s+(?:shall|must|may|might|can|could|will|would|should)\b.*$",
        "",
        subject,
        flags=re.I,
    )
    if predicate == "encoded_with":
        subject = re.sub(
            r"\s+(?:is|are|was|were)\s+encoded$", "", subject, flags=re.I
        )
    subject = re.sub(r"^Model\s+The\s+", "", subject, flags=re.I)
    if predicate != "type" and re.search(
        r"\b(?:computes?|contained|containing|contains?|uses?|using|requires?|"
        r"produces?|provides?|employs?|encoded)\b",
        subject,
        re.I,
    ):
        return None
    if re.match(
        r"^(?:at\s+least|of\s+whom|in\s+a\s+manner|between|hereunto|"
        r"therein|thereof|whereof|if|unless)\b",
        subject,
        re.I,
    ):
        return None
    if re.fullmatch(
        r"(?:firstly|secondly|finally|however|moreover|therefore|their|them|"
        r"him|her|it|long|poor|whom\s+one\s+at\s+least)", subject, re.I
    ):
        return None
    if re.search(r"\b[A-Z]\)\s+\S", subject):
        return None

    raw_object = canonical_label(object_)
    # Universal quantifiers change the claim: a list of all people voted for
    # is not merely a list of some people voted for. Generic node
    # canonicalization drops these words, so restore them in offered triples.
    object_quantifier = re.match(r"(?i)^(all|each|every)\s+", raw_object)
    object_ = canonical_entity(object_)
    object_ = re.sub(
        r"\s*\((?:Supplementary\s+)?(?:Figure|Fig\.?|Table)\s+[^)]*\)?$",
        "", object_, flags=re.I,
    ).strip()
    if predicate in {"has", "possesses"} and re.match(
        r"^(?:(?:the\s+)?sole\s+)?power\s+to\s+", raw_object, re.I
    ):
        predicate = "authorized_to"
    if predicate == "authorized_to":
        object_ = re.sub(
            r"^(?:(?:the\s+)?sole\s+)?power\s+to\s+", "", object_, flags=re.I
        )
        object_ = re.sub(r"^to\s+", "", object_, flags=re.I)
    elif predicate == "used_with":
        object_ = re.sub(
            r"^(?:(?:in\s+)?conjunction\s+with|with)\s+", "", object_, flags=re.I
        )
    elif predicate == "used_for":
        object_ = re.sub(
            r"^(?:successfully\s+)?(?:in|for)\s+", "", object_, flags=re.I
        )
    object_ = canonical_entity(object_)
    if object_quantifier and not re.match(r"(?i)^(all|each|every)\s+", object_):
        object_ = f"{object_quantifier.group(1)} {object_}"

    if predicate == "authorized_to" and object_.casefold() in {"power", "sole power"}:
        return None
    if predicate in {"has", "possesses"} and re.match(
        r"^(?:to|been|become)\b", object_, re.I
    ):
        return None
    if not subject or not object_:
        return None
    if len(predicate) < 3 or predicate in {
        "gunn", "jared", "cod", "non_cod", "significantly", "differentiated",
    }:
        return None
    if not graphable_node(subject) or not graphable_node(object_):
        return None
    return subject, predicate, object_


def _ranked_indexes(sizes: tuple[int, int, int]) -> Iterator[tuple[int, int, int]]:
    """Visit the original (sum, max, tuple) order without sorting the full product."""
    if not all(sizes):
        return
    for total in range(sum(sizes) - 2):
        shell = []
        for subject in range(
            max(0, total - sizes[1] - sizes[2] + 2), min(sizes[0], total + 1)
        ):
            for predicate in range(
                max(0, total - subject - sizes[2] + 1),
                min(sizes[1], total - subject + 1),
            ):
                object_ = total - subject - predicate
                shell.append((subject, predicate, object_))
        yield from sorted(shell, key=lambda item: (max(item), item))


@lru_cache(maxsize=4_096)
def _triple_options(
    frame: RelationFrame, limit: int = 32
) -> tuple[tuple[str, str, str], ...]:
    ranked = _ranked_indexes(
        (
            len(frame.subject_options),
            len(frame.predicate_options),
            len(frame.object_options),
        )
    )
    options: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    has_power_to = any(
        re.match(
            r"^(?:(?:the\s+)?sole\s+)?power\s+to\s+",
            canonical_label(value),
            re.I,
        )
        for value in frame.object_options
    )
    action_prefix = canonical_label(frame.object_options[0]).split()[0].casefold()
    passive_with = bool(
        re.search(
            r"\b(?:is|are|was|were|be|been|being)\s+used\s+"
            r"(?:(?:in\s+)?conjunction\s+with|with)\b",
            frame.evidence,
            re.I,
        )
    )
    passive_for = bool(
        re.search(
            r"\b(?:is|are|was|were|has\s+been|have\s+been|had\s+been)\s+used\s+"
            r"(?:successfully\s+)?(?:in(?!\s+conjunction\b)|for)\b",
            frame.evidence,
            re.I,
        )
    )
    encoded_using = bool(
        re.search(
            r"\b(?:is|are|was|were)\s+encoded\s+using\b", frame.evidence, re.I
        )
    )
    for subject_index, predicate_index, object_index in ranked:
        predicate = frame.predicate_options[predicate_index]
        raw_object = canonical_label(frame.object_options[object_index])
        is_with_complement = bool(
            re.match(r"^(?:(?:in\s+)?conjunction\s+with|with)\s+", raw_object, re.I)
        )
        if has_power_to and predicate in {"has", "possesses"}:
            continue
        if predicate in {"authorized_to", "has_right_to"} and (
            not raw_object.split()
            or raw_object.split()[0].casefold() != action_prefix
        ):
            continue
        if encoded_using and predicate != "encoded_with":
            continue
        if not encoded_using and predicate == "encoded_with":
            continue
        if passive_for and predicate != "used_for":
            continue
        if not passive_for and predicate == "used_for":
            continue
        if passive_with and predicate != "used_with":
            continue
        if predicate == "used_with" and not is_with_complement:
            continue
        if predicate in {"uses", "applies"} and is_with_complement:
            continue
        normalized = _normalize_components(
            frame.subject_options[subject_index],
            predicate,
            frame.object_options[object_index],
        )
        if normalized is None:
            continue
        key = tuple(value.casefold() for value in normalized)
        if key in seen:
            continue
        seen.add(key)
        options.append(normalized)
        if len(options) == limit:
            break
    return tuple(options)


def build_choice_request(
    frames: list[RelationFrame], *, compact: bool = False, allow_reject: bool = False
) -> dict[str, object]:
    choice_policy = (
        "Which complete RDF triple most precisely captures the relation signaled "
        "by the evidence? Legal, normative, hypothetical, and scientific modal "
        "statements are valid assertions when their modality and polarity are "
        "preserved separately. Prefer exact, self-contained entity boundaries. "
        "Use type only for class membership and equivalent_to for definitions, "
        "symbols, quantities, or two names for the same thing. "
        + (
            "Choose none if every available triple has a wrong entity boundary, "
            "predicate, or meaning. Do not force an invalid triple. "
            if allow_reject else ""
        )
        + "A separate verification pass will reject unsupported triples."
    )
    questions: dict[str, object] = {}
    for index, frame in enumerate(frames):
        criteria: dict[str, object] = {
            f"t{option_index}": {
                "subject": subject,
                "predicate": predicate,
                "object": object_,
            }
            for option_index, (subject, predicate, object_) in enumerate(
                _triple_options(frame)
            )
        }
        if allow_reject:
            criteria["reject"] = {"meaning": "No candidate is an accurate complete relation"}
        questions[f"f{index}_triple"] = {
            "type": "choice",
            "instructions": {
                "evidence": frame.evidence,
                **({"context": frame.context} if frame.context and frame.context != frame.evidence else {}),
                "modality": frame.modality or "unmodalized",
                "polarity": frame.polarity,
                **({"claim_type": frame.claim_type} if frame.claim_type else {}),
                **({"comparison": frame.comparison} if frame.comparison else {}),
                **({"conditions": frame.conditions} if frame.conditions else {}),
                **({"measurements": frame.measurements} if frame.measurements else {}),
                "question": (
                    "Choose the best complete triple using state.choice_policy."
                    if compact else choice_policy
                ),
            },
            "criteria": criteria,
        }
        if compact:
            fixed = {
                name: next(iter(values))
                for name in ("subject", "predicate", "object")
                if len(values := {triple[name] for key, triple in criteria.items() if key != "reject"}) == 1
            }
            if fixed:
                instructions = questions[f"f{index}_triple"]["instructions"]
                instructions["fixed_fields"] = fixed
                instructions["question"] += " Each candidate inherits these fixed fields."
                for key, triple in criteria.items():
                    if key == "reject":
                        continue
                    for name in fixed:
                        del triple[name]
    state = {
        "task": (
            "Select the best source-grounded RDF triple for every atomic relation "
            "frame. Do not perform support filtering in this pass."
        )
    }
    if compact:
        state["choice_policy"] = choice_policy
    return {
        "model": MODEL,
        "state": state,
        "questions": questions,
    }


def parse_choice_answers(
    frames: list[RelationFrame], response: dict[str, object]
) -> list[CandidateTriple | None]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")
    candidates: list[CandidateTriple | None] = []
    for index, frame in enumerate(frames):
        answer = answers.get(f"f{index}_triple")
        if not isinstance(answer, dict):
            raise JevError(f"Jev omitted a choice for frame {index}")
        choice = answer.get("choice")
        if choice == "reject":
            candidates.append(None)
            continue
        if not isinstance(choice, str) or not choice.startswith("t"):
            raise JevError(f"Jev returned an invalid choice for frame {index}")
        try:
            subject, predicate, object_ = _triple_options(frame)[int(choice[1:])]
            confidence = float(answer["confidence"])
            probabilities = answer["probabilities"]
            if not isinstance(probabilities, dict):
                raise TypeError
            probability = float(probabilities[choice])
            if not all(math.isfinite(value) and 0 <= value <= 1 for value in (confidence, probability)):
                raise ValueError
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise JevError(f"Jev returned an unknown choice for frame {index}") from error
        candidates.append(
            replace(
                _candidate(frame, (subject, predicate, object_)),
                selection_confidence=confidence,
                selection_probability=probability,
            )
        )
    return candidates


_CLAIM_SLOTS = ("subject", "predicate", "object")


def _claim_slot_options(frame: RelationFrame) -> dict[str, tuple[str, ...]]:
    """Return de-duplicated slot menus that occur in a valid candidate triple."""
    triples = _triple_options(frame)
    return {
        slot: tuple(dict.fromkeys(triple[index] for triple in triples))
        for index, slot in enumerate(_CLAIM_SLOTS)
    }


def build_claim_slot_request(frames: list[RelationFrame]) -> dict[str, object]:
    """Ask Jev only about ambiguous fields of typed scientific claims.

    Singleton fields are deliberately absent from the request. They can be
    copied exactly without spending tokens. Every ambiguous field has an
    explicit ``none`` choice so a bad deterministic menu cannot force a claim.
    """
    questions: dict[str, object] = {}
    evidence_ids: dict[str, str] = {}
    evidence_by_id: dict[str, str] = {}

    def evidence_ref(value: str) -> str:
        if value not in evidence_ids:
            key = f"e{len(evidence_ids)}"
            evidence_ids[value] = key
            evidence_by_id[key] = value
        return evidence_ids[value]

    for frame_index, frame in enumerate(frames):
        menus = _claim_slot_options(frame)
        fixed = {
            slot: values[0] for slot, values in menus.items() if len(values) == 1
        }
        for slot, values in menus.items():
            if len(values) <= 1:
                continue
            criteria = {
                f"v{option_index}": value
                for option_index, value in enumerate(values)
            }
            criteria["none"] = "No offered span accurately fills this claim slot"
            questions[f"f{frame_index}_{slot}"] = {
                "type": "choice",
                "instructions": {
                    "evidence_ref": evidence_ref(frame.evidence),
                    "claim_type": frame.claim_type,
                    "fixed_slots": fixed,
                    **({"comparison": frame.comparison} if frame.comparison else {}),
                    **({"conditions": frame.conditions} if frame.conditions else {}),
                    **({"measurements": frame.measurements} if frame.measurements else {}),
                    "question": (
                        f"Which offered source-grounded value fills the {slot} slot? "
                        "Choose none when every option is wrong or incomplete."
                    ),
                },
                "criteria": criteria,
            }
    return {
        "model": MODEL,
        "state": {
            "task": (
                "Fill only ambiguous slots in typed atomic scientific claims. "
                "Keep qualifiers separate and do not infer facts absent from the evidence."
            ),
            "evidence_by_id": evidence_by_id,
        },
        "questions": questions,
    }


def parse_claim_slot_answers(
    frames: list[RelationFrame], response: dict[str, object]
) -> list[CandidateTriple | None]:
    """Assemble typed claims from fixed fields and Jev's ambiguous slot choices."""
    answers = response.get("answers", {})
    if not isinstance(answers, dict):
        raise JevError("Jev slot response did not contain an answers object")
    resolved: list[CandidateTriple | None] = []
    for frame_index, frame in enumerate(frames):
        menus = _claim_slot_options(frame)
        if any(not values for values in menus.values()):
            resolved.append(None)
            continue
        selected: dict[str, str] = {}
        confidences: list[float] = []
        probabilities: list[float] = []
        rejected = False
        for slot, values in menus.items():
            if len(values) == 1:
                selected[slot] = values[0]
                continue
            answer = answers.get(f"f{frame_index}_{slot}")
            if not isinstance(answer, dict):
                raise JevError(
                    f"Jev omitted the {slot} slot for scientific frame {frame_index}"
                )
            choice = answer.get("choice")
            if choice == "none":
                rejected = True
                break
            if not isinstance(choice, str) or not choice.startswith("v"):
                raise JevError(
                    f"Jev returned an invalid {slot} slot for scientific frame {frame_index}"
                )
            try:
                value = values[int(choice[1:])]
                confidence = float(answer["confidence"])
                probability_map = answer["probabilities"]
                if not isinstance(probability_map, dict):
                    raise TypeError
                probability = float(probability_map[choice])
                if not all(
                    math.isfinite(score) and 0 <= score <= 1
                    for score in (confidence, probability)
                ):
                    raise ValueError
            except (IndexError, KeyError, TypeError, ValueError) as error:
                raise JevError(
                    f"Jev returned an unknown {slot} slot for scientific frame {frame_index}"
                ) from error
            selected[slot] = value
            confidences.append(confidence)
            probabilities.append(probability)
        if rejected:
            resolved.append(None)
            continue
        normalized = _normalize_components(
            selected["subject"], selected["predicate"], selected["object"]
        )
        if normalized is None:
            resolved.append(None)
            continue
        resolved.append(replace(
            _candidate(frame, normalized),
            selection_confidence=min(confidences, default=1.0),
            selection_probability=min(probabilities, default=1.0),
        ))
    return resolved


def build_intent_request(instruction: str) -> dict[str, object]:
    return {
        "model": MODEL,
        "state": {"user_instruction": instruction},
        "questions": {
            "organization": {
                "type": "choice",
                "instructions": {
                    "question": (
                        "How does the user ask to organize the graph? Choose none when "
                        "the instruction only filters content. Choose unsupported when "
                        "it requests a grouping other than the three offered modes."
                    )
                },
                "criteria": {
                    "none": {"meaning": "No organization requested"},
                    "source": {"meaning": "Group by source article, section, or document unit"},
                    "entity": {"meaning": "Group by subject actor or entity"},
                    "relation": {"meaning": "Group by relation or predicate type"},
                    "unsupported": {"meaning": "A different organization was requested"},
                },
            }
        },
    }


def parse_intent_answer(instruction: str, response: dict[str, object]) -> GraphIntent:
    answers = response.get("answers")
    answer = answers.get("organization") if isinstance(answers, dict) else None
    choice = answer.get("choice") if isinstance(answer, dict) else None
    if choice not in {"none", "source", "entity", "relation", "unsupported"}:
        raise JevError("Jev returned an invalid graph organization choice")
    if choice == "unsupported":
        raise ValueError(
            "This organization is not supported. Ask to group by source section, "
            "subject entity, or relation type."
        )
    return GraphIntent(instruction, choice)


def build_verification_request(
    candidates: list[CandidateTriple],
    *,
    instruction: str = "",
    compact_policies: bool = True,
) -> dict[str, object]:
    questions: dict[str, object] = {}
    evidence_ids: dict[str, str] = {}
    evidence_by_id: dict[str, str] = {}
    policy_ids: dict[str, str] = {}
    question_policies: dict[str, str] = {}

    def question_text(value: str) -> str:
        if not compact_policies:
            return value
        if value not in policy_ids:
            reference = f"p{len(policy_ids)}"
            policy_ids[value] = reference
            question_policies[reference] = value
        return f"Score this candidate using state.question_policies.{policy_ids[value]}."

    def evidence_ref(value: str) -> str:
        if value not in evidence_ids:
            reference = f"e{len(evidence_ids)}"
            evidence_ids[value] = reference
            evidence_by_id[reference] = value
        return evidence_ids[value]

    for index, candidate in enumerate(candidates):
        support_data = {
            "subject": candidate.subject,
            "predicate": candidate.predicate,
            "object": candidate.object,
            "evidence_ref": evidence_ref(candidate.evidence),
            "modality": candidate.modality or "unmodalized",
            "polarity": candidate.polarity,
        }
        if candidate.context and candidate.context != candidate.evidence:
            support_data["context_ref"] = evidence_ref(candidate.context)
        if candidate.condition:
            support_data["condition"] = candidate.condition
        if candidate.claim_type:
            support_data["claim_type"] = candidate.claim_type
        if candidate.comparison:
            support_data["comparison"] = candidate.comparison
        if candidate.conditions:
            support_data["conditions"] = candidate.conditions
        if candidate.measurements:
            support_data["measurements"] = candidate.measurements
        if candidate.attribution:
            support_data["attribution"] = candidate.attribution
        if candidate.polarity == "negative":
            support_question = (
                "Does the evidence explicitly deny, prohibit, or negate this exact "
                "subject-predicate-object relationship? Answer yes when phrases such as "
                "no, not, or never negate the relationship. The candidate intentionally "
                "records that negative assertion rather than claiming the positive triple."
            )
        elif candidate.origin == "table":
            support_question = (
                "Does the table row support this exact cell relationship when interpreted "
                "using the ordered headers and parsed-row context? The row identifier may "
                "name its explicit configuration cells. Blank cells inherit from the base "
                "row only when the caption explicitly says unlisted values are identical."
            )
        elif candidate.origin == "equation":
            support_question = (
                "Does the displayed equation or assignment explicitly equate this exact "
                "left-hand symbol with this value or expression?"
            )
        else:
            support_question = (
                "Does the evidence explicitly assert this exact relationship with the "
                "recorded modality? A law saying shall, may, or must is an explicit "
                "normative assertion, not a reason to reject it."
            )
        if candidate.predicate == "partially_inhibited":
            support_question += (
                " For a list joined by or, check whether the shared partial effect "
                "applies to this named intervention."
            )
        if candidate.condition:
            support_question += (
                " Judge the triple together with its condition. A conditional or "
                "quantified prohibition can support a negative claim under the stated "
                "condition without prohibiting the relation unconditionally. Check that "
                "the condition preserves the source's actor, limit, and exception."
            )
        if candidate.attribution:
            support_question += (
                " Check that the source attributes this relationship to the named prior "
                "study rather than presenting it as this paper's own finding."
            )
        questions[f"c{index}_support"] = {
            "type": "noul",
            "instructions": {
                "candidate": support_data,
                "question": question_text(support_question),
            },
        }
        questions[f"c{index}_entities"] = {
            "type": "noul",
            "instructions": {
                "candidate": {
                    "subject": candidate.subject,
                    "predicate": candidate.predicate,
                    "object": candidate.object,
                    "evidence_ref": evidence_ref(candidate.evidence),
                    "modality": candidate.modality or "unmodalized",
                    "polarity": candidate.polarity,
                    **({"condition": candidate.condition} if candidate.condition else {}),
                },
                "question": question_text(
                    "Are the subject and object precise, self-contained graph values rather "
                    "than headings, unresolved pronouns, relation-bearing clauses, or random "
                    "fragments? Quantities and actions are allowed as values."
                ),
            },
        }
        questions[f"c{index}_qualifiers"] = {
            "type": "noul",
            "instructions": {
                "candidate": support_data,
                "question": question_text(COMPLETENESS_POLICIES["qualifiers"]),
            },
        }
        questions[f"c{index}_atomicity"] = {
            "type": "noul",
            "instructions": {
                "candidate": support_data,
                "question": question_text(COMPLETENESS_POLICIES["atomicity"]),
            },
        }
        if instruction:
            scope_data = dict(support_data)
            if candidate.polarity == "negative":
                scope_data["claim_reading"] = (
                    "The source reports a negative finding: this relationship "
                    "did not hold. Judge the finding's topic, not its polarity."
                )
            elif candidate.predicate == "revealed" and re.search(
                r"\b(?:expression|knockdown|assay|experiment|modeling)\b",
                candidate.subject, re.I,
            ):
                scope_data["claim_reading"] = (
                    "This claim names the experiment that revealed the result. "
                    "The separate result claim carries the biological finding."
                )
            questions[f"c{index}_scope"] = {
                "type": "noul",
                "instructions": {
                    "user_instruction_ref": "state.user_instruction",
                    "candidate": scope_data,
                    "question": question_text(
                        "Should this claim appear under the user's instruction? "
                        "Biological entity properties and origins, associations, "
                        "functions, intervention outcomes including null results, "
                        "and hedged mechanisms are biological findings. An "
                        "explicit negative intervention outcome remains in scope "
                        "even when it names experimental expression of a variant. Routine "
                        "laboratory procedures, analytical methods, and cohort "
                        "bookkeeping are not biological findings. When a method is "
                        "the subject of a suggested or inferred result, exclude "
                        "the method-provenance claim but include its separate "
                        "hedged biological conclusion. An experiment revealing "
                        "a result is method provenance; include the separate "
                        "biological result. A statement that effects remain "
                        "poorly understood is a research gap, not a biological "
                        "function. Score method-provenance and research-gap "
                        "claims below 0.5 for a biology-only instruction. Grouping "
                        "instructions do not restrict which claims appear."
                    ),
                },
            }
    return {
        "model": MODEL,
        "state": {
            "task": (
                "Verify source-grounded RDF triples. Resolve each evidence_ref and "
                "context_ref against evidence_by_id before answering."
                + (" Resolve question policy references against question_policies."
                   if compact_policies else "")
            ),
            "evidence_by_id": evidence_by_id,
            **({"question_policies": question_policies} if compact_policies else {}),
            **({"user_instruction": instruction} if instruction else {}),
        },
        "questions": questions,
    }


def parse_verification_answers(
    candidates: list[CandidateTriple], response: dict[str, object], *, instruction: str = ""
) -> list[VerifiedTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")
    verified: list[VerifiedTriple] = []
    for index, candidate in enumerate(candidates):
        support_answer = answers.get(f"c{index}_support")
        entities_answer = answers.get(f"c{index}_entities")
        qualifiers_answer = answers.get(f"c{index}_qualifiers")
        atomicity_answer = answers.get(f"c{index}_atomicity")
        if not isinstance(support_answer, dict) or not isinstance(
            entities_answer, dict
        ) or not isinstance(qualifiers_answer, dict) or not isinstance(
            atomicity_answer, dict
        ):
            raise JevError(f"Jev omitted verification answers for candidate {index}")
        try:
            support = float(support_answer["noul"])
            entity_quality = float(entities_answer["noul"])
            qualifier_quality = float(qualifiers_answer["noul"])
            atomicity = float(atomicity_answer["noul"])
            scope_answer = answers.get(f"c{index}_scope") if instruction else None
            scope_relevance = float(scope_answer["noul"]) if instruction else 1.0
            if not all(
                math.isfinite(value) and 0 <= value <= 1
                for value in (
                    support, entity_quality, scope_relevance,
                    qualifier_quality, atomicity,
                )
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise JevError(
                f"Jev returned an invalid verification score for candidate {index}"
            ) from error
        verified.append(VerifiedTriple(
            candidate, support, entity_quality, scope_relevance,
            qualifier_quality, atomicity,
        ))
    return verified


COMPLETENESS_POLICIES = {
    "support": (
        "Does the source explicitly support this exact subject-predicate-object "
        "relationship with its recorded polarity and modality? A nearby sentence "
        "or a plausible inference is insufficient."
    ),
    "boundaries": (
        "Are subject and object precise, self-contained graph values? Answer no "
        "for unresolved pronouns, discourse prefixes, dangling prepositions, "
        "relation-bearing clauses, or an actor placed only in condition."
    ),
    "qualifiers": (
        "Does the claim record preserve every material condition, comparator, "
        "measurement, hedge, negation, mechanism, time point, and prior-study "
        "attribution stated in the source? Evidence text does not fill a missing field."
    ),
    "atomicity": (
        "Does the record express one atomic relationship? Answer no when distinct "
        "outcomes, experimental arms, cell-specific findings, or causal steps that "
        "need separate graph claims are bundled together."
    ),
}


def build_completeness_request(
    candidates: list[CandidateTriple], *, compact_policies: bool = True
) -> dict[str, object]:
    """Build a batched four-dimension audit for selected claim candidates."""
    questions: dict[str, object] = {}
    evidence_ids: dict[str, str] = {}
    evidence_by_id: dict[str, str] = {}

    def evidence_ref(value: str) -> str:
        if value not in evidence_ids:
            reference = f"e{len(evidence_ids)}"
            evidence_ids[value] = reference
            evidence_by_id[reference] = value
        return evidence_ids[value]

    for index, candidate in enumerate(candidates):
        claim = {
            "subject": candidate.subject,
            "predicate": candidate.predicate,
            "object": candidate.object,
            "polarity": candidate.polarity,
            "modality": candidate.modality or "unmodalized",
            "evidence_ref": evidence_ref(candidate.evidence),
            **({"condition": candidate.condition} if candidate.condition else {}),
            **({"attribution": candidate.attribution} if candidate.attribution else {}),
            **({"claim_type": candidate.claim_type} if candidate.claim_type else {}),
            **({"comparison": candidate.comparison} if candidate.comparison else {}),
            **({"conditions": candidate.conditions} if candidate.conditions else {}),
            **({"measurements": candidate.measurements} if candidate.measurements else {}),
        }
        if candidate.context and candidate.context != candidate.evidence:
            claim["context_ref"] = evidence_ref(candidate.context)
        for dimension, policy in COMPLETENESS_POLICIES.items():
            questions[f"c{index}_{dimension}"] = {
                "type": "noul",
                "instructions": {
                    "claim": claim,
                    "question": (
                        f"Score this claim using state.dimension_policies.{dimension}."
                        if compact_policies
                        else policy
                    ),
                },
            }

    return {
        "model": MODEL,
        "state": {
            "task": (
                "Audit selected source-grounded graph claims. Score every dimension "
                "independently and resolve evidence_ref and context_ref using evidence_by_id."
            ),
            "evidence_by_id": evidence_by_id,
            **({"dimension_policies": COMPLETENESS_POLICIES} if compact_policies else {}),
        },
        "questions": questions,
    }


def parse_completeness_answers(
    candidates: list[CandidateTriple], response: dict[str, object]
) -> list[ClaimAssessment]:
    """Parse a completeness response without combining independent dimensions."""
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev completeness audit omitted answers")

    assessments: list[ClaimAssessment] = []
    for index, candidate in enumerate(candidates):
        scores: dict[str, float] = {}
        for dimension in COMPLETENESS_POLICIES:
            answer = answers.get(f"c{index}_{dimension}")
            if not isinstance(answer, dict):
                raise JevError(
                    f"Jev completeness audit omitted {dimension} for candidate {index}"
                )
            try:
                score = float(answer["noul"])
            except (KeyError, TypeError, ValueError) as error:
                raise JevError(
                    f"Jev completeness audit returned an invalid {dimension} score "
                    f"for candidate {index}"
                ) from error
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise JevError(
                    f"Jev completeness {dimension} score is out of range for "
                    f"candidate {index}"
                )
            scores[dimension] = score
        assessments.append(ClaimAssessment(candidate=candidate, **scores))
    return assessments


def _batches(items: list[T], size: int) -> list[list[T]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def _parallel_batches(
    batches: list[list[T]],
    worker: Callable[[list[T]], list[R]],
    max_workers: int,
) -> list[R]:
    if not batches:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(batches))) as executor:
        results = list(executor.map(worker, batches))
    return [item for batch in results for item in batch]


class JevClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 30.0,
        choice_batch_size: int = 24,
        verification_batch_size: int = 40,
        max_workers: int = 12,
        attempts: int = 6,
        compact: bool = True,
        compact_verification: bool = True,
        allow_reject: bool = False,
        requests_per_second: float = 24.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if min(choice_batch_size, verification_batch_size, max_workers, attempts) < 1:
            raise ValueError("batch sizes, workers, and attempts must be positive")
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.api_key = api_key
        self.timeout = timeout
        self.choice_batch_size = choice_batch_size
        self.verification_batch_size = verification_batch_size
        self.max_workers = max_workers
        self.attempts = attempts
        self.compact = compact
        self.compact_verification = compact_verification
        self.allow_reject = allow_reject
        self.singleton_selections = 0
        self.selection_rejections: list[RelationFrame] = []
        self.usage = Usage()
        self._stats_lock = Lock()
        self._connections = local()
        self.rate_limit_detail = None
        self._request_interval = 1.0 / requests_per_second
        self._next_request_at = 0.0

    def _wait_for_request(self) -> None:
        """Space requests across workers instead of bursting into rate limits."""
        while True:
            with self._stats_lock:
                now = time.monotonic()
                delay = self._next_request_at - now
                if delay <= 0:
                    self._next_request_at = now + self._request_interval
                    return
            time.sleep(delay)

    def resolve(self, frames: list[RelationFrame]) -> list[CandidateTriple]:
        candidates, singleton_count = self._resolve_frames(frames)
        self.singleton_selections += singleton_count
        return candidates

    def interpret_instruction(self, instruction: str) -> GraphIntent:
        instruction = instruction.strip()
        if not instruction:
            return GraphIntent()
        return parse_intent_answer(instruction, self._post(build_intent_request(instruction)))

    def _resolve_frames(
        self, frames: list[RelationFrame]
    ) -> tuple[list[CandidateTriple], int]:
        resolved: dict[int, CandidateTriple] = {}
        pending_indexes: list[int] = []
        pending_frames: list[RelationFrame] = []
        slot_indexes: list[int] = []
        slot_frames: list[RelationFrame] = []
        eligible_index = 0
        singleton_count = 0
        for frame in frames:
            options = _triple_options(frame)
            if not options:
                continue
            if len(options) == 1:
                resolved[eligible_index] = _candidate(frame, options[0])
                singleton_count += 1
            elif frame.claim_type:
                slot_indexes.append(eligible_index)
                slot_frames.append(frame)
            else:
                pending_indexes.append(eligible_index)
                pending_frames.append(frame)
            eligible_index += 1

        batches = _batches(pending_frames, self.choice_batch_size)
        selected = (
            self._resolve_batch(batches[0])
            if len(batches) == 1
            else _parallel_batches(batches, self._resolve_batch, self.max_workers)
        )
        for index, candidate in zip(pending_indexes, selected, strict=True):
            if candidate is not None:
                resolved[index] = candidate
        slot_batches = _batches(slot_frames, self.choice_batch_size)
        slot_selected = (
            self._resolve_claim_slot_batch(slot_batches[0])
            if len(slot_batches) == 1
            else _parallel_batches(
                slot_batches, self._resolve_claim_slot_batch, self.max_workers
            )
        )
        for index, candidate in zip(slot_indexes, slot_selected, strict=True):
            if candidate is not None:
                resolved[index] = candidate
        rejected = [
            frame for frame, candidate in zip(pending_frames, selected, strict=True)
            if candidate is None
        ]
        rejected.extend(
            frame for frame, candidate in zip(slot_frames, slot_selected, strict=True)
            if candidate is None
        )
        if rejected:
            with self._stats_lock:
                self.selection_rejections.extend(rejected)
        return [resolved[index] for index in range(eligible_index) if index in resolved], singleton_count

    def verify(self, candidates: list[CandidateTriple], *, instruction: str = "") -> list[VerifiedTriple]:
        return _parallel_batches(
            _batches(candidates, self.verification_batch_size),
            (lambda batch: self._verify_batch(batch, instruction=instruction)) if instruction else self._verify_batch,
            self.max_workers,
        )

    def assess_claims(
        self, candidates: list[CandidateTriple]
    ) -> list[ClaimAssessment]:
        """Audit every selected candidate on four independent quality dimensions."""
        return _parallel_batches(
            _batches(candidates, self.verification_batch_size),
            self._assess_claim_batch,
            self.max_workers,
        )

    def assess_completeness(
        self, candidates: list[CandidateTriple]
    ) -> list[dict[str, float]]:
        """Return score dictionaries for benchmark reports."""
        return [assessment.scores() for assessment in self.assess_claims(candidates)]

    def score(self, frames: list[RelationFrame], *, instruction: str = "") -> list[VerifiedTriple]:
        batches = sorted(self._iter_scored_batches(frames, instruction=instruction), key=lambda item: item[0])
        return [item for _, batch in batches for item in batch]

    def iter_score_batches(
        self, frames: list[RelationFrame], *, instruction: str = ""
    ) -> Iterator[list[VerifiedTriple]]:
        """Yield independently verified frame batches as they actually complete."""
        for _, batch in self._iter_scored_batches(frames, instruction=instruction):
            if batch:
                yield batch

    def _iter_scored_batches(
        self, frames: list[RelationFrame], *, instruction: str = ""
    ) -> Iterator[tuple[int, list[VerifiedTriple]]]:
        batches = iter(enumerate(_batches(frames, self.choice_batch_size)))
        if not frames:
            return
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        pending = {}
        worker = (
            (lambda batch: self._score_frame_batch(batch, instruction=instruction))
            if instruction else self._score_frame_batch
        )
        try:
            for index, batch in batches:
                pending[executor.submit(worker, batch)] = index
                if len(pending) == self.max_workers:
                    break
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                # Observe failures before scheduling more paid requests.
                completed = [
                    (pending.pop(future), future.result()) for future in done
                ]
                for index, verified in completed:
                    yield index, verified
                    next_batch = next(batches, None)
                    if next_batch is not None:
                        next_index, batch = next_batch
                        future = executor.submit(worker, batch)
                        pending[future] = next_index
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    def _score_frame_batch(
        self, frames: list[RelationFrame], *, instruction: str = ""
    ) -> list[VerifiedTriple]:
        candidates, singleton_count = self._resolve_frames(frames)
        if singleton_count:
            with self._stats_lock:
                self.singleton_selections += singleton_count
        verified: list[VerifiedTriple] = []
        for batch in _batches(candidates, self.verification_batch_size):
            verified.extend(
                self._verify_batch(batch, instruction=instruction)
                if instruction else self._verify_batch(batch)
            )
        return verified

    def _resolve_batch(self, frames: list[RelationFrame]) -> list[CandidateTriple | None]:
        payload = build_choice_request(
            frames, compact=self.compact, allow_reject=self.allow_reject
        )
        if len(frames) > 1 and len(_request_body(payload)) > MAX_REQUEST_BYTES:
            return [
                candidate
                for batch in _batches(frames, (len(frames) + 1) // 2)
                for candidate in self._resolve_batch(batch)
            ]
        return parse_choice_answers(frames, self._post(payload))

    def _resolve_claim_slot_batch(
        self, frames: list[RelationFrame]
    ) -> list[CandidateTriple | None]:
        payload = build_claim_slot_request(frames)
        if len(frames) > 1 and len(_request_body(payload)) > MAX_REQUEST_BYTES:
            return [
                candidate
                for batch in _batches(frames, (len(frames) + 1) // 2)
                for candidate in self._resolve_claim_slot_batch(batch)
            ]
        return parse_claim_slot_answers(frames, self._post(payload))

    def _verify_batch(
        self, candidates: list[CandidateTriple], *, instruction: str = ""
    ) -> list[VerifiedTriple]:
        payload = build_verification_request(
            candidates, instruction=instruction,
            compact_policies=self.compact_verification,
        )
        if len(candidates) > 1 and len(_request_body(payload)) > MAX_REQUEST_BYTES:
            return [
                item
                for batch in _batches(candidates, (len(candidates) + 1) // 2)
                for item in self._verify_batch(batch, instruction=instruction)
            ]
        return parse_verification_answers(candidates, self._post(payload), instruction=instruction)

    def _assess_claim_batch(
        self, candidates: list[CandidateTriple]
    ) -> list[ClaimAssessment]:
        payload = build_completeness_request(
            candidates, compact_policies=self.compact_verification
        )
        if len(candidates) > 1 and len(_request_body(payload)) > MAX_REQUEST_BYTES:
            return [
                assessment
                for batch in _batches(candidates, (len(candidates) + 1) // 2)
                for assessment in self._assess_claim_batch(batch)
            ]
        return parse_completeness_answers(candidates, self._post(payload))

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        body = _request_body(payload)
        url = urlsplit(API_URL)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "jevy-graph/0.1",
        }
        for attempt in range(self.attempts):
            self._wait_for_request()
            with self._stats_lock:
                self.usage.requests += 1
                self.usage.retries += int(attempt > 0)
                self.usage.request_bytes += len(body)
            try:
                connection = getattr(self._connections, "connection", None)
                if connection is None:
                    connection = http.client.HTTPSConnection(
                        url.netloc, timeout=self.timeout
                    )
                    self._connections.connection = connection
                connection.request("POST", url.path, body, headers)
                response = connection.getresponse()
                data = response.read()
                if response.status != 200:
                    if response.status == 429:
                        try:
                            self.rate_limit_detail = json.loads(data).get("detail")
                        except (ValueError, AttributeError):
                            pass
                    if (
                        response.status not in {429, 529}
                        or attempt + 1 == self.attempts
                    ):
                        raise JevError(_http_error_message(response.status))
                    try:
                        retry_after = float(response.getheader("Retry-After", "0"))
                    except ValueError:
                        retry_after = 0.0
                else:
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise JevError("Jev returned a non-object response")
                    usage = result.get("usage", {})
                    with self._stats_lock:
                        self.usage.input_tokens += usage.get("input_tokens", 0)
                        self.usage.output_tokens += usage.get("output_tokens", 0)
                    return result
            except (OSError, http.client.HTTPException) as error:
                if connection is not None:
                    connection.close()
                self._connections.connection = None
                if attempt + 1 == self.attempts:
                    raise JevError(f"Could not reach Jev: {error}") from error
                retry_after = 0.0
            backoff = max(retry_after, min(8.0, 0.5 * (2**attempt)))
            with self._stats_lock:
                self._next_request_at = max(
                    self._next_request_at, time.monotonic() + backoff
                )
            time.sleep(backoff + random.uniform(0.0, backoff * 0.25))
        raise JevError("Jev request failed")

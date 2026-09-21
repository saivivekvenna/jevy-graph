from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict
from itertools import product
from typing import TypeVar

from .models import CandidateTriple, RelationFrame, VerifiedTriple
from .normalize import canonical_label

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
T = TypeVar("T")


class JevError(RuntimeError):
    pass


def _normalize_components(
    subject: str, predicate: str, object_: str
) -> tuple[str, str, str] | None:
    subject = canonical_label(subject)
    subject = re.sub(
        r"\s+(?:do|does|did|can|could|will|would|shall|may|might|must|should|"
        r"has|have|had|is|are|was|were|be|been|being)$",
        "",
        subject,
        flags=re.I,
    )
    object_ = canonical_label(object_)
    if predicate in {"has", "possesses"} and re.match(
        r"^(?:(?:the\s+)?sole\s+)?power\s+to\s+", object_, re.I
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
    object_ = canonical_label(object_)
    if predicate == "authorized_to" and object_.casefold() in {"power", "sole power"}:
        return None
    if not subject or not object_ or re.match(r"^(?:no|not|without)\b", object_, re.I):
        return None
    return subject, predicate, object_


def _triple_options(
    frame: RelationFrame, limit: int = 96
) -> tuple[tuple[str, str, str], ...]:
    indexes = product(
        range(len(frame.subject_options)),
        range(len(frame.predicate_options)),
        range(len(frame.object_options)),
    )
    ranked = sorted(indexes, key=lambda item: (sum(item), max(item), item))
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
    passive_with = bool(
        re.search(
            r"\b(?:is|are|was|were|be|been|being)\s+used\s+"
            r"(?:(?:in\s+)?conjunction\s+with|with)\b",
            frame.evidence,
            re.I,
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


def build_resolution_request(frames: list[RelationFrame]) -> dict[str, object]:
    questions: dict[str, object] = {}
    for index, frame in enumerate(frames):
        options = _triple_options(frame)
        criteria: dict[str, object] = {
            f"t{option_index}": {
                "subject": subject,
                "predicate": predicate,
                "object": object_,
            }
            for option_index, (subject, predicate, object_) in enumerate(options)
        }
        criteria["none"] = {
            "meaning": "No candidate triple is precisely and explicitly supported."
        }
        questions[f"f{index}_triple"] = {
            "type": "choice",
            "instructions": {
                "context": frame.context,
                "evidence": frame.evidence,
                "question": (
                    "Which complete subject-predicate-object triple most precisely captures "
                    "one relationship explicitly asserted by `evidence`? Select `none` if "
                    "every option has a wrong boundary, meaning, direction, or factual status."
                ),
            },
            "criteria": criteria,
        }
    return {
        "model": MODEL,
        "state": {"task": "Resolve deterministic knowledge graph candidate lattices."},
        "questions": questions,
    }


def _selected_triple(
    answer: object,
    options: tuple[tuple[str, str, str], ...],
    frame_index: int,
    minimum_confidence: float,
) -> tuple[tuple[str, str, str], float, float] | None:
    if not isinstance(answer, dict):
        raise JevError(f"Jev omitted a resolution answer for frame {frame_index}")
    choice = answer.get("choice")
    if choice == "none":
        return None
    if not isinstance(choice, str) or not choice.startswith("t"):
        raise JevError(f"Jev returned an invalid resolution answer for frame {frame_index}")
    try:
        selected = options[int(choice[1:])]
        confidence = float(answer["confidence"])
        probabilities = answer["probabilities"]
        if not isinstance(probabilities, dict):
            raise TypeError
        probability = float(probabilities[choice])
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise JevError(f"Jev returned an unknown option for frame {frame_index}") from error
    if confidence < minimum_confidence:
        return None
    return selected, confidence, probability


def parse_resolution_answers(
    frames: list[RelationFrame],
    response: dict[str, object],
    *,
    minimum_confidence: float = 0.0,
) -> list[CandidateTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")

    candidates: list[CandidateTriple] = []
    for index, frame in enumerate(frames):
        selected = _selected_triple(
            answers.get(f"f{index}_triple"),
            _triple_options(frame),
            index,
            minimum_confidence,
        )
        if selected is None:
            continue
        (subject, predicate, object_), confidence, probability = selected
        candidates.append(
            CandidateTriple(
                subject=subject,
                predicate=predicate,
                object=object_,
                evidence=frame.evidence,
                sentence_index=frame.sentence_index,
                start=frame.start,
                end=frame.end,
                resolution_confidence=confidence,
                resolution_probability=probability,
            )
        )
    return candidates


def build_request(candidates: list[CandidateTriple]) -> dict[str, object]:
    questions: dict[str, object] = {}
    for index, candidate in enumerate(candidates):
        candidate_data = asdict(candidate)
        questions[f"c{index}_support"] = {
            "type": "noul",
            "instructions": {
                "candidate": candidate_data,
                "question": (
                    "Does `evidence` explicitly state this exact subject-predicate-object "
                    "relationship without requiring an unstated inference?"
                ),
            },
            "criteria": {
                "true": "The evidence directly states or clearly entails this exact relationship.",
                "false": "The relationship is absent, merely associated, or needs unstated assumptions.",
            },
        }
        questions[f"c{index}_direction"] = {
            "type": "noul",
            "instructions": {
                "candidate": candidate_data,
                "question": (
                    "Does the candidate preserve the relationship direction in `evidence`, "
                    "with the source or actor as subject and its target or value as object?"
                ),
            },
            "criteria": {
                "true": "The subject and object occupy the correct semantic roles.",
                "false": "The roles are reversed, displaced, or attached to the wrong phrase.",
            },
        }
        questions[f"c{index}_factual"] = {
            "type": "noul",
            "instructions": {
                "candidate": candidate_data,
                "question": (
                    "Does `evidence` present this relationship as an actual claim rather than "
                    "negated, hypothetical, questioned, desired, or merely possible?"
                ),
            },
            "criteria": {
                "true": "The relationship is presented as an actual claim.",
                "false": "It is negated, hypothetical, conditional, questioned, desired, or only possible.",
            },
        }
        questions[f"c{index}_entities"] = {
            "type": "noul",
            "instructions": {
                "candidate": candidate_data,
                "question": (
                    "Are both candidate entities self-contained, meaningful knowledge-graph "
                    "nodes rather than pronouns, deictic labels, headings, fragments, or clauses?"
                ),
            },
            "criteria": {
                "true": "Both labels identify clear entities, concepts, quantities, or actions.",
                "false": "Either label is vague, referential, malformed, or not independently meaningful.",
            },
        }
    return {
        "model": MODEL,
        "state": {"task": "Verify source-grounded knowledge graph candidates."},
        "questions": questions,
    }


def parse_answers(
    candidates: list[CandidateTriple], response: dict[str, object]
) -> list[VerifiedTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")

    verified: list[VerifiedTriple] = []
    for index, candidate in enumerate(candidates):
        support_answer = answers.get(f"c{index}_support")
        direction_answer = answers.get(f"c{index}_direction")
        factual_answer = answers.get(f"c{index}_factual")
        entities_answer = answers.get(f"c{index}_entities")
        if not all(
            isinstance(answer, dict)
            for answer in (
                support_answer,
                direction_answer,
                factual_answer,
                entities_answer,
            )
        ):
            raise JevError(f"Jev response omitted answers for candidate {index}")
        try:
            support = float(support_answer["noul"])
            direction = float(direction_answer["noul"])
            factuality = float(factual_answer["noul"])
            entity_quality = float(entities_answer["noul"])
        except (KeyError, TypeError, ValueError) as error:
            raise JevError(f"Jev returned an invalid answer for candidate {index}") from error
        verified.append(
            VerifiedTriple(candidate, support, direction, factuality, entity_quality)
        )
    return verified


def _batches(items: list[T], size: int) -> Iterable[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class JevClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 30.0,
        batch_size: int = 20,
        resolution_batch_size: int = 5,
        resolution_confidence: float = 0.25,
        attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self.api_key = api_key
        self.timeout = timeout
        self.batch_size = batch_size
        self.resolution_batch_size = resolution_batch_size
        self.resolution_confidence = resolution_confidence
        self.attempts = attempts

    def verify(self, candidates: list[CandidateTriple]) -> list[VerifiedTriple]:
        verified: list[VerifiedTriple] = []
        for batch in _batches(candidates, self.batch_size):
            verified.extend(self._verify_batch(batch))
        return verified

    def resolve(self, frames: list[RelationFrame]) -> list[CandidateTriple]:
        candidates: list[CandidateTriple] = []
        for batch in _batches(frames, self.resolution_batch_size):
            payload = self._post(build_resolution_request(batch))
            candidates.extend(
                parse_resolution_answers(
                    batch,
                    payload,
                    minimum_confidence=self.resolution_confidence,
                )
            )
        return candidates

    def _verify_batch(self, candidates: list[CandidateTriple]) -> list[VerifiedTriple]:
        payload = self._post(build_request(candidates))
        return parse_answers(candidates, payload)

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "jevy-graph/0.1",
            },
            method="POST",
        )

        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    result = json.load(response)
                if not isinstance(result, dict):
                    raise JevError("Jev returned a non-object response")
                return result
            except urllib.error.HTTPError as error:
                if error.code not in {429, 529} or attempt + 1 == self.attempts:
                    raise JevError(f"Jev request failed with HTTP {error.code}") from error
            except urllib.error.URLError as error:
                if attempt + 1 == self.attempts:
                    raise JevError(f"Could not reach Jev: {error.reason}") from error
            time.sleep(0.25 * (2**attempt))

        raise JevError("Jev request failed")

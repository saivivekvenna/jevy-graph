from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from itertools import product
from typing import TypeVar

from .models import CandidateTriple, RelationFrame, VerifiedTriple
from .normalize import canonical_entity, canonical_label, object_kind

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
T = TypeVar("T")
R = TypeVar("R")


class JevError(RuntimeError):
    pass


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

    raw_object = canonical_label(object_)
    object_ = canonical_entity(object_)
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

    if predicate == "authorized_to" and object_.casefold() in {"power", "sole power"}:
        return None
    if predicate in {"has", "possesses"} and re.match(
        r"^(?:to|been|become)\b", object_, re.I
    ):
        return None
    if not subject or not object_:
        return None
    if len(predicate) < 3 or predicate in {"gunn", "jared"}:
        return None
    return subject, predicate, object_


def _triple_options(
    frame: RelationFrame, limit: int = 32
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


def build_choice_request(frames: list[RelationFrame]) -> dict[str, object]:
    questions: dict[str, object] = {}
    for index, frame in enumerate(frames):
        criteria: dict[str, object] = {
            f"t{option_index}": {
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "modality": frame.modality or "unmodalized",
                "polarity": frame.polarity,
            }
            for option_index, (subject, predicate, object_) in enumerate(
                _triple_options(frame)
            )
        }
        questions[f"f{index}_triple"] = {
            "type": "choice",
            "instructions": {
                "context": frame.context,
                "evidence": frame.evidence,
                "modality": frame.modality or "unmodalized",
                "polarity": frame.polarity,
                "question": (
                    "Which complete RDF triple most precisely captures the relation signaled "
                    "by the evidence? Legal, normative, hypothetical, and scientific modal "
                    "statements are valid assertions when their modality and polarity are "
                    "preserved separately. Prefer exact, self-contained entity boundaries. "
                    "Use type only for class membership and equivalent_to for definitions, "
                    "symbols, quantities, or two names for the same thing. "
                    "Choose the best available boundary and predicate combination. "
                    "A separate verification pass will reject unsupported triples."
                ),
            },
            "criteria": criteria,
        }
    return {
        "model": MODEL,
        "state": {
            "task": (
                "Select the best source-grounded RDF triple for every atomic relation "
                "frame. Do not perform support filtering in this pass."
            )
        },
        "questions": questions,
    }


def parse_choice_answers(
    frames: list[RelationFrame], response: dict[str, object]
) -> list[CandidateTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")
    candidates: list[CandidateTriple] = []
    for index, frame in enumerate(frames):
        answer = answers.get(f"f{index}_triple")
        if not isinstance(answer, dict):
            raise JevError(f"Jev omitted a choice for frame {index}")
        choice = answer.get("choice")
        if not isinstance(choice, str) or not choice.startswith("t"):
            raise JevError(f"Jev returned an invalid choice for frame {index}")
        try:
            subject, predicate, object_ = _triple_options(frame)[int(choice[1:])]
            confidence = float(answer["confidence"])
            probabilities = answer["probabilities"]
            if not isinstance(probabilities, dict):
                raise TypeError
            probability = float(probabilities[choice])
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


def build_verification_request(
    candidates: list[CandidateTriple],
) -> dict[str, object]:
    questions: dict[str, object] = {}
    for index, candidate in enumerate(candidates):
        candidate_data = asdict(candidate)
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
        questions[f"c{index}_support"] = {
            "type": "noul",
            "instructions": {
                "candidate": candidate_data,
                "question": support_question,
            },
        }
        questions[f"c{index}_entities"] = {
            "type": "noul",
            "instructions": {
                "candidate": candidate_data,
                "question": (
                    "Are the subject and object precise, self-contained graph values rather "
                    "than headings, unresolved pronouns, relation-bearing clauses, or random "
                    "fragments? Quantities and actions are allowed as values."
                ),
            },
        }
    return {
        "model": MODEL,
        "state": {"task": "Verify selected source-grounded RDF triples."},
        "questions": questions,
    }


def parse_verification_answers(
    candidates: list[CandidateTriple], response: dict[str, object]
) -> list[VerifiedTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")
    verified: list[VerifiedTriple] = []
    for index, candidate in enumerate(candidates):
        support_answer = answers.get(f"c{index}_support")
        entities_answer = answers.get(f"c{index}_entities")
        if not isinstance(support_answer, dict) or not isinstance(
            entities_answer, dict
        ):
            raise JevError(f"Jev omitted verification answers for candidate {index}")
        try:
            support = float(support_answer["noul"])
            entity_quality = float(entities_answer["noul"])
        except (KeyError, TypeError, ValueError) as error:
            raise JevError(
                f"Jev returned an invalid verification score for candidate {index}"
            ) from error
        verified.append(VerifiedTriple(candidate, support, entity_quality))
    return verified


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
        attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self.api_key = api_key
        self.timeout = timeout
        self.choice_batch_size = choice_batch_size
        self.verification_batch_size = verification_batch_size
        self.max_workers = max_workers
        self.attempts = attempts
        self.singleton_selections = 0

    def resolve(self, frames: list[RelationFrame]) -> list[CandidateTriple]:
        resolved: dict[int, CandidateTriple] = {}
        pending_indexes: list[int] = []
        pending_frames: list[RelationFrame] = []
        eligible_index = 0
        for frame in frames:
            options = _triple_options(frame)
            if not options:
                continue
            if len(options) == 1:
                resolved[eligible_index] = _candidate(frame, options[0])
                self.singleton_selections += 1
            else:
                pending_indexes.append(eligible_index)
                pending_frames.append(frame)
            eligible_index += 1

        selected = _parallel_batches(
            _batches(pending_frames, self.choice_batch_size),
            self._resolve_batch,
            self.max_workers,
        )
        for index, candidate in zip(pending_indexes, selected, strict=True):
            resolved[index] = candidate
        return [resolved[index] for index in range(eligible_index)]

    def verify(self, candidates: list[CandidateTriple]) -> list[VerifiedTriple]:
        return _parallel_batches(
            _batches(candidates, self.verification_batch_size),
            self._verify_batch,
            self.max_workers,
        )

    def score(self, frames: list[RelationFrame]) -> list[VerifiedTriple]:
        return self.verify(self.resolve(frames))

    def _resolve_batch(self, frames: list[RelationFrame]) -> list[CandidateTriple]:
        return parse_choice_answers(frames, self._post(build_choice_request(frames)))

    def _verify_batch(
        self, candidates: list[CandidateTriple]
    ) -> list[VerifiedTriple]:
        return parse_verification_answers(
            candidates, self._post(build_verification_request(candidates))
        )

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

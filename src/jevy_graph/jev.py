from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
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
    if predicate == "encoded_with":
        subject = re.sub(
            r"\s+(?:is|are|was|were)\s+encoded$", "", subject, flags=re.I
        )
    subject = re.sub(r"^Model\s+The\s+", "", subject, flags=re.I)
    if re.search(
        r"\b(?:computes?|contained|containing|contains?|uses?|using|requires?|"
        r"produces?|provides?|employs?|encoded)\b",
        subject,
        re.I,
    ):
        return None
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
    elif predicate == "used_for":
        object_ = re.sub(
            r"^(?:successfully\s+)?(?:in|for)\s+", "", object_, flags=re.I
        )
    object_ = canonical_label(object_)
    if predicate == "authorized_to" and object_.casefold() in {"power", "sole power"}:
        return None
    if predicate in {"has", "possesses"} and re.match(
        r"^(?:to|been|become)\b", object_, re.I
    ):
        return None
    if not subject or not object_ or re.match(r"^(?:no|not|without)\b", object_, re.I):
        return None
    return subject, predicate, object_


def _triple_options(
    frame: RelationFrame, limit: int = 16
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


def build_scoring_request(frames: list[RelationFrame]) -> dict[str, object]:
    state_frames = [
        {
            "id": f"f{index}",
            "context": frame.context,
            "evidence": frame.evidence,
        }
        for index, frame in enumerate(frames)
    ]
    questions: dict[str, object] = {}
    for frame_index, frame in enumerate(frames):
        for option_index, (subject, predicate, object_) in enumerate(
            _triple_options(frame)
        ):
            shared = {
                "evidence_id": f"f{frame_index}",
                "candidate": {
                    "subject": subject,
                    "predicate": predicate,
                    "object": object_,
                },
            }
            questions[f"f{frame_index}_t{option_index}_support"] = {
                "type": "noul",
                "instructions": {
                    **shared,
                    "question": (
                        "Does the referenced evidence explicitly assert exactly this "
                        "relationship as a factual claim? Answer no for wrong or incomplete "
                        "boundaries, wrong direction, negation, modality, or relationships "
                        "requiring an unstated inference."
                    ),
                },
            }
            questions[f"f{frame_index}_t{option_index}_entities"] = {
                "type": "noul",
                "instructions": {
                    **shared,
                    "question": (
                        "Are both the subject and object self-contained, meaningful RDF node "
                        "labels rather than pronouns, deictic phrases, headings, fragments, "
                        "or clauses containing the relation itself?"
                    ),
                },
            }
    return {
        "model": MODEL,
        "state": {
            "task": "Score complete source-grounded RDF triple candidates.",
            "frames": state_frames,
        },
        "questions": questions,
    }


def parse_scoring_answers(
    frames: list[RelationFrame], response: dict[str, object]
) -> list[VerifiedTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")

    verified: list[VerifiedTriple] = []
    for frame_index, frame in enumerate(frames):
        best: VerifiedTriple | None = None
        for option_index, (subject, predicate, object_) in enumerate(
            _triple_options(frame)
        ):
            support_answer = answers.get(
                f"f{frame_index}_t{option_index}_support"
            )
            entities_answer = answers.get(
                f"f{frame_index}_t{option_index}_entities"
            )
            if not isinstance(support_answer, dict) or not isinstance(
                entities_answer, dict
            ):
                raise JevError(
                    f"Jev omitted candidate {option_index} for frame {frame_index}"
                )
            try:
                support = float(support_answer["noul"])
                entity_quality = float(entities_answer["noul"])
            except (KeyError, TypeError, ValueError) as error:
                raise JevError(
                    f"Jev returned an invalid candidate score for frame {frame_index}"
                ) from error
            item = VerifiedTriple(
                CandidateTriple(
                    subject=subject,
                    predicate=predicate,
                    object=object_,
                    evidence=frame.evidence,
                    sentence_index=frame.sentence_index,
                    start=frame.start,
                    end=frame.end,
                ),
                support,
                entity_quality,
            )
            if best is None or min(item.support, item.entity_quality) > min(
                best.support, best.entity_quality
            ):
                best = item
        if best is not None:
            verified.append(best)
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
        batch_size: int = 16,
        attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self.api_key = api_key
        self.timeout = timeout
        self.batch_size = batch_size
        self.attempts = attempts

    def score(self, frames: list[RelationFrame]) -> list[VerifiedTriple]:
        verified: list[VerifiedTriple] = []
        for batch in _batches(frames, self.batch_size):
            payload = self._post(build_scoring_request(batch))
            verified.extend(parse_scoring_answers(batch, payload))
        return verified

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

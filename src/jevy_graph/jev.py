from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict
from typing import TypeVar

from .models import CandidateTriple, RelationFrame, VerifiedTriple

API_URL = "https://api.typesafe.ai/v1/systemone"
T = TypeVar("T")


class JevError(RuntimeError):
    pass


def _choice_criteria(prefix: str, options: tuple[str, ...]) -> dict[str, str]:
    criteria = {f"{prefix}{index}": option for index, option in enumerate(options)}
    criteria["none"] = "No candidate is a precise, supported answer."
    return criteria


def build_resolution_request(frames: list[RelationFrame]) -> dict[str, object]:
    questions: dict[str, object] = {}
    for index, frame in enumerate(frames):
        shared = {"context": frame.context, "evidence": frame.evidence}
        questions[f"f{index}_subject"] = {
            "type": "choice",
            "instructions": {
                **shared,
                "question": (
                    "Which option is the minimal complete semantic subject of the relation "
                    "expressed in `evidence`? Exclude determiners, modal verbs, and auxiliaries."
                ),
            },
            "criteria": _choice_criteria("s", frame.subject_options),
        }
        questions[f"f{index}_predicate"] = {
            "type": "choice",
            "instructions": {
                **shared,
                "question": (
                    "Which normalized predicate most precisely represents the relation "
                    "expressed in `evidence`?"
                ),
            },
            "criteria": _choice_criteria("p", frame.predicate_options),
        }
        questions[f"f{index}_object"] = {
            "type": "choice",
            "instructions": {
                **shared,
                "question": (
                    "Which option is the minimal complete semantic object of the relation "
                    "expressed in `evidence`? Include necessary complements but no extra claim."
                ),
            },
            "criteria": _choice_criteria("o", frame.object_options),
        }
    return {
        "model": "jev-latest",
        "state": {"task": "Resolve deterministic knowledge graph candidate lattices."},
        "questions": questions,
    }


def _selected_option(
    answer: object, options: tuple[str, ...], prefix: str, frame_index: int
) -> str | None:
    if not isinstance(answer, dict):
        raise JevError(f"Jev omitted a resolution answer for frame {frame_index}")
    choice = answer.get("choice")
    if choice == "none":
        return None
    if not isinstance(choice, str) or not choice.startswith(prefix):
        raise JevError(f"Jev returned an invalid resolution answer for frame {frame_index}")
    try:
        return options[int(choice[len(prefix) :])]
    except (ValueError, IndexError) as error:
        raise JevError(f"Jev returned an unknown option for frame {frame_index}") from error


def parse_resolution_answers(
    frames: list[RelationFrame], response: dict[str, object]
) -> list[CandidateTriple]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Jev response did not contain an answers object")

    candidates: list[CandidateTriple] = []
    for index, frame in enumerate(frames):
        subject = _selected_option(
            answers.get(f"f{index}_subject"), frame.subject_options, "s", index
        )
        predicate = _selected_option(
            answers.get(f"f{index}_predicate"), frame.predicate_options, "p", index
        )
        object_ = _selected_option(
            answers.get(f"f{index}_object"), frame.object_options, "o", index
        )
        if subject is None or predicate is None or object_ is None:
            continue
        if predicate == "authorized_to":
            object_ = re.sub(r"^(?:the\s+)?power\s+to\s+", "", object_, flags=re.I)
        candidates.append(
            CandidateTriple(
                subject=subject,
                predicate=predicate,
                object=object_,
                evidence=frame.evidence,
                sentence_index=frame.sentence_index,
                start=frame.start,
                end=frame.end,
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
                    "Does `evidence` directly support the candidate subject-predicate-object "
                    "relationship, with the same meaning and direction?"
                ),
            },
            "criteria": {
                "true": "The evidence directly states or clearly entails this exact relationship.",
                "false": "The relationship is absent, reversed, merely associated, or needs unstated assumptions.",
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
    return {
        "model": "jev-latest",
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
        factual_answer = answers.get(f"c{index}_factual")
        if not isinstance(support_answer, dict) or not isinstance(factual_answer, dict):
            raise JevError(f"Jev response omitted answers for candidate {index}")
        try:
            support = float(support_answer["noul"])
            factuality = float(factual_answer["noul"])
        except (KeyError, TypeError, ValueError) as error:
            raise JevError(f"Jev returned an invalid answer for candidate {index}") from error
        verified.append(VerifiedTriple(candidate, support, factuality))
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
        batch_size: int = 40,
        attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self.api_key = api_key
        self.timeout = timeout
        self.batch_size = batch_size
        self.attempts = attempts

    def verify(self, candidates: list[CandidateTriple]) -> list[VerifiedTriple]:
        verified: list[VerifiedTriple] = []
        for batch in _batches(candidates, self.batch_size):
            verified.extend(self._verify_batch(batch))
        return verified

    def resolve(self, frames: list[RelationFrame]) -> list[CandidateTriple]:
        candidates: list[CandidateTriple] = []
        for batch in _batches(frames, self.batch_size):
            payload = self._post(build_resolution_request(batch))
            candidates.extend(parse_resolution_answers(batch, payload))
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

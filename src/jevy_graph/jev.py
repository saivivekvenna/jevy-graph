from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict

from .models import CandidateTriple, VerifiedTriple

API_URL = "https://api.typesafe.ai/v1/systemone"


class JevError(RuntimeError):
    pass


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


def _batches(items: list[CandidateTriple], size: int) -> Iterable[list[CandidateTriple]]:
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

    def _verify_batch(self, candidates: list[CandidateTriple]) -> list[VerifiedTriple]:
        body = json.dumps(build_request(candidates), separators=(",", ":")).encode()
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
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise JevError("Jev returned a non-object response")
                return parse_answers(candidates, payload)
            except urllib.error.HTTPError as error:
                if error.code not in {429, 529} or attempt + 1 == self.attempts:
                    raise JevError(f"Jev request failed with HTTP {error.code}") from error
            except urllib.error.URLError as error:
                if attempt + 1 == self.attempts:
                    raise JevError(f"Could not reach Jev: {error.reason}") from error
            time.sleep(0.25 * (2**attempt))

        raise JevError("Jev request failed")


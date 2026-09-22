from __future__ import annotations

import http.client
import json
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

from .models import CandidateTriple, RelationFrame, VerifiedTriple
from .normalize import canonical_entity, canonical_label, object_kind

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
    input_tokens: int = 0
    output_tokens: int = 0


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
    frames: list[RelationFrame], *, compact: bool = False
) -> dict[str, object]:
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
        if compact:
            fixed = {
                name: next(iter(values))
                for name in ("subject", "predicate", "object")
                if len(values := {triple[name] for triple in criteria.values()}) == 1
            }
            if fixed:
                instructions = questions[f"f{index}_triple"]["instructions"]
                instructions["fixed_fields"] = fixed
                instructions["question"] += " Each candidate inherits these fixed fields."
                for triple in criteria.values():
                    for name in fixed:
                        del triple[name]
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
        candidate_data = {
            "subject": candidate.subject,
            "predicate": candidate.predicate,
            "object": candidate.object,
            "evidence": candidate.evidence,
            "context": candidate.context,
            "modality": candidate.modality or "unmodalized",
            "polarity": candidate.polarity,
            "condition": candidate.condition,
            "origin": candidate.origin,
        }
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
        attempts: int = 6,
        compact: bool = False,
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
        self.singleton_selections = 0
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

    def _resolve_frames(
        self, frames: list[RelationFrame]
    ) -> tuple[list[CandidateTriple], int]:
        resolved: dict[int, CandidateTriple] = {}
        pending_indexes: list[int] = []
        pending_frames: list[RelationFrame] = []
        eligible_index = 0
        singleton_count = 0
        for frame in frames:
            options = _triple_options(frame)
            if not options:
                continue
            if len(options) == 1:
                resolved[eligible_index] = _candidate(frame, options[0])
                singleton_count += 1
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
            resolved[index] = candidate
        return [resolved[index] for index in range(eligible_index)], singleton_count

    def verify(self, candidates: list[CandidateTriple]) -> list[VerifiedTriple]:
        return _parallel_batches(
            _batches(candidates, self.verification_batch_size),
            self._verify_batch,
            self.max_workers,
        )

    def score(self, frames: list[RelationFrame]) -> list[VerifiedTriple]:
        batches = sorted(self._iter_scored_batches(frames), key=lambda item: item[0])
        return [item for _, batch in batches for item in batch]

    def iter_score_batches(
        self, frames: list[RelationFrame]
    ) -> Iterator[list[VerifiedTriple]]:
        """Yield independently verified frame batches as they actually complete."""
        for _, batch in self._iter_scored_batches(frames):
            if batch:
                yield batch

    def _iter_scored_batches(
        self, frames: list[RelationFrame]
    ) -> Iterator[tuple[int, list[VerifiedTriple]]]:
        batches = iter(enumerate(_batches(frames, self.choice_batch_size)))
        if not frames:
            return
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        pending = {}
        try:
            for index, batch in batches:
                pending[executor.submit(self._score_frame_batch, batch)] = index
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
                        future = executor.submit(self._score_frame_batch, batch)
                        pending[future] = next_index
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    def _score_frame_batch(
        self, frames: list[RelationFrame]
    ) -> list[VerifiedTriple]:
        candidates, singleton_count = self._resolve_frames(frames)
        if singleton_count:
            with self._stats_lock:
                self.singleton_selections += singleton_count
        verified: list[VerifiedTriple] = []
        for batch in _batches(candidates, self.verification_batch_size):
            verified.extend(self._verify_batch(batch))
        return verified

    def _resolve_batch(self, frames: list[RelationFrame]) -> list[CandidateTriple]:
        payload = build_choice_request(frames, compact=self.compact)
        if len(frames) > 1 and len(json.dumps(payload).encode()) > MAX_REQUEST_BYTES:
            return [
                candidate
                for batch in _batches(frames, (len(frames) + 1) // 2)
                for candidate in self._resolve_batch(batch)
            ]
        return parse_choice_answers(frames, self._post(payload))

    def _verify_batch(
        self, candidates: list[CandidateTriple]
    ) -> list[VerifiedTriple]:
        payload = build_verification_request(candidates)
        if len(candidates) > 1 and len(json.dumps(payload).encode()) > MAX_REQUEST_BYTES:
            return [
                item
                for batch in _batches(candidates, (len(candidates) + 1) // 2)
                for item in self._verify_batch(batch)
            ]
        return parse_verification_answers(candidates, self._post(payload))

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, separators=(",", ":")).encode()
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

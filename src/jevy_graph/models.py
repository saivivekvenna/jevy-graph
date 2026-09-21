from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelationFrame:
    subject_options: tuple[str, ...]
    predicate_options: tuple[str, ...]
    object_options: tuple[str, ...]
    evidence: str
    context: str
    sentence_index: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class CandidateTriple:
    subject: str
    predicate: str
    object: str
    evidence: str
    sentence_index: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class VerifiedTriple:
    candidate: CandidateTriple
    support: float
    factuality: float

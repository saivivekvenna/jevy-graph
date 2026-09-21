from __future__ import annotations

from dataclasses import dataclass


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


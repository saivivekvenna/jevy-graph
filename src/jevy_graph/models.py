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
    modality: str | None = None
    polarity: str = "positive"


@dataclass(frozen=True, slots=True)
class CandidateTriple:
    subject: str
    predicate: str
    object: str
    evidence: str
    sentence_index: int
    start: int
    end: int
    modality: str | None = None
    polarity: str = "positive"
    object_kind: str = "entity"
    selection_confidence: float = 1.0
    selection_probability: float = 1.0


@dataclass(frozen=True, slots=True)
class VerifiedTriple:
    candidate: CandidateTriple
    support: float
    entity_quality: float

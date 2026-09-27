from __future__ import annotations

from dataclasses import dataclass


SCIENTIFIC_CLAIM_TYPES = frozenset({
    "attribute", "directional_effect", "comparison", "causality",
    "association", "null_result",
})


@dataclass(frozen=True, slots=True)
class ClaimFrame:
    """A source-grounded claim whose qualifiers remain structured.

    Scientific claims use this representation as their canonical form.  A
    subject-relation-object projection remains available for RDF output,
    but comparisons and measurements are not compressed into node labels.
    """

    claim_type: str
    subject: str
    relation: str
    object: str
    evidence: str
    sentence_index: int
    start: int
    end: int
    comparison: str | None = None
    conditions: tuple[str, ...] = ()
    measurements: tuple[str, ...] = ()
    modality: str | None = None
    polarity: str = "positive"
    negated: bool = False
    source_unit: str | None = None
    source_locator: str | None = None
    source_page: int | None = None
    trigger_start: int | None = None
    trigger_end: int | None = None
    origin: str = "scientific_claim"
    attribution: str | None = None

    def __post_init__(self) -> None:
        if self.claim_type not in SCIENTIFIC_CLAIM_TYPES:
            raise ValueError(f"Unknown scientific claim type: {self.claim_type}")

    @property
    def complete(self) -> bool:
        return bool(self.subject and self.relation and self.object)


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
    source_unit: str | None = None
    source_locator: str | None = None
    source_page: int | None = None
    condition: str | None = None
    origin: str = "pattern"
    attribution: str | None = None
    claim_type: str | None = None
    comparison: str | None = None
    conditions: tuple[str, ...] = ()
    measurements: tuple[str, ...] = ()


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
    source_unit: str | None = None
    source_locator: str | None = None
    source_page: int | None = None
    condition: str | None = None
    origin: str = "pattern"
    context: str | None = None
    attribution: str | None = None
    claim_type: str | None = None
    comparison: str | None = None
    conditions: tuple[str, ...] = ()
    measurements: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerifiedTriple:
    candidate: CandidateTriple
    support: float
    entity_quality: float
    scope_relevance: float = 1.0
    qualifier_quality: float = 1.0
    atomicity: float = 1.0


@dataclass(frozen=True, slots=True)
class GraphIntent:
    instruction: str = ""
    group_by: str = "none"

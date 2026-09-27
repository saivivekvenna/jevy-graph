from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class Mention:
    span: SourceSpan
    head: str
    kind: str
    normalized: str
    provenance: tuple[SourceSpan, ...] = ()


@dataclass(frozen=True, slots=True)
class ScientificQualifiers:
    polarity: str = "positive"
    modality: str | None = "asserted"
    cells: tuple[str, ...] = ()
    cohort: str | None = None
    comparator: str | None = None
    conditions: tuple[str, ...] = ()
    measurements: tuple[str, ...] = ()
    assay: str | None = None
    attribution: str | None = None

    def render(self) -> str | None:
        parts = tuple(dict.fromkeys((
            *self.cells,
            self.comparator,
            self.cohort,
            *self.conditions,
            *self.measurements,
            self.assay,
        )))
        values = tuple(part for part in parts if part)
        return "; ".join(values) if values else None


@dataclass(frozen=True, slots=True)
class EventHypothesis:
    subject: Mention
    predicate: str
    object: Mention
    qualifiers: ScientificQualifiers
    anchor: SourceSpan
    construction: str
    confidence: str = "exact"
    required_qualifiers: frozenset[str] = frozenset()
    covered_qualifiers: frozenset[str] = frozenset()
    provenance: tuple[SourceSpan, ...] = ()

    @property
    def complete(self) -> bool:
        return self.required_qualifiers <= self.covered_qualifiers


@dataclass(frozen=True, slots=True)
class TraceRecord:
    stage: str
    decision: str
    detail: str = ""


@dataclass(slots=True)
class ScientificContext:
    source_unit: str | None = None
    heading: str | None = None
    intervention: str | None = None
    cells: tuple[str, ...] = field(default_factory=tuple)
    model: str | None = None
    assay: str | None = None
    outcome: str | None = None
    performance_target: str | None = None
    signature: str | None = None
    validation_context: str | None = None
    sentence_index: int = -1

    def reset_local(self) -> None:
        self.intervention = None
        self.cells = ()
        self.model = None
        self.assay = None
        self.outcome = None
        self.performance_target = None
        self.signature = None
        self.validation_context = None


@dataclass(frozen=True, slots=True)
class CompileResult:
    hypotheses: tuple[EventHypothesis, ...]
    traces: tuple[TraceRecord, ...]
    classification: str
    suppress_generic: bool = False

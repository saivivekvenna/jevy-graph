from __future__ import annotations

import re

from ..events import ContextBundle, EventFrame, EvidenceSpan
from ..models import ClaimFrame
from .constructions import compile_constructions
from .general import compile_general_constructions
from .mentions import clean_text, split_coordination
from .model import CompileResult, ScientificContext, TraceRecord
from .segment import classify_clause


def _cell_list(value: str) -> tuple[str, ...]:
    value = clean_text(value)
    values = []
    for item in split_coordination(value):
        item = re.sub(r"^(?:both|the)\s+", "", item, flags=re.I)
        if not item.casefold().endswith(" cells"):
            item += " cells"
        values.append(item)
    return tuple(dict.fromkeys(values))


def _claim_parts(hypothesis) -> tuple[str, str | None, tuple[str, ...]]:
    """Keep comparison and magnitude material out of the object boundary."""
    qualifiers = hypothesis.qualifiers

    def comparable(value: str) -> str:
        return re.sub(r"\s+([%°])", r"\1", clean_text(value)).casefold()

    comparison = qualifiers.comparator
    conditions: list[str] = []
    for condition in qualifiers.conditions:
        match = re.match(
            r"^(?:compared\s+(?:with|to)|versus|vs\.?|relative\s+to|than)\s+(.+)$",
            condition, re.I,
        )
        if match and comparison is None:
            comparison = clean_text(match.group(1))
        elif any(
            comparable(condition) == f"by {comparable(measurement)}"
            for measurement in qualifiers.measurements
        ):
            continue
        else:
            conditions.append(condition)
    object_ = hypothesis.object.normalized
    for measurement in qualifiers.measurements:
        suffix = re.search(r"\s+by\s+(.+)$", object_, re.I)
        if suffix and comparable(suffix.group(1)) == comparable(measurement):
            object_ = object_[:suffix.start()]
    return clean_text(object_), comparison, tuple(conditions)


class ScientificClauseCompiler:
    """Stateful, source-grounded compiler for scientific Results clauses."""

    def __init__(self, *, dependency_compiler: object | None = None) -> None:
        self.state = ScientificContext()
        self.traces: list[TraceRecord] = []
        self.dependency_compiler = dependency_compiler

    def compile(
        self,
        text: str,
        *,
        source_unit: str | None,
        sentence_index: int,
    ) -> CompileResult:
        if not source_unit or not (
            source_unit.upper().startswith("RESULT")
            or source_unit.upper() == "DOCUMENT"
        ):
            return CompileResult((), (), "outside_scientific_results")

        if source_unit != self.state.source_unit:
            self.state = ScientificContext(source_unit=source_unit)
        self.state.sentence_index = sentence_index
        classification = classify_clause(text)
        local_trace = [TraceRecord("classification", classification)]
        if classification == "heading":
            self.state.heading = clean_text(text)
            self.state.reset_local()
            local_trace.append(TraceRecord("context", "heading_reset", self.state.heading))
            self.traces.extend(local_trace)
            return CompileResult((), tuple(local_trace), classification)

        self._observe_explicit_setup(text, local_trace)
        construction_hypotheses = tuple(compile_constructions(text, self.state))
        general_hypotheses = tuple(compile_general_constructions(text, self.state))
        native_hypotheses = (*construction_hypotheses, *general_hypotheses)
        dependency_hypotheses = (
            tuple(self.dependency_compiler.compile(
                text, self.state, classification=classification,
            ))
            if (
                self.dependency_compiler is not None
                and (
                    getattr(self.dependency_compiler, "grammar", True)
                    or not native_hypotheses
                )
            ) else ()
        )
        # Prefer the representation that atomizes the clause more completely.
        # Existing curated constructions normally win.  The dependency
        # compiler replaces them only when the native object still contains a
        # conjunction or another relation, which signals an un-split claim.
        native_needs_atomization = any(
            re.search(
                r"\b(?:and|both|increases?|decreases?|reduces?|promotes?|"
                r"inhibits?|blocks?|outperforms?|underperforms?)\b",
                f"{item.subject.normalized} {item.object.normalized}", re.I,
            )
            for item in native_hypotheses
        )
        native_needs_atomization = native_needs_atomization or any(
            re.match(r"^(?:while|which|it)\b", item.subject.normalized, re.I)
            for item in native_hypotheses
        )
        dependency_structured = any(
            item.construction in {
                "dependency_shared_metric", "dependency_unit_assignment",
                "dependency_elliptic_comparison",
            }
            for item in dependency_hypotheses
        )
        selected = (
            dependency_hypotheses
            if (
                not native_hypotheses
                or (
                    (native_needs_atomization or dependency_structured)
                    and len(dependency_hypotheses) > len(native_hypotheses)
                )
            )
            else native_hypotheses
        )
        hypotheses = self._dedupe(selected)
        if hypotheses:
            local_trace.extend(
                TraceRecord("construction", item.construction, item.anchor.text)
                for item in hypotheses
            )
        elif classification not in {"procedure", "purpose", "mixed"}:
            local_trace.append(TraceRecord(
                "candidate_generation", "miss", "no complete construction",
            ))
        self._observe_findings(text, local_trace)
        self.traces.extend(local_trace)
        return CompileResult(
            hypotheses, tuple(local_trace), classification,
            suppress_generic=bool(
                general_hypotheses
                or (selected is dependency_hypotheses and dependency_hypotheses)
            ),
        )

    @staticmethod
    def _dedupe(hypotheses):
        unique = []
        seen = set()
        for item in hypotheses:
            key = (
                item.subject.normalized.casefold(), item.predicate,
                item.object.normalized.casefold(), item.qualifiers.modality,
                item.qualifiers.polarity, item.qualifiers.render(),
            )
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return tuple(unique)

    def _observe_explicit_setup(
        self, text: str, traces: list[TraceRecord]
    ) -> None:
        patterns = (
            (r"\b(?:used\s+[^,.;]+?\s+to\s+)?knock\s+down\s+(?:the\s+expression\s+of\s+)?"
             r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "knockdown"),
            (r"\bknocked\s+down\s+(?:the\s+expression\s+of\s+)?"
             r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "knockdown"),
            (r"\boverexpressed\s+(?:[A-Za-z]+-tagged\s+)?"
             r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "overexpression"),
            (r"\b(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+overexpression\b", "overexpression"),
            (r"\bdownregulation\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+expression", "knockdown"),
        )
        for pattern, operation in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                self.state.intervention = f"{match.group('entity')} {operation}"
                traces.append(TraceRecord(
                    "context", "explicit_intervention", self.state.intervention,
                ))
                break

        in_cells = re.search(
            r"\bin\s+(?P<cells>(?:both\s+)?[A-Z][A-Za-z0-9-]*(?:\s+and\s+"
            r"[A-Z][A-Za-z0-9-]*)?\s+cells)\b",
            text,
        )
        if in_cells:
            self.state.cells = _cell_list(in_cells.group("cells"))
            traces.append(TraceRecord(
                "context", "explicit_cells", "; ".join(self.state.cells),
            ))

        xenograft = re.search(
            r"xenograft\s+tumou?r\s+model\s+using\s+[^,.;]*?"
            r"sh-(?:NC|control)-(?P<cell>[A-Za-z0-9-]+)\s+and\s+"
            r"sh-(?P<entity>[A-Za-z][A-Za-z0-9-]*)-(?P=cell)\s+cells",
            text,
            re.I,
        )
        if xenograft:
            self.state.intervention = f"{xenograft.group('entity')} knockdown"
            self.state.cells = (f"{xenograft.group('cell')} cells",)
            self.state.model = f"{xenograft.group('cell')} xenograft tumors"
            traces.append(TraceRecord(
                "context", "explicit_model", self.state.model,
            ))

        sh_groups = re.search(
            r"\bshNC\s+and\s+sh(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+groups\b",
            text,
            re.I,
        )
        if sh_groups:
            self.state.intervention = f"{sh_groups.group('entity')} knockdown"
            self.state.model = "xenograft tumors"
            traces.append(TraceRecord(
                "context", "explicit_intervention", self.state.intervention,
            ))

        assay = re.search(
            r"\b(?P<assay>MTT|colony\s+formation|flow\s+cytometry|"
            r"EdU\s+incorporation|western\s+blotting|RIP-RT.?qPCR)\s+assay",
            text,
            re.I,
        )
        if assay:
            self.state.assay = clean_text(assay.group("assay"))

    def _observe_findings(
        self, text: str, traces: list[TraceRecord]
    ) -> None:
        outcome = re.search(
            r"(?:ratio\s+of\s+)?(?P<outcome>apoptotic\s+cells|cell\s+proliferation|"
            r"colony\s+formation|S-phase\s+cells)",
            text,
            re.I,
        )
        if outcome:
            normalized = clean_text(outcome.group("outcome"))
            normalized = {
                "apoptotic cells": "apoptotic cell ratio",
                "s-phase cells": "S-phase cell count",
            }.get(normalized.casefold(), normalized)
            self.state.outcome = normalized
            traces.append(TraceRecord("context", "explicit_outcome", normalized))

        performance = re.search(
            r"(?P<target>median\s+[A-Za-z][A-Za-z0-9]*\s+"
            r"(?:greater\s+than|less\s+than|of)\s+\d+(?:\.\d+)?)",
            text,
            re.I,
        )
        if performance:
            self.state.performance_target = clean_text(performance.group("target"))
            traces.append(TraceRecord(
                "context", "performance_target", self.state.performance_target,
            ))

        signature = re.search(
            r"(?P<signature>\d+-gene\s+(?:diagnostic\s+)?signature)", text, re.I,
        )
        if signature:
            self.state.signature = clean_text(signature.group("signature"))
            traces.append(TraceRecord(
                "context", "signature", self.state.signature,
            ))

        if re.search(r"\b(?:the\s+)?validation\s+cohort\b", text, re.I):
            self.state.validation_context = "independent validation cohort"
            traces.append(TraceRecord(
                "context", "validation_context", self.state.validation_context,
            ))

        classifier_model = re.search(
            r"(?P<model>[^,.;]{1,100}?\([^)]*\)\s+model|"
            r"[A-Za-z][A-Za-z0-9/-]+\s+model)\s+classified\b",
            text,
            re.I,
        )
        if classifier_model:
            model = re.sub(
                r"^The\s+", "", clean_text(classifier_model.group("model")), flags=re.I,
            )
            acronym = re.search(r"\((?P<name>[A-Z][A-Z0-9/-]+)\)", model)
            self.state.model = f"{acronym.group('name')} model" if acronym else model
            traces.append(TraceRecord("context", "model", self.state.model))


def hypotheses_to_events(result: CompileResult) -> tuple[EventFrame, ...]:
    events: list[EventFrame] = []
    for hypothesis in result.hypotheses:
        qualifiers = hypothesis.qualifiers
        object_, comparison, conditions = _claim_parts(hypothesis)
        events.append(EventFrame(
            subject=hypothesis.subject.normalized,
            predicate=hypothesis.predicate,
            object=object_,
            modality=qualifiers.modality,
            polarity=qualifiers.polarity,
            context=ContextBundle(
                cells=qualifiers.cells,
                cohort=qualifiers.cohort,
                comparator=comparison,
                measurements=qualifiers.measurements,
                assay=qualifiers.assay,
                extra=conditions,
            ),
            attribution=qualifiers.attribution,
            trigger=EvidenceSpan(
                hypothesis.anchor.start,
                hypothesis.anchor.end,
                hypothesis.anchor.text,
            ),
            required_qualifiers=hypothesis.required_qualifiers,
            covered_qualifiers=hypothesis.covered_qualifiers,
            claim_type=claim_type_for(
                hypothesis.predicate, qualifiers.polarity,
            ),
            comparison=comparison,
            conditions=conditions,
            measurements=qualifiers.measurements,
        ))
    return tuple(events)


def claim_type_for(predicate: str, polarity: str = "positive") -> str:
    """Map a normalized relation into one of the six reusable claim types."""
    relation = predicate.casefold()
    if polarity == "negative" or relation.startswith(("does_not_", "no_")):
        return "null_result"
    if any(token in relation for token in (
        "higher", "lower", "better", "worse", "outperform", "underperform",
        "differ_from",
    )):
        return "comparison"
    if relation.startswith("has_") or relation in {
        "has", "is", "are", "type", "exhibits", "follows",
    }:
        return "attribute"
    if any(token in relation for token in (
        "increase", "decrease", "reduce", "elevate", "improve", "impair",
        "restore", "attenuate", "diminish",
    )):
        return "directional_effect"
    if any(token in relation for token in (
        "correlat", "associat", "interact", "linked_to", "overlap",
    )):
        return "association"
    return "causality"


def hypotheses_to_claims(
    result: CompileResult,
    *,
    evidence: str,
    sentence_index: int,
    start: int,
    end: int,
    source_unit: str | None,
) -> tuple[ClaimFrame, ...]:
    """Preserve scientific hypotheses as typed claim graph nodes."""
    claims = []
    for hypothesis in result.hypotheses:
        qualifiers = hypothesis.qualifiers
        object_, comparison, conditions = _claim_parts(hypothesis)
        claim = ClaimFrame(
            claim_type=claim_type_for(hypothesis.predicate, qualifiers.polarity),
            subject=hypothesis.subject.normalized,
            relation=hypothesis.predicate,
            object=object_,
            comparison=comparison,
            conditions=conditions,
            measurements=qualifiers.measurements,
            modality=qualifiers.modality,
            polarity=qualifiers.polarity,
            negated=qualifiers.polarity == "negative",
            evidence=evidence,
            sentence_index=sentence_index,
            start=start,
            end=end,
            trigger_start=start + hypothesis.anchor.start,
            trigger_end=start + hypothesis.anchor.end,
            source_unit=source_unit,
            origin=hypothesis.construction,
            attribution=qualifiers.attribution,
        )
        if claim.complete:
            claims.append(claim)
    return tuple(claims)

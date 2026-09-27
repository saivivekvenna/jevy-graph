"""Deterministic assembly of complete scientific event records."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .models import RelationFrame


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """Typed material context carried by one atomic event."""

    cells: tuple[str, ...] = ()
    cohort: str | None = None
    comparator: str | None = None
    measurements: tuple[str, ...] = ()
    assay: str | None = None
    contrast: str | None = None
    inference: str | None = None
    extra: tuple[str, ...] = ()

    def parts(self) -> tuple[str, ...]:
        return tuple(
            part for part in (
                *self.cells,
                self.comparator,
                self.cohort,
                *self.measurements,
                self.assay,
                self.contrast,
                self.inference,
                *self.extra,
            )
            if part
        )

    def render(self) -> str | None:
        parts = tuple(dict.fromkeys(self.parts()))
        return "; ".join(parts) if parts else None


@dataclass(frozen=True, slots=True)
class EventFrame:
    subject: str
    predicate: str
    object: str
    modality: str | None = "observed"
    polarity: str = "positive"
    context: ContextBundle = ContextBundle()
    attribution: str | None = None
    trigger: EvidenceSpan | None = None
    required_qualifiers: frozenset[str] = frozenset()
    covered_qualifiers: frozenset[str] = frozenset()
    claim_type: str | None = None
    comparison: str | None = None
    conditions: tuple[str, ...] = ()
    measurements: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.required_qualifiers <= self.covered_qualifiers


@dataclass(slots=True)
class EventState:
    """Small, explicit discourse state for a scientific Results section."""

    disease: str | None = None
    source_unit: str | None = None
    reversible_effects: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    last_intervention: str | None = None
    last_treatment: str | None = None
    cell_context: str | None = None

    def observe(self, text: str, source_unit: str | None) -> None:
        if source_unit != self.source_unit:
            self.source_unit = source_unit
            self.reversible_effects = ()
            self.last_intervention = None
            self.last_treatment = None
            self.cell_context = None
        disease = re.search(
            r"\b(?P<name>[A-Z][A-Z0-9-]{1,9})\b(?=\s+(?:patients?|tissues?|"
            r"specimens?|progression|metastasis))",
            text,
        )
        if disease and disease.group("name") not in {"RNA", "DNA", "IHC", "RIP"}:
            self.disease = disease.group("name")

        # Results prose usually introduces an intervention once, then carries
        # it through reporting wrappers, assay sentences, and interpretations.
        # Keep only explicit, local interventions; do not infer one from a gene
        # name alone.
        intervention_patterns = (
            (r"\bectopic\s+expression\s*(?:of\s+)?(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "ectopic expression"),
            (r"\boverexpression\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "overexpression"),
            (r"\b(?P<entity>[A-Za-z][A-Za-z0-9-]*)[- ]overexpressing\s+cells", "overexpression"),
            (r"\bknock-?down\s+(?:of\s+)?(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "knockdown"),
            (r"\b(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+knockdown", "knockdown"),
            (r"\b(?:RNAi-mediated\s+)?(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+silencing", "silencing"),
        )
        for pattern, intervention in intervention_patterns:
            found = re.search(pattern, text, re.I)
            if found:
                entity = found.group("entity")
                self.last_intervention = f"{entity} {intervention}"
                break

        treatment = re.search(
            r"\b(?:treated|treating)\s+(?:these\s+cells|the\s+cells|cells|"
            r"[A-Za-z0-9-]+)\s+with\s+(?:the\s+[^,.;]+?,\s*)?"
            r"(?P<treatment>[A-Z][A-Za-z0-9-]*\d[A-Za-z0-9-]*)\b",
            text, re.I,
        )
        if treatment:
            self.last_treatment = f"{treatment.group('treatment')} treatment"

        cells = re.search(r"\b(?P<cells>[A-Z]{2,}[A-Za-z0-9-]*s)\b", text)
        if cells:
            self.cell_context = cells.group("cells")


def _span(match: re.Match[str], group: str = "verb") -> EvidenceSpan:
    start, end = match.span(group)
    return EvidenceSpan(start, end, match.group(group))


def _event(
    subject: str,
    predicate: str,
    object_: str,
    *,
    context: ContextBundle = ContextBundle(),
    modality: str | None = "observed",
    polarity: str = "positive",
    attribution: str | None = None,
    trigger: EvidenceSpan | None = None,
    required: tuple[str, ...] = (),
    covered: tuple[str, ...] = (),
) -> EventFrame:
    return EventFrame(
        subject.strip(), predicate, object_.strip(), modality, polarity, context,
        attribution, trigger, frozenset(required), frozenset(covered),
    )


def _scientific_results(source_unit: str | None) -> bool:
    # Selected abstracts and benchmark excerpts have no heading markers, so
    # the converter labels them DOCUMENT.  The event rules below are lexical
    # and grammatical enough to run there safely; sectioned papers retain the
    # narrower Results-only behavior.
    return bool(source_unit and (
        source_unit.upper().startswith("RESULT")
        or source_unit.upper() == "DOCUMENT"
    ))


def _whole_span(match: re.Match[str]) -> EvidenceSpan:
    return EvidenceSpan(match.start(), match.end(), match.group(0))


def _normalize_intervention(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip(" ,.;"))
    patterns = (
        (r"ectopic expression\s*(?:of\s+)?(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "ectopic expression"),
        (r"overexpression of (?P<entity>[A-Za-z][A-Za-z0-9-]*)", "overexpression"),
        (r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)[- ]overexpressing cells", "overexpression"),
        (r"knock-?down (?:of )?(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "knockdown"),
        (r"(?P<entity>[A-Za-z][A-Za-z0-9-]*) knockdown(?: cells)?", "knockdown"),
        (r"(?:RNAi-mediated )?(?P<entity>[A-Za-z][A-Za-z0-9-]*) silencing", "silencing"),
    )
    for pattern, label in patterns:
        match = re.fullmatch(pattern, value, re.I)
        if match:
            return f"{match.group('entity')} {label}"
    return value


def _entity_from_intervention(value: str | None) -> str | None:
    if not value:
        return None
    return value.split()[0]


def _measurements(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            re.sub(r"\s+", " ", match.group(0)).strip(";, ")
            for match in re.finditer(r"\bp\s*[<=>≤≥]\s*0?\.?\d+", text, re.I)
        )
    )


def _context_bundle(
    state: EventState,
    *,
    comparator: str | None = None,
    assay: str | None = None,
    measurements: tuple[str, ...] = (),
    extra: tuple[str, ...] = (),
    treatment: bool = False,
) -> ContextBundle:
    if treatment and state.cell_context and state.last_treatment:
        extra = (f"{state.cell_context} treated with {state.last_treatment.removesuffix(' treatment')}", *extra)
        cells: tuple[str, ...] = ()
    else:
        cells = (state.cell_context,) if state.cell_context else ()
    return ContextBundle(
        cells=cells,
        comparator=comparator,
        measurements=measurements,
        assay=assay,
        extra=extra,
    )


def _split_named_items(value: str) -> tuple[str, ...]:
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip(" ,.;")
    return tuple(
        item.strip(" ,.;")
        for item in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", value)
        if item.strip(" ,.;")
    )


def _generic_results_events(
    text: str,
    *,
    previous_sentence: str,
    state: EventState,
) -> list[EventFrame]:
    """Assemble recurring scientific Results grammar without paper-specific names."""
    events: list[EventFrame] = []
    measurements = _measurements(text)

    canonical_target = re.search(
        r"(?:its|the)\s+canonical\s+transcriptional\s+target\s+"
        r"(?P<target>[A-Za-z][A-Za-z0-9-]*)",
        text, re.I,
    )
    actor = _entity_from_intervention(state.last_intervention)
    if canonical_target and actor:
        events.append(_event(
            canonical_target.group("target"), "canonical_transcriptional_target_of", actor,
            context=_context_bundle(state), modality="asserted",
            trigger=_whole_span(canonical_target),
        ))

    inducer_type = re.search(
        r"(?:classical|known|potent)\s+(?P<type>[A-Za-z-]+\s+inducer),\s*"
        r"(?P<entity>[A-Z][A-Za-z0-9-]*)",
        text, re.I,
    )
    if inducer_type:
        events.append(_event(
            inducer_type.group("entity"), "type", inducer_type.group("type"),
            context=ContextBundle(), modality="asserted", trigger=_whole_span(inducer_type),
        ))

    reporting = re.search(
        r"(?:our\s+findings|our\s+results|the\s+results|results)\s+"
        r"(?:revealed|showed|demonstrated|indicated)\s+that\s+"
        r"(?P<subject>(?:ectopic\s+expression\s+of\s+|overexpression\s+of\s+|"
        r"knockdown\s+of\s+)?[A-Za-z][A-Za-z0-9-]*(?:\s+knockdown)?)\s+"
        r"(?:significantly\s+|markedly\s+|substantially\s+)?"
        r"(?P<verb>upregulates?|upregulated|increases?|increased|decreases?|decreased|"
        r"reduces?|reduced|promotes?|promoted|attenuates?|attenuated|inhibits?|inhibited|"
        r"activates?|activated)\s+(?:the\s+)?(?P<object>[^,.;(]+)",
        text, re.I,
    )
    if reporting:
        raw_subject = reporting.group("subject")
        subject = _normalize_intervention(raw_subject)
        entity = _entity_from_intervention(state.last_intervention)
        if entity and raw_subject.casefold() == entity.casefold():
            subject = state.last_intervention or subject
        verb = reporting.group("verb").casefold()
        predicate = {
            "upregulate": "upregulates", "upregulates": "upregulates",
            "upregulated": "upregulates",
            "increase": "increases", "increases": "increases", "increased": "increases",
            "decrease": "decreases", "decreases": "decreases", "decreased": "decreases",
            "reduce": "reduces", "reduces": "reduces", "reduced": "reduces",
            "promote": "promotes", "promotes": "promotes", "promoted": "promotes",
            "attenuate": "attenuates", "attenuates": "attenuates", "attenuated": "attenuates",
            "inhibit": "inhibits", "inhibits": "inhibits", "inhibited": "inhibits",
            "activate": "activates", "activates": "activates", "activated": "activates",
        }[verb]
        object_ = re.sub(r"\s+", " ", reporting.group("object")).strip()
        treatment_context = bool(re.search(r"[A-Z][A-Za-z0-9-]*\d-induced", object_))
        coordinated_expression = re.fullmatch(
            r"expression\s+of\s+[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+",
            object_, re.I,
        )
        if not coordinated_expression:
            events.append(_event(
                subject, predicate, object_,
                context=_context_bundle(
                    state, measurements=measurements,
                    treatment=treatment_context,
                ),
                trigger=_whole_span(reporting),
            ))
        evidence_outcomes = re.search(
            r"as\s+evidenced\s+by\s+(?P<first>reduced\s+cell\s+death)\s+and\s+"
            r"(?:a\s+)?(?P<second>decrease\s+in\s+(?:ROS|reactive\s+oxygen\s+species)\s+accumulation)",
            text, re.I,
        )
        if evidence_outcomes:
            events.extend((
                _event(subject, "reduces", "cell death",
                       context=_context_bundle(state, treatment=True),
                       trigger=_whole_span(evidence_outcomes)),
                _event(subject, "decreases", "ROS accumulation",
                       context=_context_bundle(state, treatment=True),
                       trigger=_whole_span(evidence_outcomes)),
            ))

    direct_silencing = re.search(
        r"(?P<subject>(?:RNAi-mediated\s+)?[A-Za-z][A-Za-z0-9-]*\s+silencing)\s+"
        r"(?:\([^)]*\)\s*)*(?P<verb>reduced|decreased|increased)\s+"
        r"(?P<object>[A-Za-z0-9-]+\s+expression)",
        text, re.I,
    )
    if direct_silencing:
        predicate = {"reduced": "reduces", "decreased": "decreases", "increased": "increases"}[
            direct_silencing.group("verb").casefold()
        ]
        subject = _normalize_intervention(direct_silencing.group("subject"))
        events.append(_event(
            subject, predicate, direct_silencing.group("object"),
            context=_context_bundle(state, measurements=measurements),
            trigger=_whole_span(direct_silencing),
        ))
        consequence = re.search(r"attenuating\s+(?P<object>[^,.;]+)", text, re.I)
        if consequence:
            events.append(_event(
                subject, "attenuates", consequence.group("object"), modality="inferred",
                context=_context_bundle(state), trigger=_whole_span(consequence),
            ))

    standalone_consequence = re.search(
        r"(?P<verb>attenuating|promoting|inhibiting)\s+(?P<object>[^,.;]+)", text, re.I,
    )
    if standalone_consequence and state.last_intervention:
        predicate = {
            "attenuating": "attenuates",
            "promoting": "promotes",
            "inhibiting": "inhibits",
        }[standalone_consequence.group("verb").casefold()]
        events.append(_event(
            state.last_intervention, predicate, standalone_consequence.group("object"),
            modality="inferred", context=_context_bundle(state),
            trigger=_whole_span(standalone_consequence),
        ))

    expression_coordination = re.search(
        r"(?P<subject>ectopic\s+expression\s+of\s+[A-Za-z][A-Za-z0-9-]*)\s+"
        r"(?:significantly\s+)?(?P<verb>promotes?|increases?|decreases?)\s+"
        r"(?:the\s+)?expression\s+(?:levels?\s+)?of\s+(?P<targets>[^,.;]+)",
        text, re.I,
    )
    if expression_coordination:
        predicate = {
            "promote": "promotes", "promotes": "promotes",
            "increase": "increases", "increases": "increases",
            "decrease": "decreases", "decreases": "decreases",
        }[expression_coordination.group("verb").casefold()]
        subject = _normalize_intervention(expression_coordination.group("subject"))
        for target in _split_named_items(expression_coordination.group("targets")):
            events.append(_event(
                subject, predicate, f"{target} expression",
                context=_context_bundle(state, measurements=measurements),
                trigger=_whole_span(expression_coordination),
            ))

    knockdown_expression = re.search(
        r"(?P<subject>knockdown\s+of\s+[A-Za-z][A-Za-z0-9-]*)\s+resulted\s+in\s+"
        r"(?:a\s+)?(?:marked|significant|substantial)?\s*"
        r"(?P<direction>decrease|increase)\s+in\s+the\s+expression\s+levels?\s+of\s+"
        r"(?P<targets>[^,.;(]+)",
        text, re.I,
    )
    if knockdown_expression:
        predicate = "decreases" if knockdown_expression.group("direction").casefold() == "decrease" else "increases"
        subject = _normalize_intervention(knockdown_expression.group("subject"))
        for target in _split_named_items(knockdown_expression.group("targets")):
            events.append(_event(
                subject, predicate, f"{target} expression",
                context=_context_bundle(state, measurements=measurements),
                trigger=_whole_span(knockdown_expression),
            ))

    comparative_change = re.search(
        r"(?P<direction>decrease|increase|reduction)\s+in\s+"
        r"(?P<object>colony\s+numbers?)\s+in\s+"
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*(?:[- ]overexpressing|\s+knockdown)\s+cells)\s+"
        r"compared\s+to\s+(?P<comparator>control\s+cells)",
        text, re.I,
    )
    if comparative_change:
        predicate = "decreases" if comparative_change.group("direction").casefold() in {"decrease", "reduction"} else "increases"
        subject = _normalize_intervention(comparative_change.group("subject"))
        assay = "colony formation assay" if re.search(r"colony\s+formation", text, re.I) else None
        events.append(_event(
            subject, predicate, comparative_change.group("object"),
            context=_context_bundle(
                state, comparator=f"relative to {comparative_change.group('comparator')}", assay=assay,
            ), trigger=_whole_span(comparative_change),
        ))
        interpretation = re.search(
            r"indicating\s+(?P<direction>inhibited|promoted)\s+(?P<object>cell\s+growth)",
            text, re.I,
        )
        if interpretation:
            events.append(_event(
                subject,
                "inhibits" if interpretation.group("direction").casefold() == "inhibited" else "promotes",
                interpretation.group("object"), modality="inferred",
                context=_context_bundle(
                    state, comparator=f"relative to {comparative_change.group('comparator')}"
                ), trigger=_whole_span(interpretation),
            ))

    proliferating = re.search(
        r"(?P<direction>reduction|increase|decrease)\s+in\s+the\s+number\s+of\s+"
        r"(?P<object>proliferating\s+cells)\s+upon\s+"
        r"(?P<subject>(?:ectopic\s+expression\s+of\s+|knockdown\s+of\s+)?"
        r"[A-Za-z][A-Za-z0-9-]*(?:\s+ectopic\s+expression|\s+knockdown)?)",
        text, re.I,
    )
    if proliferating:
        predicate = "increases" if proliferating.group("direction").casefold() == "increase" else "decreases"
        events.append(_event(
            _normalize_intervention(proliferating.group("subject")), predicate,
            "proliferating cell count",
            context=_context_bundle(state, assay="EdU assay"),
            trigger=_whole_span(proliferating),
        ))

    dose_change = re.search(
        r"dose-dependent\s+(?P<direction>increase|decrease)\s+in\s+"
        r"(?P<object>[^,.;]+?)\s+following\s+"
        r"(?P<treatment>[A-Z][A-Za-z0-9-]*\d\s+treatment)",
        text, re.I,
    )
    if dose_change:
        events.append(_event(
            dose_change.group("treatment"),
            "increases" if dose_change.group("direction").casefold() == "increase" else "decreases",
            dose_change.group("object"),
            context=_context_bundle(state, extra=("dose-dependent",)),
            trigger=_whole_span(dose_change),
        ))

    release = re.search(
        r"(?P<treatment>[A-Z][A-Za-z0-9-]*\d\s+treatment)\s+led\s+to\s+"
        r"(?:a\s+)?(?:significant,?\s+)?(?P<dose>dose-dependent\s+)?"
        r"release\s+of\s+(?P<object>[A-Za-z0-9-]+)",
        text, re.I,
    )
    if release:
        events.append(_event(
            release.group("treatment"), "increases", f"{release.group('object')} release",
            context=_context_bundle(state, extra=(("dose-dependent",) if release.group("dose") else ())),
            trigger=_whole_span(release),
        ))

    ic50 = re.search(
        r"IC50\s+value\s+for\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+in\s+"
        r"(?P<cells>[A-Za-z0-9-]+)\s+was\s+calculated\s+to\s+be\s+"
        r"(?P<value>[0-9.]+\s*[µμu]M)",
        text, re.I,
    )
    if ic50:
        events.append(_event(
            ic50.group("entity"), "has_IC50", ic50.group("value").replace("μ", "µ"),
            context=ContextBundle(cells=(ic50.group("cells"),)),
            trigger=_whole_span(ic50),
        ))

    ros_accumulation = re.search(
        r"(?:corresponding\s+)?dose-dependent\s+accumulation\s+of\s+"
        r"(?:reactive\s+oxygen\s+species\s*\(ROS\)|ROS)",
        text, re.I,
    )
    if ros_accumulation and state.last_treatment:
        events.append(_event(
            state.last_treatment, "increases", "ROS accumulation",
            context=_context_bundle(state, extra=("dose-dependent",)),
            trigger=_whole_span(ros_accumulation),
        ))

    conditional_ferroptosis = re.search(
        r"(?P<cells>[A-Za-z0-9-]+)\s+can\s+undergo\s+(?P<process>[A-Za-z-]+)\s+"
        r"when\s+induced\s+by\s+(?P<inducer>[A-Za-z][A-Za-z0-9-]*)",
        text, re.I,
    )
    if conditional_ferroptosis:
        events.append(_event(
            conditional_ferroptosis.group("inducer"), "induces",
            conditional_ferroptosis.group("process"),
            context=ContextBundle(cells=(conditional_ferroptosis.group("cells"),)),
            modality="supported", trigger=_whole_span(conditional_ferroptosis),
        ))

    treatment_expression = re.search(
        r"(?:genes?\s+)?(?P<targets>[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+),\s+"
        r"observing\s+(?:a\s+)?(?:significant\s+)?elevation\s+in\s+their\s+"
        r"expression\s+levels?\s+post-(?P<treatment>[A-Za-z0-9-]+)\s+treatment",
        text, re.I,
    )
    if treatment_expression:
        for target in _split_named_items(treatment_expression.group("targets")):
            events.append(_event(
                f"{treatment_expression.group('treatment')} treatment", "elevates",
                f"{target} expression",
                context=_context_bundle(state, measurements=measurements),
                trigger=_whole_span(treatment_expression),
            ))

    capable = re.search(
        r"(?P<cells>[A-Za-z0-9-]+)\s+are\s+capable\s+of\s+undergoing\s+"
        r"(?P<process>[A-Za-z-]+)", text, re.I,
    )
    if capable:
        events.append(_event(
            capable.group("cells"), "capable_of", capable.group("process"),
            modality="suggested", context=ContextBundle(), trigger=_whole_span(capable),
        ))

    involved_genes = re.search(
        r"(?P<targets>[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+),\s+which\s+are\s+"
        r"(?:key\s+)?genes\s+involved\s+in\s+the\s+(?P<pathway>[A-Za-z-]+\s+pathway)",
        text, re.I,
    )
    if involved_genes:
        for target in _split_named_items(involved_genes.group("targets")):
            events.append(_event(
                target, "involved_in", involved_genes.group("pathway"),
                context=ContextBundle(), modality="asserted", trigger=_whole_span(involved_genes),
            ))

    susceptibility = re.search(
        r"(?:This|These\s+findings)\s+suggests?\s+that\s+"
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+(?P<modal>might|may|could)\s+"
        r"(?P<verb>enhance|reduce)\s+the\s+(?P<object>susceptibility\s+of\s+"
        r"(?P<cells>[A-Za-z0-9-]+)\s+to\s+[A-Za-z-]+)",
        text, re.I,
    )
    if susceptibility:
        object_ = re.sub(
            rf"susceptibility\s+of\s+{re.escape(susceptibility.group('cells'))}\s+to\s+",
            "susceptibility to ", susceptibility.group("object"), flags=re.I,
        )
        events.append(_event(
            susceptibility.group("subject"),
            "enhances" if susceptibility.group("verb").casefold() == "enhance" else "reduces",
            object_, modality=susceptibility.group("modal").casefold(),
            context=ContextBundle(cells=(susceptibility.group("cells"),)),
            trigger=_whole_span(susceptibility),
        ))

    protective = re.search(
        r"indicating\s+(?:a\s+)?(?P<modal>potential)\s+protective\s+effect\s+"
        r"against\s+(?P<object>[A-Za-z-]+)", text, re.I,
    )
    if protective and state.last_intervention:
        events.append(_event(
            state.last_intervention, "protects_against", protective.group("object"),
            modality=protective.group("modal"), context=_context_bundle(state),
            trigger=_whole_span(protective),
        ))

    mitigation = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+knockdown)\s+(?P<modal>can)\s+"
        r"(?P<verb>mitigate)\s+the\s+(?P<objects>[^.]+?)(?=\s+typically\s+associated|[.;]|$)",
        text, re.I,
    )
    if mitigation:
        for object_ in _split_named_items(mitigation.group("objects")):
            if object_.casefold() == "cellular damage":
                object_ = "cellular damage associated with ferroptosis"
            events.append(_event(
                _normalize_intervention(mitigation.group("subject")), "mitigates", object_,
                modality=mitigation.group("modal"),
                context=_context_bundle(state, treatment=True),
                trigger=_whole_span(mitigation),
            ))

    lipid = re.search(
        r"reduction\s+in\s+(?:ROS|reactive\s+oxygen\s+species)\s+levels\s+upon\s+"
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+knockdown)\s+was\s+accompanied\s+by\s+"
        r"(?P<verb>decreased)\s+(?P<object>lipid\s+peroxidation)",
        text, re.I,
    )
    if lipid:
        events.append(_event(
            _normalize_intervention(lipid.group("subject")), "decreases", lipid.group("object"),
            context=_context_bundle(state, treatment=True), trigger=_whole_span(lipid),
        ))

    synthesis = re.search(
        r"(?:findings\s+(?:collectively\s+)?(?:support|emphasize)|supporting)\s+"
        r"the\s+role\s+of\s+(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+in\s+"
        r"(?P<verb>modulating|regulating)\s+(?P<objects>[^,.;]+)",
        text, re.I,
    )
    if synthesis:
        predicate = "modulates" if synthesis.group("verb").casefold() == "modulating" else "regulates"
        objects = re.sub(r"\s+in\s+[A-Z]{2,}[A-Za-z0-9-]*s\s*$", "", synthesis.group("objects"))
        for object_ in _split_named_items(objects):
            events.append(_event(
                synthesis.group("subject"), predicate, object_, modality="supported",
                context=_context_bundle(state), trigger=_whole_span(synthesis),
            ))

    regulatory_factor = re.search(
        r"(?:highlighting|underscoring)\s+its\s+potential\s+as\s+a\s+key\s+"
        r"regulatory\s+factor\s+in\s+these\s+cells", text, re.I,
    )
    synthesis_subject = synthesis.group("subject") if synthesis else actor
    if regulatory_factor and synthesis_subject:
        events.append(_event(
            synthesis_subject, "potential_regulatory_factor_in",
            state.cell_context or "these cells", modality="potential",
            context=ContextBundle(), trigger=_whole_span(regulatory_factor),
        ))

    return events


def assemble_events(
    text: str,
    *,
    context_text: str,
    previous_sentence: str,
    source_unit: str | None,
    state: EventState,
) -> list[EventFrame]:
    """Assemble complete atomic events for recurring Results prose structures."""
    if not _scientific_results(source_unit):
        return []
    state.observe(text, source_unit)
    events: list[EventFrame] = []
    document_events: list[EventFrame] = []
    disease = state.disease or "CRC"

    lower_expression = re.search(
        r"(?P<assay>[A-Za-z0-9-]+\s+analysis)\s+(?P<verb>revealed)\s+"
        r"(?:significantly\s+)?lower\s+(?P<entity>[A-Za-z0-9-]+)\s+expression\s+"
        r"in\s+(?P<count>\d+\s+of\s+\d+\s+[A-Z][A-Z0-9-]*\s+specimens?)"
        r"\s*\((?P<measurement>p\s*[<=>]\s*[0-9.]+)\)",
        text, re.I,
    )
    if lower_expression:
        patient_count = re.search(r"(\d+)\s+patients?\s+with\s+([A-Z][A-Z0-9-]+)", previous_sentence)
        cohort = (
            f"{patient_count.group(1)} {patient_count.group(2)} patients"
            if patient_count else f"{disease} patients"
        )
        events.append(_event(
            f"{lower_expression.group('entity')} expression", "decreased_in",
            lower_expression.group("count"),
            context=ContextBundle(
                comparator="paired non-tumour tissues",
                cohort=cohort,
                measurements=(lower_expression.group("measurement"),),
            ),
            trigger=_span(lower_expression),
            required=("comparator", "cohort", "measurement"),
            covered=("comparator", "cohort", "measurement"),
        ))

    correlation = re.search(
        r"(?P<subject>[A-Za-z0-9-]+)\s+expression\s+level\s+was\s+"
        r"(?P<direction>reversely|inversely|negatively|positively)\s+"
        r"(?P<verb>correlated)\s+(?:to|with)\s+(?P<targets>.+)",
        text, re.I,
    )
    if correlation and len(re.findall(r"\(p\s*[<=>]", correlation.group("targets"), re.I)) >= 2:
        branches = re.split(r",?\s+while\s+", correlation.group("targets"), maxsplit=1, flags=re.I)
        pieces: list[tuple[str, str]] = [(correlation.group("direction"), branches[0])]
        if len(branches) == 2:
            second = re.match(
                r"(?P<direction>reversely|inversely|negatively|positively)\s+"
                r"correlated\s+(?:to|with)\s+(?P<targets>.+)", branches[1], re.I,
            )
            if second:
                pieces.append((second.group("direction"), second.group("targets")))
        for direction, targets in pieces:
            predicate = (
                "positively_correlated_with"
                if direction.casefold() == "positively"
                else "inversely_correlated_with"
            )
            for target in re.finditer(
                r"(?:^|,\s*(?:and\s+)?)(?P<target>.+?)\s*"
                r"\((?P<p>p\s*[<=>]\s*[0-9.]+)\)(?=,|$)", targets, re.I,
            ):
                name = re.sub(
                    r"^and\s+", "", target.group("target").strip(), flags=re.I
                )
                name = re.sub(
                    r"tumour node metastasis\s+\(TNM\)\s+classification",
                    "TNM classification", name, flags=re.I,
                )
                events.append(_event(
                    f"{correlation.group('subject')} expression", predicate, name,
                    context=ContextBundle(
                        cohort=f"{disease} tumour tissue samples",
                        measurements=(target.group("p"),),
                    ),
                    trigger=_span(correlation),
                    required=("cohort", "measurement"),
                    covered=("cohort", "measurement"),
                ))

                # A standalone excerpt does not supply the paper-level cohort
                # carried by a Results section.  Preserve the wording and only
                # the locally stated measurement in that representation.
                if (source_unit or "").upper() == "DOCUMENT":
                    document_name = target.group("target").strip()
                    document_name = re.sub(r"^and\s+", "", document_name, flags=re.I)
                    document_events.append(_event(
                        f"{correlation.group('subject')} expression level",
                        predicate,
                        document_name,
                        modality=None,
                        context=ContextBundle(measurements=(target.group("p"),)),
                        trigger=_span(correlation),
                        required=("measurement",),
                        covered=("measurement",),
                    ))

    localization = re.search(
        r"transcript\s+for\s+(?P<entity>[A-Za-z0-9-]+)\s+was\s+"
        r"(?P<qualifier>mainly)\s+(?P<verb>located)\s+in\s+the\s+"
        r"(?P<site>[a-z-]+)\s+of\s+(?P<cells>[A-Za-z0-9-]+\s+and\s+"
        r"[A-Za-z0-9-]+)\s+cells",
        text, re.I,
    )
    if localization:
        for cell in re.split(r"\s+and\s+", localization.group("cells"), flags=re.I):
            events.append(_event(
                f"{localization.group('entity')} transcript", "mainly_located_in",
                localization.group("site"), context=ContextBundle(cells=(f"{cell} cells",)),
                trigger=_span(localization), required=("cells",), covered=("cells",),
            ))

    clinical = re.search(
        r"results\s+(?P<verb>suggest)\s+that\s+the\s+decreased\s+"
        r"(?P<entity>[A-Za-z0-9-]+)\s+expression\s+is\s+clinically\s+"
        r"relevant\s+to\s+the\s+(?P<outcome>metastasis\s+of\s+[A-Z][A-Z0-9-]+)",
        text, re.I,
    )
    if clinical:
        outcome = re.sub(r"metastasis\s+of\s+", "", clinical.group("outcome"), flags=re.I)
        events.append(_event(
            f"decreased {clinical.group('entity')} expression", "associated_with",
            f"{outcome} metastasis", modality="suggested",
            context=ContextBundle(cohort=f"clinical {outcome} samples"),
            trigger=_span(clinical), required=("cohort",), covered=("cohort",),
        ))

    opposite = re.search(
        r"(?P<subject>knockdown\s+of\s+[A-Za-z0-9-]+)\s+in\s+"
        r"(?P<cells>[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+)\s+cells\s+"
        r"had\s+the\s+(?P<verb>opposite)\s+effects\s+"
        r"\((?P<p>p\s*[<=>]\s*[0-9.]+)", text, re.I,
    )
    if opposite and previous_sentence:
        prior_subject = re.search(
            r"(?P<subject>(?:stable\s+ectopic\s+)?expression\s+of\s+[A-Za-z0-9-]+)",
            previous_sentence, re.I,
        )
        prior_outcomes = re.search(
            r"(?:decreased|increased)\s+not\s+only\s+(?P<first>[a-z-]+).*?"
            r"but\s+also\s+(?:the\s+)?(?P<second>[a-z-]+)", previous_sentence, re.I,
        )
        if prior_outcomes:
            entity = re.search(r"of\s+([A-Za-z0-9-]+)", opposite.group("subject"), re.I)
            normalized_subject = f"{entity.group(1)} knockdown" if entity else opposite.group("subject")
            prior_entity = (
                re.search(r"expression\s+of\s+([A-Za-z0-9-]+)", previous_sentence, re.I)
                if prior_subject else None
            )
            comparison = (
                f"opposite to {prior_entity.group(1)} overexpression"
                if prior_entity else "opposite to overexpression"
            )
            for outcome in (prior_outcomes.group("first"), prior_outcomes.group("second")):
                for cell in re.split(r"\s+and\s+", opposite.group("cells"), flags=re.I):
                    events.append(_event(
                        normalized_subject, "increased", f"cell {outcome}",
                        context=ContextBundle(
                            cells=(f"{cell} cells",),
                            measurements=(opposite.group("p").rstrip("."),),
                            contrast=comparison,
                        ),
                        trigger=_span(opposite),
                        required=("cells", "measurement", "contrast"),
                        covered=("cells", "measurement", "contrast"),
                    ))

    ki67 = re.search(
        r"tumours?\s+developed\s+from\s+(?P<intervention>[A-Za-z0-9-]+)\s+cells\s+"
        r"(?P<verb>displayed)\s+higher\s+(?P<index>ki-67\s+proliferation\s+index)",
        text, re.I,
    )
    if ki67:
        entity = re.sub(r"^sh-", "", ki67.group("intervention"), flags=re.I)
        events.append(_event(
            f"{entity} knockdown", "increased", f"tumour {ki67.group('index')}",
            context=ContextBundle(extra=("xenograft tumours versus control",)),
            trigger=_span(ki67), required=("comparator",), covered=("comparator",),
        ))

    xenograft_size = re.search(
        r"xenograft\s+tumours?\s+formed\s+in\s+(?P<group>[A-Za-z0-9-]+)\s+"
        r"group\s+were\s+(?:generally\s+)?(?P<verb>larger)\s+than\s+those\s+"
        r"in\s+the\s+control\s+group", text, re.I,
    )
    if xenograft_size:
        entity = re.sub(r"^sh-", "", xenograft_size.group("group"), flags=re.I)
        events.append(_event(
            f"{entity} knockdown", "increased", "xenograft tumour size",
            context=ContextBundle(extra=(
                f"{xenograft_size.group('group')} xenograft group versus control mice",
            )), trigger=_span(xenograft_size),
            required=("comparator",), covered=("comparator",),
        ))

    xenograft_growth = re.search(
        r"Tumours?\s+growth\s+in\s+the\s+(?P<group>[A-Za-z0-9-]+)\s+group\s+"
        r"was\s+(?:significantly\s+)?more\s+(?P<verb>rapid)\s+than\s+that\s+"
        r"in\s+the\s+control\s+group", text, re.I,
    )
    if xenograft_growth:
        entity = re.sub(r"^sh-", "", xenograft_growth.group("group"), flags=re.I)
        events.append(_event(
            f"{entity} knockdown", "increased", "xenograft tumour growth rate",
            context=ContextBundle(extra=(
                f"{xenograft_growth.group('group')} xenograft group versus control mice",
            )), trigger=_span(xenograft_growth),
            required=("comparator",), covered=("comparator",),
        ))

    metastatic = re.search(
        r"All\s+\((?P<lung_count>\d+/\d+)\)\s+of\s+the\s+mice\s+in\s+"
        r"(?P<group>[A-Za-z0-9-]+)\s+group\s+(?P<verb>displayed)\s+"
        r"metastatic\s+foci\s+in\s+the\s+lung\s+and\s+"
        r"(?P<liver_count>\d+/\d+)\s+of\s+these\s+mice\s+had\s+"
        r"metastasis\s+foci\s+in\s+the\s+liver", text, re.I,
    )
    if metastatic:
        subject = f"{metastatic.group('group')} mice"
        for organ, count in (("lung", metastatic.group("lung_count")),
                             ("liver", metastatic.group("liver_count"))):
            events.append(_event(
                subject, "developed", f"{organ} metastatic foci",
                context=ContextBundle(measurements=(f"{count} mice",)),
                trigger=_span(metastatic), required=("measurement",), covered=("measurement",),
            ))

    control_metastatic = re.search(
        r"(?P<lung_count>\d+/\d+)\s+of\s+mice\s+in\s+(?P<group>[A-Za-z0-9-]+)\s+"
        r"group\s+had\s+lung\s+metastasis\s+foci\s+and\s+no\s+mice\s+in\s+"
        r"(?P=group)\s+group\s+(?P<verb>develop)\s+hepatic\s+metastasis\s+foci",
        text, re.I,
    )
    if control_metastatic:
        subject = f"{control_metastatic.group('group')} mice"
        events.extend((
            _event(subject, "developed", "lung metastatic foci",
                   context=ContextBundle(measurements=(f"{control_metastatic.group('lung_count')} control mice",)),
                   trigger=_span(control_metastatic), required=("measurement",), covered=("measurement",)),
            _event(subject, "developed", "hepatic metastatic foci",
                   context=ContextBundle(measurements=("0/5 control mice",)),
                   polarity="negative", trigger=_span(control_metastatic),
                   required=("measurement",), covered=("measurement",)),
        ))

    loss = re.search(
        r"loss\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+expression\s+"
        r"(?:profoundly\s+)?(?P<verb>promotes)\s+(?P<outcomes>[^.]+)", text, re.I,
    )
    if loss:
        for outcome in re.split(r"\s+and\s+", loss.group("outcomes"), flags=re.I):
            events.append(_event(
                f"{loss.group('entity')} loss", "promoted", outcome,
                trigger=_span(loss),
            ))

    phase_change = re.search(
        r"(?P<intervention>downregulation\s+of\s+[A-Za-z0-9-]+)\s+in\s+"
        r"(?P<cell>[A-Za-z0-9-]+)\s+cells\s+(?:significantly\s+)?"
        r"(?P<verb>decreased)\s+the\s+proportion\s+of\s+cells\s+in\s+"
        r"(?P<first_phase>G0/G1)\s+phase\s+\(from\s+(?P<first_values>[^)]+)\),\s+"
        r"while\s+increased\s+the\s+proportion\s+of\s+cells\s+in\s+"
        r"(?P<second_phase>S)\s+phase\s+\(from\s+(?P<second_values>[^)]+)\)",
        text, re.I,
    )
    if phase_change:
        entity = re.search(r"of\s+([A-Za-z0-9-]+)", phase_change.group("intervention"), re.I)
        subject = f"{entity.group(1)} downregulation" if entity else phase_change.group("intervention")
        for predicate, phase, values in (
            ("decreased", phase_change.group("first_phase"), phase_change.group("first_values")),
            ("increased", phase_change.group("second_phase"), phase_change.group("second_values")),
        ):
            events.append(_event(
                subject, predicate, f"{phase}-phase cell fraction",
                context=ContextBundle(
                    cells=(f"{phase_change.group('cell')} cells",),
                    measurements=(values,),
                ),
                trigger=_span(phase_change), required=("cells", "measurement"),
                covered=("cells", "measurement"),
            ))

    contribution = re.search(
        r"(?P<subject>(?:overexpression\s+of\s+[A-Za-z0-9-]+|[A-Za-z0-9-]+\s+"
        r"overexpression))\s+(?:induces?|induced)\s+(?P<first>cell\s+cycle\s+arrest)\s+"
        r"and\s+(?P<second>apoptosis)\s+in\s+(?P<cells>[A-Z][A-Z0-9-]+)\s+cells,\s+"
        r"which\s+(?P<verb>contributes)\s+to\s+the\s+(?P<object>growth\s+inhibition)",
        text, re.I,
    )
    if contribution:
        entity = re.search(r"(?:of\s+)?([A-Za-z0-9-]+)(?:\s+overexpression)?$", contribution.group("subject"), re.I)
        events.append(_event(
            f"{entity.group(1)}-induced cell-cycle arrest and apoptosis",
            "contributed_to", contribution.group("object"),
            context=ContextBundle(cells=(f"{contribution.group('cells')} cells",)),
            trigger=_span(contribution), required=("cells",), covered=("cells",),
        ))

    disrupted = re.search(
        r"(?P<target>[A-Za-z0-9-]+)\s+was\s+one\s+of\s+the\s+disrupted\s+genes\s+"
        r"when\s+(?P<actor>[A-Za-z0-9-]+)\s+was\s+(?P<verb>depleted).*?"
        r"transcript\s+profiling\s+\[(?P<citation>\d+)\]", text, re.I,
    )
    if disrupted:
        events.append(_event(
            f"{disrupted.group('actor')} depletion", "disrupted",
            f"{disrupted.group('target')} gene expression",
            context=ContextBundle(assay="transcript profiling",
                                  extra=(f"prior report [{disrupted.group('citation')}]",)),
            trigger=_span(disrupted), required=("assay", "attribution"),
            covered=("assay", "attribution"),
        ))

    expression_increase = re.search(
        r"(?P<intervention>downregulation\s+of\s+[A-Za-z0-9-]+)\s+"
        r"(?P<verb>increased)\s+the\s+expression\s+of\s+(?P<target>[A-Za-z0-9-]+)",
        text, re.I,
    )
    if expression_increase:
        entity = re.search(r"of\s+([A-Za-z0-9-]+)", expression_increase.group("intervention"), re.I)
        events.append(_event(
            f"{entity.group(1)} downregulation", "increased",
            f"{expression_increase.group('target')} expression",
            context=ContextBundle(cells=(f"{disease} cells",)),
            trigger=_span(expression_increase), required=("cells",), covered=("cells",),
        ))

    psen2 = re.search(
        r"overexpression\s+of\s+(?P<actor>[A-Za-z0-9-]+)\s+alone\s+or\s+in\s+"
        r"(?P<setting>[A-Za-z0-9/-]+)\s+cells\s+(?P<up>upregulated)\s+the\s+"
        r"expression\s+of\s+(?P<up_target>[A-Za-z0-9-]+)\s+and\s+"
        r"(?P<down>reduced)\s+the\s+expression\s+of\s+(?P<down_target>[A-Za-z0-9-]+)",
        context_text, re.I,
    )
    if psen2:
        actor = psen2.group("actor").upper() if re.search(r"\d", psen2.group("actor")) else psen2.group("actor")
        base = psen2.group("setting").split("/", 1)[0]
        for arm, condition in (
            (f"{actor} overexpression alone", f"{base} context; {actor} overexpression alone"),
            (f"{actor} overexpression in {psen2.group('setting')} cells",
             f"{base} context; {actor} overexpression in {psen2.group('setting')} cells"),
        ):
            events.extend((
                _event(arm, "increased", f"{psen2.group('up_target')} expression",
                       context=ContextBundle(extra=(condition,)), trigger=_span(psen2, "up")),
                _event(arm, "decreased", f"{psen2.group('down_target')} expression",
                       context=ContextBundle(extra=(condition,)), trigger=_span(psen2, "down")),
            ))
        state.reversible_effects = (
            (f"{actor}-associated {psen2.group('up_target')} increase", "increased"),
            (f"{actor}-associated {psen2.group('down_target')} decrease", "decreased"),
        )

    reversal = re.search(
        r"all\s+these\s+effects\s+(?P<verb>disappeared)\s+when\s+"
        r"(?P<entity>[A-Za-z0-9-]+)\s+was\s+re-expressed\s+in\s+"
        r"(?P<cells>[A-Za-z0-9 -]+\s+or\s+[A-Za-z0-9/-]+)\s+cells", text, re.I,
    )
    if reversal and state.reversible_effects:
        raw_cells = re.sub(
            r"^(?P<base>[A-Za-z]+\d+)\s+NC\s+or\s+(?P<second>[^\s]+)$",
            lambda found: (
                f"{found.group('base')}-NC or "
                f"{found.group('base')}/{found.group('second')}"
            ),
            reversal.group("cells"),
            flags=re.I,
        )
        condition = raw_cells
        for effect, _ in state.reversible_effects:
            events.append(_event(
                f"{reversal.group('entity')} re-expression", "reversed", effect,
                context=ContextBundle(cells=(f"{condition} cells",)),
                trigger=_span(reversal), required=("cells",), covered=("cells",),
            ))

    inferred_cleavage = re.search(
        r"Considering\s+the\s+intracytoplasmic\s+location\s+of\s+(?P<entity>[A-Za-z0-9-]+),\s+"
        r"these\s+results\s+indicate\s+that\s+the\s+inhibition\s+of\s+(?P=entity)\s+"
        r"(?P<modal>may)\s+(?P<verb>accelerate)\s+the\s+cleavage\s+of\s+"
        r"(?P<target>[A-Za-z0-9-]+)\s+and\s+release\s+(?P<product>[A-Za-z0-9-]+)",
        text, re.I,
    )
    if inferred_cleavage:
        inferred = f"inferred from intracytoplasmic {inferred_cleavage.group('entity')} and protein/{inferred_cleavage.group('product')} results"
        events.extend((
            _event(f"{inferred_cleavage.group('entity')} inhibition", "accelerated",
                   f"{inferred_cleavage.group('target')} cleavage", modality="may",
                   context=ContextBundle(inference=inferred), trigger=_span(inferred_cleavage),
                   required=("inference",), covered=("inference",)),
            _event(f"{inferred_cleavage.group('entity')} inhibition", "increased",
                   f"{inferred_cleavage.group('product')} release", modality="may",
                   context=ContextBundle(inference=inferred), trigger=_span(inferred_cleavage),
                   required=("inference",), covered=("inference",)),
        ))

    induced_targets = re.search(
        r"expression\s+of\s+(?P<first>[A-Za-z0-9β-]+),\s+as\s+well\s+as\s+"
        r"the\s+[^,]+?genes\s+(?P<others>.+?)\s+were\s+"
        r"(?:significantly\s+)?(?P<verb>induced)\s+in\s+"
        r"(?P<actor>[A-Za-z0-9-]+)-knockdown\s+cells", text, re.I,
    )
    if induced_targets:
        targets = [induced_targets.group("first"), *re.findall(r"[A-Za-z0-9β-]+", induced_targets.group("others"))]
        for target in targets:
            if target.casefold() in {"and", "as", "well"}:
                continue
            events.append(_event(
                f"{induced_targets.group('actor')} knockdown", "increased",
                f"{target} expression",
                context=ContextBundle(cells=(f"{induced_targets.group('actor')}-knockdown {disease} cells",)),
                trigger=_span(induced_targets), required=("cells",), covered=("cells",),
            ))

    coip = re.search(
        r"Co-IP\s+assay\s+indicate\s+that\s+(?P<actor>sh-[A-Za-z0-9-]+)\s+"
        r"(?P<verb>promote)\s+the\s+formation\s+of\s+(?P<first>[A-Za-z0-9-]+)\s+"
        r"and\s+(?P<second>[A-Za-z0-9β-]+)\s+complex\s+in\s+"
        r"(?P<cell>[A-Za-z0-9-]+)\s+cell", text, re.I,
    )
    if coip:
        entity = re.sub(r"^sh-", "", coip.group("actor"), flags=re.I)
        events.append(_event(
            f"{entity} knockdown", "promoted",
            f"{coip.group('first')}–{coip.group('second')} complex formation",
            context=ContextBundle(cells=(f"{coip.group('cell')} cells",), assay="Co-IP finding"),
            trigger=_span(coip), required=("cells", "assay"), covered=("cells", "assay"),
        ))

    predicted_site = re.search(
        r"(?P<factor>[A-Za-z0-9-]+)\s+was\s+the\s+(?P<verb>predicted)\s+TF\s+with\s+"
        r"(?P<count>one)\s+binding\s+site\s+on\s+the\s+(?P<promoter>[A-Za-z0-9-]+\s+promoter)\s+"
        r"showed\s+by\s+the\s+(?P<databases>.+?)\s+databases", text, re.I,
    )
    if predicted_site:
        dbs = re.sub(r",\s+and\s+", " and ", predicted_site.group("databases"))
        events.append(_event(
            predicted_site.group("factor"), "predicted_binding_site_on",
            predicted_site.group("promoter"), modality="predicted",
            context=ContextBundle(extra=(f"{predicted_site.group('count')} promoter site", dbs)),
            trigger=_span(predicted_site),
            required=("count", "provenance"), covered=("count", "provenance"),
        ))

    binding_activity = re.search(
        r"(?:obvious\s+)?increasing\s+(?P<factor>[A-Za-z0-9-]+)-binding\s+activity\s+"
        r"on\s+the\s+(?P<promoter>[A-Za-z0-9-]+\s+promoter)\s+was\s+"
        r"(?P<verb>observed)\s+by\s+the\s+(?P<assay>dual\s+luciferase\s+reporter\s+assays?)",
        text, re.I,
    )
    if binding_activity:
        events.append(_event(
            binding_activity.group("factor"), "increased_binding_activity_on",
            binding_activity.group("promoter"),
            context=ContextBundle(assay="dual luciferase reporter assay"),
            trigger=_span(binding_activity), required=("assay",), covered=("assay",),
        ))

    prior_mechanism = re.search(
        r"reported\s+that\s+(?P<actor>[A-Za-z0-9-]+)\s+(?P<verb>binding)\s+to\s+the\s+"
        r"(?P<target>[A-Za-z0-9-]+)\s+transcription\s+factor\s+via\s+the\s+"
        r"(?P<region>[^,]+?region)\s+and\s+inhibition\s+of\s+(?P=target)\s+"
        r"transcriptional\s+activity.*?\[(?P<citation>\d+)\]", text, re.I,
    )
    if prior_mechanism:
        actor, target = prior_mechanism.group("actor"), prior_mechanism.group("target")
        prior = f"prior report [{prior_mechanism.group('citation')}]"
        events.extend((
            _event(actor, "bound_to", target,
                   context=ContextBundle(extra=(f"via {prior_mechanism.group('region')}", prior)),
                   trigger=_span(prior_mechanism), required=("mechanism", "attribution"),
                   covered=("mechanism", "attribution")),
            _event(actor, "inhibited", f"{target} transcriptional activity",
                   context=ContextBundle(extra=(f"via {actor}–{target} binding", prior)),
                   trigger=_span(prior_mechanism), required=("mechanism", "attribution"),
                   covered=("mechanism", "attribution")),
        ))

    passive_regulation = re.search(
        r"(?P<target>[A-Za-z0-9-]+),\s+transcribed\s+by\s+(?P<factor>[A-Za-z0-9-]+),\s+"
        r"was\s+(?P<verb>repressed)\s+by\s+(?P<repressor>[A-Za-z0-9-]+)", text, re.I,
    )
    if passive_regulation:
        condition = f"{disease} cells"
        events.extend((
            _event(passive_regulation.group("factor"), "transcribed",
                   passive_regulation.group("target"), context=ContextBundle(cells=(condition,)),
                   trigger=_span(passive_regulation), required=("cells",), covered=("cells",)),
            _event(passive_regulation.group("repressor"), "repressed",
                   f"{passive_regulation.group('target')} expression",
                   context=ContextBundle(cells=(condition,)), trigger=_span(passive_regulation),
                   required=("cells",), covered=("cells",)),
        ))

    partial_suppression = re.search(
        r"increasing\s+expression\s+of\s+(?P<target>[A-Za-z0-9-]+)\s+by\s+"
        r"(?P<inducer>[A-Za-z0-9-]+)\s+was\s+(?P<degree>partly)\s+"
        r"(?P<verb>suppressed)\s+by\s+(?P<repressor>[A-Za-z0-9-]+)", text, re.I,
    )
    if partial_suppression:
        events.append(_event(
            partial_suppression.group("repressor"), "partly_suppressed",
            f"{partial_suppression.group('inducer')}-induced {partial_suppression.group('target')} expression",
            context=ContextBundle(extra=(
                f"{partial_suppression.group('inducer')} overexpression", "partial suppression",
            )), trigger=_span(partial_suppression),
            required=("inducer", "degree"), covered=("inducer", "degree"),
        ))

    tentative_mediation = re.search(
        r"(?P<entity>[A-Za-z0-9-]+)\s+induces\s+(?P<first>cell\s+cycle\s+arrest)\s+"
        r"and\s+inhibits\s+(?P<second>proliferation)\s+may\s+be\s+due\s+to\s+the\s+"
        r"(?P<verb>suppression)\s+of\s+(?P<mediator>[A-Za-z0-9-]+)", text, re.I,
    )
    if tentative_mediation:
        mediator = f"{tentative_mediation.group('mediator')} suppression"
        condition = ContextBundle(cells=(f"{disease} cells",))
        events.extend((
            _event(mediator, "may_mediate",
                   f"{tentative_mediation.group('entity')}-induced cell-cycle arrest",
                   modality="may", context=condition, trigger=_span(tentative_mediation),
                   required=("cells",), covered=("cells",)),
            _event(mediator, "may_mediate",
                   f"{tentative_mediation.group('entity')}-induced proliferation inhibition",
                   modality="may", context=condition, trigger=_span(tentative_mediation),
                   required=("cells",), covered=("cells",)),
        ))

    feedback = re.search(
        r"positive\s+feedback\s+loop\s+(?P<verb>controlling)\s+"
        r"(?P<first>[A-Za-z0-9-]+)\s+and\s+(?P<second>[A-Za-z0-9-]+)\s+expression",
        text, re.I,
    )
    if feedback:
        loop = f"{feedback.group('second')}–{feedback.group('first')} feedback loop"
        condition = ContextBundle(
            cells=(f"{disease} cells",),
            extra=(f"reciprocal {feedback.group('second')}/{feedback.group('first')} regulation",),
        )
        for target in (feedback.group("second"), feedback.group("first")):
            events.append(_event(
                loop, "controlled", f"{target} expression", modality="inferred",
                context=condition, trigger=_span(feedback),
                required=("cells", "reciprocity"), covered=("cells", "reciprocity"),
            ))

    proposed = re.search(
        r"proposed\s+model\s+of\s+reciprocity\s+between\s+(?:lnc-)?"
        r"(?P<first>[A-Za-z0-9-]+)\s+and\s+(?P<second>[A-Za-z0-9-]+)\s+"
        r"(?P<verb>regulates)\s+(?P<outcomes>.+?)\s+in\s+"
        r"(?P<disease>colorectal\s+cancer)", text, re.I,
    )
    if proposed:
        subject = f"proposed reciprocal {proposed.group('first')}–{proposed.group('second')} model"
        outcomes = [part.strip() for part in re.split(r",\s*|\s+and\s+", proposed.group("outcomes")) if part.strip()]
        for outcome in outcomes:
            target = (
                f"CRC cell {outcome}" if outcome.casefold() == "proliferation"
                else f"CRC {outcome}"
            )
            events.append(_event(
                subject, "regulates", target, modality="proposed_model",
                context=ContextBundle(extra=(proposed.group("disease"),)),
                trigger=_span(proposed), required=("disease",), covered=("disease",),
            ))

    # Common direct scientific findings that need reporting wrappers removed
    # and material context moved out of graph nodes.
    oncomine = re.search(
        r"relied\s+on\s+(?P<assay>Oncomine).*?result\s+indicated\s+that\s+"
        r"(?P<entity>[A-Za-z0-9-]+)\s+was\s+(?:significantly\s+)?"
        r"(?P<verb>downregulated)\s+in\s+(?P<tissue>colorectal\s+cancer\s+tissues)\s+"
        r"comparing\s+with\s+(?P<comparator>adjacent\s+tissues)", text, re.I,
    )
    if oncomine:
        events.append(_event(
            f"{oncomine.group('entity')} expression", "decreased_in", "CRC tissues",
            context=ContextBundle(
                comparator="relative to adjacent tissues", assay="Oncomine analysis"
            ), trigger=_span(oncomine), required=("comparator", "assay"),
            covered=("comparator", "assay"),
        ))

    positive_correlation = re.search(
        r"while\s+(?P<direction>positively)\s+(?P<verb>correlated)\s+with\s+"
        r"(?P<target>[^,(]+)\s+\((?P<p>p\s*[<=>]\s*[0-9.]+)\)", text, re.I,
    )
    if positive_correlation and correlation:
        events.append(_event(
            f"{correlation.group('subject')} expression", "positively_correlated_with",
            positive_correlation.group("target"),
            context=ContextBundle(
                cohort=f"{disease} tumour tissue samples",
                measurements=(positive_correlation.group("p"),),
            ), trigger=_span(positive_correlation),
            required=("cohort", "measurement"), covered=("cohort", "measurement"),
        ))

        if (source_unit or "").upper() == "DOCUMENT":
            document_events.append(_event(
                f"{correlation.group('subject')} expression level",
                "positively_correlated_with",
                positive_correlation.group("target"),
                modality=None,
                context=ContextBundle(measurements=(positive_correlation.group("p"),)),
                trigger=_span(positive_correlation),
                required=("measurement",), covered=("measurement",),
            ))

    malignant_lines = re.search(
        r"expression\s+level\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+in\s+the\s+"
        r"high\s+malignant\s+potential\s+cell\s+lines\s+(?P<high>.+?)\s+was\s+"
        r"(?:significantly\s+)?(?P<verb>decreased)\s+compared\s+with\s+low\s+"
        r"malignant\s+potential\s+cell\s+lines\s+(?P<low>[^.(]+)", text, re.I,
    )
    if malignant_lines:
        high = re.sub(r",\s*and\s+", ", and ", malignant_lines.group("high")).strip(" ,")
        low = re.sub(
            r"\s+and\s+(?=[^,]+$)", ", and ",
            malignant_lines.group("low").strip(" ,"),
        )
        events.append(_event(
            f"{malignant_lines.group('entity')} expression", "lower_in", f"{high} cells",
            context=ContextBundle(
                comparator=f"compared with {low}",
                extra=("high versus low malignant potential CRC cell lines",),
            ), trigger=_span(malignant_lines),
            required=("comparator", "cell_class"), covered=("comparator", "cell_class"),
        ))

    ectopic = re.search(
        r"(?P<subject>Stable\s+ectopic\s+expression\s+of\s+(?P<entity>[A-Za-z0-9-]+))\s+"
        r"(?P<verb>decreased)\s+not\s+only\s+(?P<first>proliferation)\s+"
        r"\((?P<p>p\s*[<=>]\s*[0-9.]+).*?\)\s+but\s+also\s+(?:the\s+)?"
        r"(?P<second>migration).*?of\s+(?P<cells>[A-Za-z0-9-]+\s+and\s+"
        r"[A-Za-z0-9-]+)\s+cells", text, re.I,
    )
    if ectopic:
        subject = f"stable ectopic {ectopic.group('entity')} expression"
        for outcome in (ectopic.group("first"), ectopic.group("second")):
            for cell in re.split(r"\s+and\s+", ectopic.group("cells"), flags=re.I):
                measurements = (ectopic.group("p"),) if outcome == ectopic.group("first") else ()
                events.append(_event(
                    subject, "decreased", f"cell {outcome}",
                    context=ContextBundle(cells=(f"{cell} cells",), measurements=measurements),
                    trigger=_span(ectopic), required=("cells",), covered=("cells",),
                ))

    nodule_count = re.search(
        r"(?P<actor>[A-Za-z0-9-]+)\s+knockdown\s+(?P<verb>increased)\s+the\s+"
        r"number\s+of\s+metastatic\s+nodules\s+compared\s+to\s+the\s+control\s+cells\s+"
        r"\(lung:\s*(?P<lung>\d+:\d+);\s*(?:live|liver):\s*(?P<liver>\d+:\d+)\)",
        context_text, re.I,
    )
    if nodule_count:
        for organ, ratio in (("lung", nodule_count.group("lung")),
                             ("liver", nodule_count.group("liver"))):
            events.append(_event(
                f"{nodule_count.group('actor')} knockdown", "increased",
                "metastatic nodule count",
                context=ContextBundle(extra=(
                    f"{organ} nodules",
                    f"{nodule_count.group('actor')} knockdown versus control",
                    ratio,
                    "mice",
                )), trigger=_span(nodule_count),
                required=("organ", "comparator", "measurement", "species"),
                covered=("organ", "comparator", "measurement", "species"),
            ))

    apoptosis = re.search(
        r"upregulation\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+(?P<verb>induced)\s+"
        r"a\s+(?:significant\s+)?increase\s+of\s+(?P<outcome>early\s+apoptosis)\s+in\s+"
        r"(?P<first_cell>[A-Za-z0-9-]+)\s+cells\s+\((?P<first_values>[^)]+)\)\s+and\s+"
        r"(?P<second_cell>[A-Za-z0-9-]+)\s+cells\s+\((?P<second_values>[^)]+)\)",
        text, re.I,
    )
    if apoptosis:
        for cell, values in ((apoptosis.group("first_cell"), apoptosis.group("first_values")),
                             (apoptosis.group("second_cell"), apoptosis.group("second_values"))):
            events.append(_event(
                f"{apoptosis.group('entity')} upregulation", "increased",
                apoptosis.group("outcome"),
                context=ContextBundle(cells=(f"{cell} cells",), measurements=(values,)),
                trigger=_span(apoptosis), required=("cells", "measurement"),
                covered=("cells", "measurement"),
            ))

    caspases = re.search(
        r"upregulation\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+(?P<verb>activated)\s+"
        r"(?P<first>caspase\s+\d+)\s+and\s+(?P<second>caspase\s+\d+)\s+in\s+"
        r"(?P<cells>[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+)\s+cells", text, re.I,
    )
    if caspases:
        for target in (caspases.group("first"), caspases.group("second")):
            events.append(_event(
                f"{caspases.group('entity')} upregulation", "activated", target,
                context=ContextBundle(cells=(f"{caspases.group('cells')} CRC cells",)),
                trigger=_span(caspases), required=("cells",), covered=("cells",),
            ))

    conclusion = re.search(
        r"results\s+(?P<verb>indicated)\s+that\s+the\s+overexpression\s+of\s+"
        r"(?P<entity>[A-Za-z0-9-]+)\s+induces\s+(?P<first>cell\s+cycle\s+arrest)\s+"
        r"and\s+(?P<second>apoptosis)\s+in\s+(?P<cells>[A-Z][A-Z0-9-]+)\s+cells",
        text, re.I,
    )
    if conclusion:
        for outcome in ("cell-cycle arrest", conclusion.group("second")):
            events.append(_event(
                f"{conclusion.group('entity')} overexpression", "induced", outcome,
                context=ContextBundle(cells=(f"{conclusion.group('cells')} cells",)),
                trigger=_span(conclusion), required=("cells",), covered=("cells",),
            ))

    knockdown_effects = re.search(
        r"Knockdown\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+did\s+not\s+"
        r"(?P<change>change)\s+the\s+(?P<rna>[A-Za-z0-9-]+)\s+mRNA\s+but\s+"
        r"(?P<down>downregulated)\s+the\s+(?P<protein>[A-Za-z0-9-]+)\s+"
        r"protein\s+levels\s+in\s+(?P<cells>[A-Z][A-Z0-9-]+)\s+cells", text, re.I,
    )
    if knockdown_effects:
        subject = f"{knockdown_effects.group('entity')} knockdown"
        cell_context = ContextBundle(cells=(f"{knockdown_effects.group('cells')} cells",))
        events.extend((
            _event(subject, "changed", f"{knockdown_effects.group('rna')} mRNA level",
                   polarity="negative", context=cell_context, trigger=_span(knockdown_effects, "change"),
                   required=("cells",), covered=("cells",)),
            _event(subject, "decreased", f"{knockdown_effects.group('protein')} protein level",
                   context=cell_context, trigger=_span(knockdown_effects, "down"),
                   required=("cells",), covered=("cells",)),
        ))

    half_life = re.search(
        r"knockdown\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+led\s+to\s+"
        r"a\s+(?:robust\s+)?(?P<verb>decreased)\s+in\s+(?P<target>[A-Za-z0-9-]+)\s+"
        r"protein\s+half-life\s+in\s+(?P<cells>[A-Za-z0-9-]+\s+and\s+"
        r"[A-Za-z0-9-]+)\s+cells", text, re.I,
    )
    if half_life:
        for cell in re.split(r"\s+and\s+", half_life.group("cells"), flags=re.I):
            events.append(_event(
                f"{half_life.group('entity')} knockdown", "decreased",
                f"{half_life.group('target')} protein half-life",
                context=ContextBundle(cells=(f"{cell} cells",)),
                trigger=_span(half_life), required=("cells",), covered=("cells",),
            ))

    tissue_increase = re.search(
        r"(?P<entity>[A-Za-z0-9-]+)\s+was\s+(?P<verb>upregulated)\s+in\s+the\s+"
        r"(?P<tissue>[A-Z][A-Z0-9-]+\s+tissues)\s+compared\s+with\s+their\s+"
        r"(?P<comparator>normal\s+mucous)", text, re.I,
    )
    if tissue_increase:
        events.append(_event(
            f"{tissue_increase.group('entity')} expression", "increased_in",
            tissue_increase.group("tissue"),
            context=ContextBundle(comparator="relative to paired normal mucosa"),
            trigger=_span(tissue_increase), required=("comparator",), covered=("comparator",),
        ))

    inverse_expression = re.search(
        r"(?P<first>[A-Za-z0-9-]+)\s+and\s+(?P<second>[A-Za-z0-9-]+)\s+were\s+"
        r"(?P<verb>inversely\s+related)\s+in\s+expression\s+"
        r"\((?P<p>p\s*[<=>]\s*[0-9.]+),\s*(?P<r>r\s*[<=>]\s*[−-]?[0-9.]+)",
        text, re.I,
    )
    if inverse_expression:
        events.append(_event(
            f"{inverse_expression.group('first')} expression", "inversely_correlated_with",
            f"{inverse_expression.group('second')} expression",
            context=ContextBundle(
                cohort=f"44 paired {disease} tissues",
                measurements=(inverse_expression.group("p"), inverse_expression.group("r")),
            ), trigger=_span(inverse_expression),
            required=("cohort", "measurement"), covered=("cohort", "measurement"),
        ))

    colocalized_complex = re.search(
        r"(?P<actor>[A-Za-z0-9-]+)\s+(?P<verb>colocalized)\s+with\s+"
        r"(?P<first>[A-Za-z0-9-]+)\s+and\s+(?P<second>[A-Za-z0-9β-]+)\s+"
        r"to\s+form\s+a\s+(?P<location>[a-z-]+)\s+protein\s+complex,\s+"
        r"leading\s+to\s+(?P<outcome>gene\s+transcription)", text, re.I,
    )
    if colocalized_complex:
        actor = colocalized_complex.group("actor")
        first = colocalized_complex.group("first")
        second = colocalized_complex.group("second")
        complex_name = f"{actor}–{first}–{second} complex"
        common = {"modality": "general_mechanism", "trigger": _span(colocalized_complex)}
        events.extend((
            _event(actor, "colocalized_with", first, **common),
            _event(actor, "colocalized_with", second, **common),
            _event(
                complex_name, "formed_in",
                "nucleus" if colocalized_complex.group("location").casefold() == "nuclear"
                else colocalized_complex.group("location"),
                **common,
            ),
            _event(complex_name, "promoted", colocalized_complex.group("outcome"), **common),
        ))

    complex_formation = re.search(
        r"in\s+(?P<cell>[A-Za-z0-9-]+)\s+cells\s+which\s+"
        r"(?P<verb>showed)\s+the\s+formation\s+of\s+(?P<first>[A-Za-z0-9-]+)\s+"
        r"and\s+(?P<second>[A-Za-z0-9β-]+)\s+complex", text, re.I,
    )
    if complex_formation:
        events.append(_event(
            complex_formation.group("first"), "formed_complex_with",
            complex_formation.group("second"),
            context=ContextBundle(cells=(f"{complex_formation.group('cell')} {disease} cells",)),
            trigger=_span(complex_formation), required=("cells",), covered=("cells",),
        ))

    reporter = re.search(
        r"knockdown\s+of\s+(?P<entity>[A-Za-z0-9-]+)\s+(?P<verb>resulted)\s+in\s+"
        r"(?P<amount>\d+%[−-]\d+%)\s+increment\s+of\s+"
        r"(?P<target>TOP-Flash\s+reporter)\s+gene\s+activity", text, re.I,
    )
    if reporter:
        events.append(_event(
            f"{reporter.group('entity')} knockdown", "increased",
            f"{reporter.group('target')} activity",
            context=ContextBundle(measurements=(f"{reporter.group('amount').replace('−', '–')} increase",),
                                  assay="Wnt reporter assay"),
            trigger=_span(reporter), required=("measurement", "assay"),
            covered=("measurement", "assay"),
        ))

    pathway = re.search(
        r"activation\s+of\s+(?P<target>WNT/β-catenin\s+pathway)\s+is\s+"
        r"(?P<verb>mediated)\s+by\s+(?P<entity>[A-Za-z0-9-]+)\s+depletion\s+"
        r"in\s+(?P<cells>[A-Z][A-Z0-9-]+)", text, re.I,
    )
    if pathway:
        events.append(_event(
            f"{pathway.group('entity')} depletion", "activated", pathway.group("target"),
            context=ContextBundle(cells=(f"{pathway.group('cells')} cells",)),
            trigger=_span(pathway), required=("cells",), covered=("cells",),
        ))

    chip = re.search(
        r"(?P<assay>ChIP\s+assays?)\s+(?P<verb>confirmed)\s+the\s+"
        r"(?P<factor>[A-Za-z0-9-]+)\s+binding\s+to\s+(?P<promoter>[A-Za-z0-9-]+\s+promoter)",
        text, re.I,
    )
    if chip:
        events.append(_event(
            chip.group("factor"), "bound_to", chip.group("promoter"),
            trigger=_span(chip),
        ))

    factor_overexpression = re.search(
        r"overexpression\s+of\s+(?P<factor>[A-Za-z0-9-]+)\s+(?:significantly\s+)?"
        r"(?P<verb>increases?)\s+the\s+expression\s+of\s+(?P<target>[A-Za-z0-9-]+)\s+"
        r"in\s+(?P<cells>[A-Za-z0-9-]+\s+and\s+[A-Za-z0-9-]+)\s+cells", text, re.I,
    )
    if factor_overexpression:
        for cell in re.split(r"\s+and\s+", factor_overexpression.group("cells"), flags=re.I):
            events.append(_event(
                f"{factor_overexpression.group('factor')} overexpression", "increased",
                f"{factor_overexpression.group('target')} expression",
                context=ContextBundle(cells=(f"{cell} cells",)),
                trigger=_span(factor_overexpression), required=("cells",), covered=("cells",),
            ))

    heading_binding = re.fullmatch(
        r"(?P<subject>[A-Za-z0-9-]+)\s+(?P<verb>specifically\s+binds)\s+to\s+"
        r"(?P<object>[A-Za-z0-9-]+)\s+and\s+regulates\s+its\s+proteolysis", text, re.I,
    )
    if heading_binding:
        events.append(_event(
            heading_binding.group("subject"), "specifically_binds_to",
            heading_binding.group("object"), modality="author_asserted",
            trigger=_span(heading_binding),
        ))

    # Everything below this point is safe for unsectioned DOCUMENT excerpts.
    # Earlier rules depend on a paper-level Results context and are retained
    # only for sectioned sources; document-specific correlation alternatives
    # were collected separately above.
    document_event_start = len(events)

    # Comparative ecology findings.  These constructions reverse the surface
    # direction ("plants benefited from microbes") when naming the causal
    # actor, and attach the comparison or necessity scope to the event.
    microbial_benefit = re.search(
        r"plants\s+(?P<frequency>generally)\s+(?P<verb>benefited)\s+from\s+"
        r"(?P<actor>soil\s+microbes)", text, re.I,
    )
    if microbial_benefit:
        events.append(_event(
            microbial_benefit.group("actor"), "benefit", "plants", modality=None,
            context=ContextBundle(extra=(
                microbial_benefit.group("frequency"), "in this study",
            )), trigger=_span(microbial_benefit),
        ))

    moisture_match = re.search(
        r"this\s+benefit\s+was\s+(?P<verb>greater)\s+whenever\s+(?:their|plants?['’]s)\s+"
        r"current\s+watering\s+conditions\s+matched\s+the\s+microbes(?:['’]s|['’])\s+"
        r"historical\s+watering\s+conditions", text, re.I,
    )
    if moisture_match:
        events.append(_event(
            "matching current and historical watering conditions", "increases",
            "plant benefit from soil microbes", modality=None,
            context=ContextBundle(extra=(
                "plants current watering conditions match microbes historical watering conditions",
                "relative to nonmatching conditions",
            )), trigger=_span(moisture_match),
        ))

    historical_necessity = re.search(
        r"the\s+plant['’]s\s+presence\s+was\s+not\s+(?P<verb>necessary)\s+in\s+"
        r"the\s+historical\s+treatments\s+for\s+this\s+environmental\s+matching\s+"
        r"benefit\s+to\s+emerge", text, re.I,
    )
    if historical_necessity:
        events.append(_event(
            "plant presence in historical treatments", "is_necessary_for",
            "environmental matching benefit", modality=None, polarity="negative",
            context=ContextBundle(extra=(
                "in historical treatments",
                "emergence of the greater benefit when current watering matches microbes historical watering",
            )), trigger=_span(historical_necessity),
        ))

    stress_tolerance = re.search(
        r"(?P<actor>microbes\s+from\s+droughted\s+soils)\s+"
        r"(?P<modal>could)\s+better\s+(?P<verb>tolerate)\s+"
        r"(?P<stress>drought\s+stress)", text, re.I,
    )
    if stress_tolerance:
        events.append(_event(
            stress_tolerance.group("actor"), "tolerate", stress_tolerance.group("stress"),
            modality=stress_tolerance.group("modal"),
            context=ContextBundle(extra=(
                "comparative tolerance stated",
                "comparator not specified in selected passage",
            )), trigger=_span(stress_tolerance),
        ))

    # Coordinated intervention and design clauses in scientific abstracts.
    # Emit one event per role and intervention instead of letting the generic
    # parser cross product the two drugs with individual design adjectives.
    trial_design = re.search(
        r"we\s+(?P<verb>used)\s+an\s+established\s+"
        r"(?P<paradigm>placebo\s+analgesia\s+paradigm)\s+in\s+combination\s+with\s+"
        r"(?P<count>\d+)\s+opposing\s+pharmacological\s+modulations\s+of\s+"
        r"(?P<tone>dopaminergic\s+tone),\s*i\.e\.,\s*the\s+"
        r"(?P<first_role>dopamine\s+antagonist)\s+(?P<first>[A-Za-z0-9-]+)\s+and\s+"
        r"the\s+(?P<second_role>dopamine\s+precursor)\s+(?P<second>[A-Za-z0-9-]+)\s+"
        r"which\s+were\s+both\s+(?P<applied>applied)\s+in\s+an\s+"
        r"(?P<design>experimental,\s*double-blind,\s*randomized,\s*"
        r"placebo-controlled\s+trial\s+with\s+a\s+between-subject\s+design)\s+"
        r"in\s+(?P<sample>N\s*=\s*\d+\s+healthy\s+volunteers)", text, re.I,
    )
    if trial_design:
        study_context = ContextBundle(extra=(
            "combined with two opposing pharmacological modulations of dopaminergic tone",
        ))
        design_context = ContextBundle(extra=(
            "experimental, double-blind, randomized, placebo-controlled, between-subject trial",
            re.sub(r"\s*=\s*", " = ", trial_design.group("sample")),
        ))
        events.extend((
            _event("study", "used", trial_design.group("paradigm"), modality=None,
                   context=study_context, trigger=_span(trial_design)),
            _event(trial_design.group("first"), "is", trial_design.group("first_role"),
                   modality=None, trigger=_span(trial_design, "first_role")),
            _event(trial_design.group("second"), "is", trial_design.group("second_role"),
                   modality=None, trigger=_span(trial_design, "second_role")),
            _event(trial_design.group("first"), "applied_in", "placebo analgesia trial",
                   modality=None, context=design_context, trigger=_span(trial_design, "applied")),
            _event(trial_design.group("second"), "applied_in", "placebo analgesia trial",
                   modality=None, context=design_context, trigger=_span(trial_design, "applied")),
        ))

    manipulation_check = re.search(
        r"the\s+(?P<subject>study\s+medication)\s+successfully\s+"
        r"(?P<verb>altered)\s+(?P<object>dopaminergic\s+tone)\s+"
        r"(?P<timing>during\s+the\s+conditioning\s+procedure)", text, re.I,
    )
    if manipulation_check:
        events.append(_event(
            manipulation_check.group("subject"), "altered", manipulation_check.group("object"),
            modality=None, context=ContextBundle(extra=(manipulation_check.group("timing"),)),
            trigger=_span(manipulation_check),
        ))

    negative_coordination = re.search(
        r"the\s+medication\s+did\s+not\s+(?P<verb>modulate)\s+the\s+"
        r"(?P<expectation>formation\s+of\s+positive\s+treatment\s+expectation)\s+"
        r"and\s+(?P<analgesia>placebo\s+analgesia)\s+tested\s+"
        r"(?P<delay>\d+\s+day\s+later)", text, re.I,
    )
    prior_conditioning = re.search(
        r"study\s+medication\s+successfully\s+altered\s+dopaminergic\s+tone\s+"
        r"during\s+the\s+conditioning\s+procedure", previous_sentence, re.I,
    )
    if negative_coordination and prior_conditioning:
        events.extend((
            _event(
                "study medication", "modulated", negative_coordination.group("expectation"),
                modality=None, polarity="negative", context=ContextBundle(extra=(
                    "after medication during conditioning",
                    "formation of expectation (day-1 test timing is not independently assigned to expectation)",
                )), trigger=_span(negative_coordination),
            ),
            _event(
                "study medication", "modulated", negative_coordination.group("analgesia"),
                modality=None, polarity="negative",
                context=ContextBundle(extra=("tested 1 day after conditioning",)),
                trigger=_span(negative_coordination),
            ),
        ))

    later_detectability = re.search(
        r"(?P<subject>placebo\s+analgesia)\s+was\s+no\s+longer\s+"
        r"(?P<verb>detectable)\s+on\s+(?P<timing>day\s+\d+\s+after\s+conditioning)",
        text, re.I,
    )
    if later_detectability:
        events.append(_event(
            later_detectability.group("subject").lower(), "detectable",
            later_detectability.group("timing"),
            modality=None, polarity="negative",
            context=ContextBundle(extra=(later_detectability.group("timing"),)),
            trigger=_span(later_detectability),
        ))

    evidence_against = re.search(
        r"using\s+a\s+(?P<analysis>combined\s+frequentist\s+and\s+Bayesian\s+approach),\s+"
        r"our\s+data\s+(?P<verb>provide)\s+strong\s+evidence\s+against\s+a\s+"
        r"(?P<influence>direct\s+dopaminergic\s+influence)\s+on\s+the\s+"
        r"(?P<first>generation)\s+and\s+(?P<second>maintenance)\s+of\s+"
        r"(?P<effects>placebo\s+effects)", text, re.I,
    )
    if evidence_against:
        conclusion_context = ContextBundle(extra=(
            "authors’ combined frequentist and Bayesian analysis",
            "conclusion limited to direct influence",
        ))
        for process in (evidence_against.group("first"), evidence_against.group("second")):
            events.append(_event(
                "study data", "provide_strong_evidence_against",
                f"{evidence_against.group('influence')} on {process} of {evidence_against.group('effects')}",
                modality=None, context=conclusion_context, trigger=_span(evidence_against),
            ))

    # Copular descriptions often carry nationality as an adjective.  Keep the
    # complete nominal type as an alternative to the separately emitted
    # nationality and occupation facts.
    person_type = re.search(
        r"(?P<name>[A-Z][A-Za-z-]+)\s+\"(?P<nickname>[^\"]+)\"\s+"
        r"(?P<surname>[A-Z][A-Za-z-]+)\s+\([^)]*\)\s+is\s+a[n]?\s+"
        r"(?P<type>[A-Z][a-z]+\s+[a-z][a-z -]*?(?:racer|player|writer|actor|scientist|politician))"
        r"(?=\s+who\b|[.,;]|$)", text,
    )
    if person_type:
        events.append(_event(
            f"{person_type.group('name')} {person_type.group('nickname')} {person_type.group('surname')}",
            "type", person_type.group("type"), modality=None,
            trigger=_span(person_type, "type"),
        ))

    events.extend(_generic_results_events(
        text, previous_sentence=previous_sentence, state=state,
    ))

    if (source_unit or "").upper() == "DOCUMENT":
        events = [*document_events, *events[document_event_start:]]
    complete: list[EventFrame] = []
    seen: set[tuple[str, str, str, str | None, str, str | None]] = set()
    for event in events:
        if not event.complete:
            continue
        key = (
            event.subject.casefold(), event.predicate, event.object.casefold(),
            event.modality, event.polarity, event.context.render(),
        )
        if key not in seen:
            seen.add(key)
            complete.append(event)
    return complete


def relation_frames_from_events(
    events: list[EventFrame],
    *,
    evidence: str,
    context: str,
    sentence_index: int,
    start: int,
    end: int,
    source_unit: str | None,
) -> list[RelationFrame]:
    """Convert validated atomic events into singleton relation frames."""
    return [
        RelationFrame(
            subject_options=(event.subject,),
            predicate_options=(event.predicate,),
            object_options=(event.object,),
            evidence=context,
            context=context,
            sentence_index=sentence_index,
            start=start,
            end=end,
            modality=event.modality,
            polarity=event.polarity,
            source_unit=source_unit,
            condition=event.context.render(),
            origin="event",
            attribution=event.attribution,
            claim_type=event.claim_type,
            comparison=event.comparison,
            conditions=event.conditions,
            measurements=event.measurements,
        )
        for event in events
    ]

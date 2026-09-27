from __future__ import annotations

import re

from .mentions import (
    clean_text,
    measurements,
    normalize_intervention,
    normalized_mention,
    split_coordination,
)
from .model import (
    EventHypothesis,
    ScientificContext,
    ScientificQualifiers,
    SourceSpan,
)
from .qualifiers import modality as detect_modality


def _anchor(match: re.Match[str], group: str | None = None) -> SourceSpan:
    start, end = match.span(group or 0)
    return SourceSpan(start, end, match.group(group or 0))


def _event(
    source: str,
    *,
    subject_raw: str,
    subject: str,
    predicate: str,
    object_raw: str,
    object_: str,
    construction: str,
    anchor: SourceSpan,
    modality: str = "asserted",
    condition: str | None = None,
    cells: tuple[str, ...] = (),
    comparator: str | None = None,
    measurements_: tuple[str, ...] = (),
    assay: str | None = None,
    polarity: str = "positive",
    required: tuple[str, ...] = (),
) -> EventHypothesis:
    qualifiers = ScientificQualifiers(
        polarity=polarity,
        modality=modality,
        cells=cells,
        comparator=comparator,
        conditions=((condition,) if condition else ()),
        measurements=measurements_,
        assay=assay,
    )
    covered = {
        key for key, value in (
            ("condition", condition),
            ("cells", cells),
            ("comparator", comparator),
            ("measurement", measurements_),
            ("assay", assay),
            ("modality", modality),
            ("polarity", polarity),
        ) if value
    }
    subject_mention = normalized_mention(
        subject_raw, subject, kind="intervention" if re.search(
            r"\b(?:knockdown|depletion|downregulation|silencing|overexpression)\b",
            subject,
            re.I,
        ) else "entity", source=source,
    )
    object_mention = normalized_mention(
        object_raw, object_, kind="outcome", source=source,
    )
    return EventHypothesis(
        subject_mention,
        predicate,
        object_mention,
        qualifiers,
        anchor,
        construction,
        required_qualifiers=frozenset(required),
        covered_qualifiers=frozenset(covered),
        provenance=(subject_mention.span, object_mention.span, anchor),
    )


def _predicate(direction: str) -> str:
    return {
        "increase": "increases", "increased": "increases", "higher": "increases",
        "elevated": "increases", "elevation": "increases",
        "decrease": "decreases", "decreased": "decreases", "lower": "decreases",
        "reduction": "decreases", "lighter": "decreases", "smaller": "decreases",
        "inhibit": "inhibits", "inhibited": "inhibits",
        "promote": "promotes", "promoted": "promotes",
    }[direction.casefold()]


def compile_constructions(
    text: str,
    state: ScientificContext,
) -> list[EventHypothesis]:
    """Compile broad Results constructions into bound event hypotheses."""
    events: list[EventHypothesis] = []
    value = clean_text(text)
    value = re.sub(
        r"(?<=[A-Za-z0-9])and\s+(?=negatively\s+correlated)",
        " and ",
        value,
        flags=re.I,
    )

    generic_active = re.search(
        r"(?P<subject>(?:knockdown|downregulation|overexpression)\s+of\s+"
        r"[A-Za-z][A-Za-z0-9-]*|[A-Za-z][A-Za-z0-9-]*\s+"
        r"(?:knockdown|depletion|silencing|overexpression))\s+"
        r"(?:significantly\s+|markedly\s+)?"
        r"(?P<verb>inhibited|inhibits|promoted|promotes|increased|increases|"
        r"decreased|decreases|reduced|reduces)\s+(?:the\s+)?"
        r"(?P<object>[^,.;]+?)(?=\s+(?:in|under|during|compared\s+to)\s+|$)",
        value,
        re.I,
    )
    reporting_prefix = bool(generic_active and re.search(
        r"\b(?:results?|findings?|data)\s+"
        r"(?:showed|revealed|indicated|demonstrated|confirmed|suggested)\s+that\b",
        value[:generic_active.start("subject")],
        re.I,
    ))
    if generic_active and not reporting_prefix:
        verb = generic_active.group("verb").casefold()
        predicate = (
            "inhibits" if verb.startswith("inhibit") else
            "promotes" if verb.startswith("promote") else
            "increases" if verb.startswith("increase") else
            "decreases"
        )
        events.append(_event(
            value,
            subject_raw=generic_active.group("subject"),
            subject=normalize_intervention(generic_active.group("subject")),
            predicate=predicate,
            object_raw=generic_active.group("object"),
            object_=generic_active.group("object"),
            construction="active_causal",
            anchor=_anchor(generic_active, "verb"),
        ))

    generic_passive = re.search(
        r"(?P<object>[^,.;]+?)\s+was\s+(?:significantly\s+|markedly\s+)?"
        r"(?P<verb>inhibited|promoted|increased|decreased|reduced)\s+by\s+"
        r"(?P<subject>(?:knockdown|downregulation|overexpression)\s+of\s+"
        r"[A-Za-z][A-Za-z0-9-]*|[A-Za-z][A-Za-z0-9-]*\s+"
        r"(?:knockdown|depletion|silencing|overexpression))",
        value,
        re.I,
    )
    if generic_passive:
        verb = generic_passive.group("verb").casefold()
        predicate = (
            "inhibits" if verb == "inhibited" else
            "promotes" if verb == "promoted" else
            "increases" if verb == "increased" else
            "decreases"
        )
        object_ = re.sub(
            r"^.*?\b(?:showed|revealed|indicated|demonstrated)\s+that\s+",
            "", generic_passive.group("object"), flags=re.I,
        )
        events.append(_event(
            value,
            subject_raw=generic_passive.group("subject"),
            subject=normalize_intervention(generic_passive.group("subject")),
            predicate=predicate,
            object_raw=generic_passive.group("object"), object_=object_,
            construction="passive_causal",
            anchor=_anchor(generic_passive, "verb"),
        ))

    negative_affect = re.search(
        r"(?P<subject>(?:knockdown|downregulation|overexpression)\s+of\s+"
        r"[A-Za-z][A-Za-z0-9-]*|[A-Za-z][A-Za-z0-9-]*\s+"
        r"(?:knockdown|depletion|silencing|overexpression))\s+did\s+not\s+"
        r"(?:affect|change|alter)\s+(?:the\s+)?(?P<object>[^,.;]+)$",
        value,
        re.I,
    )
    if (negative_affect and not re.search(
        r"\bbut\b.+\b(?:increased|decreased|upregulated|downregulated|"
        r"promoted|inhibited|reduced)\b",
        negative_affect.group("object"),
        re.I,
    )):
        events.append(_event(
            value,
            subject_raw=negative_affect.group("subject"),
            subject=normalize_intervention(negative_affect.group("subject")),
            predicate="does_not_change",
            object_raw=negative_affect.group("object"), object_=negative_affect.group("object"),
            construction="negative_effect",
            anchor=_anchor(negative_affect),
            polarity="negative", required=("polarity",),
        ))

    # Embedded expression comparison: "A had higher expression in X than Y".
    expression_comparison = re.search(
        r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+had\s+(?P<degree>higher|lower)\s+"
        r"(?P<kind>mRNA|protein)?\s*expression\s+in\s+(?P<left>[^,.;]+?)\s+"
        r"than\s+in\s+(?P<right>[^,.;]+)",
        value,
        re.I,
    )
    if expression_comparison:
        entity = expression_comparison.group("entity")
        kind = expression_comparison.group("kind")
        left = clean_text(expression_comparison.group("left"))
        right = clean_text(expression_comparison.group("right"))
        subject = f"{entity}{' ' + kind if kind else ''} expression"
        events.append(_event(
            value,
            subject_raw=entity,
            subject=subject,
            predicate="higher_than" if expression_comparison.group("degree").casefold() == "higher" else "lower_than",
            object_raw=right,
            object_=f"expression in {right}",
            construction="expression_comparison",
            anchor=_anchor(expression_comparison, "degree"),
            condition=f"in {left} from TCGA" if "TCGA" in value else f"in {left}",
            comparator=f"relative to {right}",
            required=("condition", "comparator"),
        ))

    survival = re.search(
        r"patients?\s+in\s+the\s+(?P<group>high\s+[A-Za-z][A-Za-z0-9-]*\s+"
        r"(?:mRNA\s+)?expression)\s+group\s+had\s+(?:a\s+)?"
        r"(?P<outcomes>shorter\s+survival\s+time\s+and\s+lower\s+survival\s+rate)\s+"
        r"than\s+those\s+in\s+the\s+(?P<control>low\s+expression\s+group)",
        value,
        re.I,
    )
    if survival:
        for outcome in split_coordination(survival.group("outcomes")):
            events.append(_event(
                value,
                subject_raw=survival.group("group"), subject=survival.group("group"),
                predicate="associated_with", object_raw=outcome, object_=outcome,
                construction="group_outcome_comparison", anchor=_anchor(survival, "outcomes"),
                comparator="relative to the low-expression group",
                required=("comparator",),
            ))

    staining_comparison = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+staining\s+signals)\s+were\s+"
        r"(?:much\s+)?(?P<degree>higher|lower)\s+in\s+(?P<left>[^,.;]+?)\s+"
        r"than\s+in\s+(?P<right>[^,.;]+)",
        value,
        re.I,
    )
    if staining_comparison:
        events.append(_event(
            value,
            subject_raw=staining_comparison.group("subject"), subject=staining_comparison.group("subject"),
            predicate="higher_than" if staining_comparison.group("degree").casefold() == "higher" else "lower_than",
            object_raw=staining_comparison.group("right"),
            object_=f"signals in {clean_text(staining_comparison.group('right'))}",
            construction="staining_comparison", anchor=_anchor(staining_comparison, "degree"),
            condition=f"in {clean_text(staining_comparison.group('left'))}",
            comparator=f"relative to {clean_text(staining_comparison.group('right'))}",
            required=("condition", "comparator"),
        ))

    relative_expression = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+expression)\s+was\s+relatively\s+"
        r"(?P<degree>high|low)\s+in\s+(?P<cells>[^,.;]+?\s+cells)", value, re.I,
    )
    if relative_expression:
        raw_cells = split_coordination(relative_expression.group("cells"))
        for cell in raw_cells:
            cell = cell if cell.casefold().endswith(" cells") else f"{cell} cells"
            events.append(_event(
                value,
                subject_raw=relative_expression.group("subject"), subject=relative_expression.group("subject"),
                predicate="relatively_high_in" if relative_expression.group("degree").casefold() == "high" else "relatively_low_in",
                object_raw=cell.removesuffix(" cells"), object_=cell,
                construction="relative_expression", anchor=_anchor(relative_expression, "degree"),
            ))

    association = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+was\s+(?P<modal>likely|possibly|potentially)\s+"
        r"associated\s+with\s+(?:the\s+)?(?P<object>[^,.;]+)", value, re.I,
    )
    if association:
        events.append(_event(
            value, subject_raw=association.group("subject"), subject=association.group("subject"),
            predicate="associated_with", object_raw=association.group("object"), object_=association.group("object"),
            construction="hedged_association", anchor=_anchor(association),
            modality=association.group("modal").casefold(), required=("modality",),
        ))

    passive_inhibited = re.search(
        r"(?P<object>cell\s+proliferation|[^,.;]{2,60})\s+was\s+(?:significantly\s+)?"
        r"(?P<direction>inhibited|increased|decreased)\s+in\s+(?P<cells>both\s+)?"
        r"(?P<cell_list>[^,.;]+?\s+cells)", value, re.I,
    )
    if passive_inhibited and state.intervention:
        cell_value = clean_text(passive_inhibited.group("cell_list"))
        cell_value = re.sub(r"\s+and\s+", " and ", cell_value)
        raw_object = clean_text(passive_inhibited.group("object"))
        raw_object = re.sub(
            r"^.*?\b(?:showed|revealed|indicated|demonstrated)\s+that\s+",
            "",
            raw_object,
            flags=re.I,
        )
        events.append(_event(
            value, subject_raw=state.intervention.split()[0], subject=state.intervention,
            predicate=_predicate(passive_inhibited.group("direction")),
            object_raw=passive_inhibited.group("object"), object_=raw_object,
            construction="passive_effect", anchor=_anchor(passive_inhibited, "direction"),
            condition=f"in {cell_value}", required=("condition",),
        ))

    group_change = re.search(
        r"(?P<object>number\s+of\s+colonies\s+formed|tumou?r\s+weight|tumou?r\s+volume)\s+"
        r"(?:in\s+the\s+(?P<group>[A-Za-z][A-Za-z0-9-]*[- ]depleted)\s+group\s+)?"
        r"was\s+(?:significantly\s+|distinctly\s+)?"
        r"(?P<direction>decreased|lighter|smaller)"
        r"(?:\s+in\s+the\s+(?P<trailing_group>[A-Za-z][A-Za-z0-9-]*[- ]depleted)\s+group)?"
        r"(?:\s+than\s+that\s+in\s+the\s+control\s+group)?",
        value,
        re.I,
    )
    if group_change and state.intervention:
        raw_object = group_change.group("object")
        object_ = {
            "number of colonies formed": "colony formation",
            "tumor weight": "tumor weight", "tumour weight": "tumor weight",
            "tumor volume": "tumor volume", "tumour volume": "tumor volume",
        }.get(raw_object.casefold(), raw_object)
        xenograft = bool(re.search(r"tumou?r", raw_object, re.I))
        explicit_group = group_change.group("group") or group_change.group("trailing_group")
        subject = normalize_intervention(explicit_group) if explicit_group else state.intervention
        if (xenograft and state.intervention and subject
                and state.intervention.split()[0].casefold() == subject.split()[0].casefold()):
            subject = state.intervention
        events.append(_event(
            value, subject_raw=(explicit_group or state.intervention.split()[0]), subject=subject,
            predicate="decreases", object_raw=raw_object, object_=object_,
            construction="group_change", anchor=_anchor(group_change, "direction"),
            condition=(f"in {state.model or 'xenografts'}" if xenograft else None),
            comparator=("relative to control" if xenograft else None),
            required=(("comparator",) if xenograft else ()),
        ))

    volume_comparison = re.search(
        r"tumou?r\s+volume\s+in\s+the\s+control\s+group\s+were?\s+"
        r"(?:much\s+)?larger", value, re.I,
    )
    if volume_comparison and state.intervention:
        events.append(_event(
            value, subject_raw=state.intervention.split()[0], subject=state.intervention,
            predicate="decreases", object_raw="tumor volume", object_="tumor volume",
            construction="inverse_control_comparison", anchor=_anchor(volume_comparison),
            condition=f"in {state.model or 'xenografts'}",
            comparator="relative to control", required=("comparator",),
        ))

    after_change = re.search(
        r"(?P<object>ratio\s+of\s+apoptotic\s+cells|number\s+of\s+S-phase\s+cells|"
        r"expression\s+level\s+of\s+[A-Za-z][A-Za-z0-9-]*(?:\s+protein)?)\s+"
        r"(?P<direction>increased|decreased)\s+(?:after|upon|when)\s+"
        r"(?P<intervention>[^,.;]+)", value, re.I,
    )
    if after_change:
        intervention = normalize_intervention(after_change.group("intervention"))
        object_ = clean_text(after_change.group("object"))
        object_ = re.sub(r"^ratio\s+of\s+", "", object_, flags=re.I)
        object_ = object_.replace("apoptotic cells", "apoptotic cell ratio")
        object_ = object_.replace("number of S-phase cells", "S-phase cell count")
        events.append(_event(
            value, subject_raw=after_change.group("intervention"), subject=intervention,
            predicate=_predicate(after_change.group("direction")),
            object_raw=after_change.group("object"), object_=object_,
            construction="change_after_intervention", anchor=_anchor(after_change, "direction"),
        ))

    observed_change = re.search(
        r"(?P<direction>decrease|increase)\s+in\s+(?P<object>[^,.;]+?)\s+was\s+"
        r"observed\s+by\s+(?P<assay>[^,.;]+?assay)\s+in\s+(?P<cells>[^,.;]+?\s+cells)",
        value,
        re.I,
    )
    if observed_change and state.intervention:
        object_ = clean_text(observed_change.group("object")).replace("cells in the S-phase", "S-phase cell count")
        events.append(_event(
            value, subject_raw=state.intervention.split()[0], subject=state.intervention,
            predicate="decreases" if observed_change.group("direction").casefold() == "decrease" else "increases",
            object_raw=observed_change.group("object"), object_=object_,
            construction="observed_nominal_change", anchor=_anchor(observed_change, "direction"),
            cells=(clean_text(observed_change.group("cells")),),
            assay=clean_text(observed_change.group("assay")), required=("cells", "assay"),
        ))

    no_difference = re.search(
        r"no\s+(?:obvious\s+)?(?:differences?|change)\s+in\s+(?:the\s+)?"
        r"(?P<object>expression(?:\s+levels?)?\s+of\s+[A-Za-z][A-Za-z0-9-]*)",
        value,
        re.I,
    )
    if no_difference and state.intervention:
        object_ = re.sub(r"^expression(?:\s+levels?)?\s+of\s+", "", no_difference.group("object"), flags=re.I)
        events.append(_event(
            value, subject_raw=state.intervention.split()[0], subject=state.intervention,
            predicate="does_not_change", object_raw=no_difference.group("object"), object_=f"{object_} expression",
            construction="negative_no_difference", anchor=_anchor(no_difference),
            polarity="negative", required=("polarity",),
        ))

    related = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+was\s+(?:markedly\s+)?related\s+to\s+"
        r"(?P<objects>[^.;]+)", value, re.I,
    )
    if related:
        for object_ in split_coordination(related.group("objects")):
            events.append(_event(
                value, subject_raw=related.group("subject"), subject=related.group("subject"),
                predicate="related_to", object_raw=object_, object_=f"{object_} expression",
                construction="related_coordination", anchor=_anchor(related),
            ))

    # Reporting conclusions with coordinated predicates.
    conclusion = re.search(
        r"(?P<report>suggested|suggest|indicated|demonstrated|confirmed|implied)\s+that\s+"
        r"(?P<subject>(?:the\s+)?(?:knockdown|downregulation|overexpression)\s+of\s+"
        r"[A-Za-z][A-Za-z0-9-]*|[A-Za-z][A-Za-z0-9-]*\s+(?:knockdown|overexpression))\s+"
        r"(?P<verb1>inhibits?|promotes?)\s+(?P<object1>[^,.;]+?)\s+and\s+"
        r"(?P<verb2>promotes?|inhibits?)\s+(?P<object2>[^,.;]+)", value, re.I,
    )
    if conclusion:
        subject = normalize_intervention(conclusion.group("subject"))
        modal = detect_modality(value, reporting=conclusion.group("report"))
        for verb, object_ in (
            (conclusion.group("verb1"), conclusion.group("object1")),
            (conclusion.group("verb2"), conclusion.group("object2")),
        ):
            if "human breast cancer cells" in object_:
                object_ = object_.replace(" in human breast cancer cells", "")
            events.append(_event(
                value, subject_raw=conclusion.group("subject"), subject=subject,
                predicate="inhibits" if verb.casefold().startswith("inhibit") else "promotes",
                object_raw=object_, object_=clean_text(object_),
                construction="reported_coordinated_conclusion", anchor=_anchor(conclusion),
                modality=modal, condition="in human breast cancer cells" if "human breast cancer cells" in value else None,
                required=("modality",),
            ))

    single_conclusion = re.search(
        r"(?P<report>showed|revealed|demonstrated|confirmed|indicated|suggested)\s+that\s+"
        r"(?P<subject>(?:knockdown|downregulation|overexpression)\s+of\s+"
        r"[A-Za-z][A-Za-z0-9-]*|[A-Za-z][A-Za-z0-9-]*\s+"
        r"(?:knockdown|depletion|silencing|overexpression))\s+"
        r"(?P<verb>inhibit(?:s|ed)?|promote(?:s|d)?)\s+"
        r"(?P<object>[^,.;]+)", value, re.I,
    )
    if single_conclusion:
        subject = normalize_intervention(single_conclusion.group("subject"))
        events.append(_event(
            value, subject_raw=single_conclusion.group("subject"), subject=subject,
            predicate="inhibits" if single_conclusion.group("verb").casefold().startswith("inhibit") else "promotes",
            object_raw=single_conclusion.group("object"), object_=single_conclusion.group("object"),
            construction="reported_single_conclusion", anchor=_anchor(single_conclusion),
            modality=("suggested" if single_conclusion.group("report").casefold().startswith("suggest") else "asserted"),
        ))

    nominal_after = re.search(
        r"(?P<direction>increases?|decreases?)\s+in\s+(?P<objects>[^.;]+?)\s+"
        r"were\s+observed\s+after\s+(?P<intervention>[^,.;]+)", value, re.I,
    )
    if nominal_after:
        subject = normalize_intervention(nominal_after.group("intervention"))
        for object_ in split_coordination(nominal_after.group("objects")):
            events.append(_event(
                value, subject_raw=nominal_after.group("intervention"), subject=subject,
                predicate="increases" if nominal_after.group("direction").casefold().startswith("increase") else "decreases",
                object_raw=object_, object_=object_, construction="result_after_intervention",
                anchor=_anchor(nominal_after, "direction"),
                condition=(f"in {state.cells[0]}" if len(state.cells) == 1 else None),
            ))

    when_change = re.search(
        r"When\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+was\s+"
        r"(?P<operation>overexpressed|silenced|depleted),\s+the\s+"
        r"(?P<object>number\s+of\s+S-phase\s+cells|[^,.;]+?)\s+"
        r"(?P<direction>increased|decreased)", value, re.I,
    )
    if when_change:
        op = {"overexpressed": "overexpression", "silenced": "silencing", "depleted": "depletion"}[
            when_change.group("operation").casefold()
        ]
        object_ = clean_text(when_change.group("object")).replace("number of S-phase cells", "S-phase cell count")
        events.append(_event(
            value, subject_raw=when_change.group("entity"), subject=f"{when_change.group('entity')} {op}",
            predicate=_predicate(when_change.group("direction")),
            object_raw=when_change.group("object"), object_=object_,
            construction="temporal_intervention_change", anchor=_anchor(when_change, "direction"),
            condition=(f"in {state.cells[0]}" if len(state.cells) == 1 else None),
        ))

    correlations = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*(?:\s+overexpression|\s+expression)?)\s+was\s+"
        r"positively\s+correlated\s+with\s+(?:the\s+expression\s+of\s+)?"
        r"(?P<positive>[^.;]+?)(?=\s+and\s+negatively\s+correlated|$)"
        r"(?:\s+and\s+negatively\s+correlated\s+with\s+"
        r"(?:the\s+expression\s+of\s+)?(?P<negative>[^.;]+))?$", value, re.I,
    )
    if correlations:
        for item in split_coordination(correlations.group("positive")):
            events.append(_event(
                value, subject_raw=correlations.group("subject"), subject=correlations.group("subject"),
                predicate="positively_correlated_with", object_raw=item, object_=f"{item} expression",
                construction="correlation_coordination", anchor=_anchor(correlations),
                condition=(f"in {state.cells[0]}" if len(state.cells) == 1 else None),
            ))
        if correlations.group("negative"):
            for item in split_coordination(correlations.group("negative")):
                events.append(_event(
                    value, subject_raw=correlations.group("subject"), subject=correlations.group("subject"),
                    predicate="negatively_correlated_with", object_raw=item, object_=f"{item} expression",
                    construction="correlation_coordination", anchor=_anchor(correlations),
                    condition=(f"in {state.cells[0]}" if len(state.cells) == 1 else None),
                ))

    direct_promotion = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+overexpression)\s+"
        r"(?P<verb>promotes?|inhibits?)\s+(?P<object>cell\s+proliferation)\s+"
        r"in\s+(?P<cells>[^,.;]+?\s+cells)", value, re.I,
    )
    if direct_promotion:
        events.append(_event(
            value, subject_raw=direct_promotion.group("subject"), subject=direct_promotion.group("subject"),
            predicate="promotes" if direct_promotion.group("verb").casefold().startswith("promote") else "inhibits",
            object_raw=direct_promotion.group("object"), object_=direct_promotion.group("object"),
            construction="direct_effect", anchor=_anchor(direct_promotion, "verb"),
            condition=f"in {clean_text(direct_promotion.group('cells'))}", required=("condition",),
        ))

    coordinated_lower = re.search(
        r"(?P<objects>[A-Za-z][A-Za-z0-9-]*\s+and\s+[A-Za-z][A-Za-z0-9-]*)\s+"
        r"were\s+(?:consistently\s+)?lower\s+in\s+expression\s+in\s+the\s+"
        r"tumou?rs?\s+of\s+the\s+(?P<group>[A-Za-z][A-Za-z0-9-]*[- ]depletion)\s+group",
        value, re.I,
    )
    if coordinated_lower:
        subject = normalize_intervention(coordinated_lower.group("group"))
        if state.intervention and state.intervention.split()[0].casefold() == subject.split()[0].casefold():
            subject = state.intervention
        for object_ in split_coordination(coordinated_lower.group("objects")):
            events.append(_event(
                value, subject_raw=coordinated_lower.group("group"), subject=subject,
                predicate="decreases", object_raw=object_, object_=f"{object_} expression",
                construction="coordinated_group_expression", anchor=_anchor(coordinated_lower),
                condition=f"in {state.model or 'xenograft tumors'}",
                comparator="relative to control", required=("comparator",),
            ))

    direct_binding = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+can\s+bind\s+to\s+and\s+regulate\s+"
        r"(?P<object>[^,.;]+)", value, re.I,
    )
    if direct_binding:
        events.append(_event(
            value, subject_raw=direct_binding.group("subject"), subject=direct_binding.group("subject"),
            predicate="binds_and_regulates", object_raw=direct_binding.group("object"), object_=direct_binding.group("object"),
            construction="coordinated_predicate", anchor=_anchor(direct_binding), modality="can",
            required=("modality",),
        ))

    enrichment = re.search(
        r"(?P<subject>peaks|[A-Za-z][A-Za-z0-9-]*\s+RIP-seq\s+peaks)\s+were\s+"
        r"most\s+enriched\s+in\s+the\s+(?P<object>[^,.;]+),\s+with\s+a\s+"
        r"percentage\s+of\s+(?P<percent>\d+(?:\.\d+)?%)", value, re.I,
    )
    if enrichment:
        subject = enrichment.group("subject")
        if subject.casefold() == "peaks" and state.heading:
            heading_entity = re.search(
                r"binding\s+RNAs?\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)",
                state.heading,
                re.I,
            )
            if heading_entity:
                subject = f"{heading_entity.group('entity')} RIP-seq peaks"
        events.append(_event(
            value, subject_raw=enrichment.group("subject"), subject=subject,
            predicate="most_enriched_in", object_raw=enrichment.group("object"), object_=enrichment.group("object"),
            construction="enrichment_percentage", anchor=_anchor(enrichment),
        ))
        events.append(_event(
            value, subject_raw=enrichment.group("subject"), subject=f"{subject} in {enrichment.group('object')}",
            predicate="has_percentage", object_raw=enrichment.group("percent"), object_=enrichment.group("percent"),
            construction="enrichment_percentage", anchor=_anchor(enrichment, "percent"),
            measurements_=(enrichment.group("percent"),), required=("measurement",),
        ))

    motif = re.search(
        r"(?P<subject>[^,.;]+?sequence\s+motif)\s+was\s+verified\s+to\s+be\s+"
        r"(?P<predicate>highly\s+enriched)\s+in\s+(?P<object>[^,.;(]+)", value, re.I,
    )
    if motif:
        subject = re.sub(r"[\"“”]", "", clean_text(motif.group("subject")))
        subject = re.sub(r"^The\s+", "", subject, flags=re.I)
        events.append(_event(
            value, subject_raw=motif.group("subject"), subject=subject,
            predicate="highly_enriched_in", object_raw=motif.group("object"), object_=motif.group("object"),
            construction="passive_enrichment", anchor=_anchor(motif, "predicate"),
        ))

    important = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+(?P<modal>might|may|could)\s+be\s+"
        r"(?:very\s+)?important\s+for\s+(?:the\s+)?(?P<object>[^,.;]+)", value, re.I,
    )
    if important:
        events.append(_event(
            value, subject_raw=important.group("subject"), subject=important.group("subject"),
            predicate="important_for", object_raw=important.group("object"),
            object_=re.sub(r"^expression\s+of\s+", "", important.group("object"), flags=re.I) + " expression",
            construction="modal_importance", anchor=_anchor(important),
            modality=important.group("modal").casefold(), required=("modality",),
        ))

    predicted_binding = re.search(
        r"predicted\s+that\s+(?P<subject>[A-Za-z][A-Za-z0-9-]*[- ]protein)\s+can\s+"
        r"bind\s+to\s+(?P<object>[A-Za-z][A-Za-z0-9-]*)\s+by\s+the\s+"
        r"(?P<region>\d+-\d+\s+region\s+of\s+[A-Za-z][A-Za-z0-9-]*[- ]mRNA)",
        value, re.I,
    )
    if predicted_binding:
        events.append(_event(
            value, subject_raw=predicted_binding.group("subject"),
            subject=predicted_binding.group("subject").replace("-protein", " protein"),
            predicate="binds", object_raw=predicted_binding.group("object"),
            object_=f"{predicted_binding.group('object')} mRNA",
            construction="predicted_binding", anchor=_anchor(predicted_binding),
            modality="predicted", condition=f"via the {predicted_binding.group('region').replace('-mRNA', ' mRNA')}",
            required=("modality", "condition"),
        ))

    arm_enrichment = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+was\s+(?:significantly\s+)?enriched\s+in\s+"
        r"the\s+(?P<arm>anti-[A-Za-z][A-Za-z0-9-]*\s+group),\s+and\s+the\s+"
        r"abundance\s+was\s+(?P<fold>\d+(?:\.\d+)?\s+times)\s+higher\s+than\s+"
        r"that\s+in\s+the\s+(?P<control>anti-[A-Za-z][A-Za-z0-9-]*\s+group)",
        value, re.I,
    )
    if arm_enrichment:
        fold = arm_enrichment.group("fold").replace(" times", "-fold")
        events.append(_event(
            value, subject_raw=arm_enrichment.group("subject"), subject=arm_enrichment.group("subject"),
            predicate="enriched_in", object_raw=arm_enrichment.group("arm"), object_=arm_enrichment.group("arm"),
            construction="arm_enrichment", anchor=_anchor(arm_enrichment),
            condition=None,
            comparator=f"relative to {arm_enrichment.group('control').removesuffix(' group')}",
            measurements_=(fold,), required=("comparator", "measurement"),
        ))

    tissue_overexpression = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+expression|[A-Za-z][A-Za-z0-9-]*)\s+was\s+"
        r"(?:significantly\s+)?overexpressed\s+in\s+(?P<left>[^,.;]+?)\s+"
        r"compared\s+with\s+(?P<right>[^,.;]+)", value, re.I,
    )
    if tissue_overexpression:
        subject = tissue_overexpression.group("subject")
        if not subject.casefold().endswith(" expression"):
            subject += " expression"
        events.append(_event(
            value, subject_raw=tissue_overexpression.group("subject"), subject=subject,
            predicate="higher_than", object_raw=tissue_overexpression.group("right"),
            object_=f"expression in {clean_text(tissue_overexpression.group('right'))}",
            construction="tissue_expression_comparison", anchor=_anchor(tissue_overexpression),
            condition=f"in {clean_text(tissue_overexpression.group('left'))} from TCGA" if "TCGA" in value else f"in {clean_text(tissue_overexpression.group('left'))}",
            comparator=f"relative to {clean_text(tissue_overexpression.group('right'))}",
            required=("condition", "comparator"),
        ))

    poorer_outcomes = re.search(
        r"patients?\s+with\s+(?P<subject>high\s+[A-Za-z][A-Za-z0-9-]*\s+expression)\s+"
        r"had\s+(?P<objects>poorer\s+survival\s+and\s+prognosis)", value, re.I,
    )
    if poorer_outcomes:
        for object_ in split_coordination(poorer_outcomes.group("objects")):
            if object_.casefold() == "prognosis":
                object_ = "poorer prognosis"
            events.append(_event(
                value, subject_raw=poorer_outcomes.group("subject"), subject=poorer_outcomes.group("subject"),
                predicate="associated_with", object_raw=object_, object_=object_,
                construction="coordinated_clinical_outcomes", anchor=_anchor(poorer_outcomes),
            ))

    plain_correlation = re.search(
        r"(?:There\s+was\s+a\s+correlation\s+between\s+|(?:the\s+)?expression\s+of\s+)"
        r"(?P<left>[A-Za-z][A-Za-z0-9-]*(?:\s+expression)?)\s+"
        r"(?:and|was\s+positively\s+correlated\s+with)\s+"
        r"(?P<right>stage\s+[A-Za-z0-9]+|[A-Za-z][A-Za-z0-9-]*\s+expression)",
        value, re.I,
    )
    if plain_correlation:
        left = plain_correlation.group("left")
        if not left.casefold().endswith(" expression"):
            left += " expression"
        positive = "positively correlated" in plain_correlation.group(0).casefold()
        events.append(_event(
            value, subject_raw=plain_correlation.group("left"), subject=left,
            predicate="positively_correlated_with" if positive else "correlated_with",
            object_raw=plain_correlation.group("right"), object_=plain_correlation.group("right"),
            construction="plain_correlation", anchor=_anchor(plain_correlation),
            condition="at transcriptional and translational levels" if "transcriptional and translational levels" in value else None,
        ))

    inverse_likelihood = re.search(
        r"The\s+higher\s+the\s+(?P<subject>[A-Za-z][A-Za-z0-9-]*\s+expression),\s+"
        r"the\s+less\s+likely\s+there\s+was\s+to\s+be\s+(?P<object>[^,.;(]+)", value, re.I,
    )
    if inverse_likelihood:
        p_value = next((m for m in measurements(value) if m.lower().startswith("p")), None)
        events.append(_event(
            value, subject_raw=inverse_likelihood.group("subject"), subject=f"higher {inverse_likelihood.group('subject')}",
            predicate="associated_with", object_raw=inverse_likelihood.group("object"),
            object_=f"lower likelihood of {inverse_likelihood.group('object')}",
            construction="inverse_likelihood", anchor=_anchor(inverse_likelihood),
            condition=p_value, measurements_=((p_value,) if p_value else ()),
            required=(("measurement",) if p_value else ()),
        ))

    lower_group = re.search(
        r"(?P<subject>staining\s+of\s+[A-Za-z][A-Za-z0-9-]*|expression\s+of\s+[A-Za-z][A-Za-z0-9-]*)\s+"
        r"was\s+(?:lighter\s+and\s+the\s+expression\s+was\s+)?lower\s+in\s+the\s+"
        r"(?P<group>[A-Za-z][A-Za-z0-9-]*[- ]depleted)\s+group\s+than\s+in\s+the\s+control\s+group",
        value, re.I,
    )
    if lower_group:
        raw_subject = lower_group.group("subject")
        entity = re.search(r"[A-Za-z][A-Za-z0-9-]*$", raw_subject).group(0)
        subject = normalize_intervention(lower_group.group("group"))
        if state.intervention and state.intervention.split()[0].casefold() == subject.split()[0].casefold():
            subject = state.intervention
        events.append(_event(
            value, subject_raw=lower_group.group("group"), subject=subject,
            predicate="decreases", object_raw=raw_subject, object_=f"{entity} expression",
            construction="depleted_group_comparison", anchor=_anchor(lower_group),
            condition=f"in {state.model or 'xenograft tumors'}",
            comparator="relative to control", required=("comparator",),
        ))

    knockdown_direct = re.search(
        r"Knocking\s+down\s+(?:the\s+expression\s+of\s+)?(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+"
        r"(?:significantly\s+)?(?P<verb>inhibited|promoted)\s+(?:the\s+)?"
        r"(?P<object>proliferation\s+of\s+[^,.;]+?\s+cells|[^,.;]+)", value, re.I,
    )
    if knockdown_direct:
        object_ = clean_text(knockdown_direct.group("object"))
        cell_match = re.search(r"proliferation\s+of\s+(?P<cell>[^,.;]+?\s+cells)", object_, re.I)
        if cell_match:
            subject_cell = clean_text(cell_match.group("cell"))
            object_ = f"{subject_cell.removesuffix(' cells')} cell proliferation"
            condition = f"in {subject_cell}"
        else:
            condition = None
        events.append(_event(
            value, subject_raw=knockdown_direct.group("entity"), subject=f"{knockdown_direct.group('entity')} knockdown",
            predicate="inhibits" if knockdown_direct.group("verb").casefold() == "inhibited" else "promotes",
            object_raw=knockdown_direct.group("object"), object_=object_,
            construction="direct_knockdown", anchor=_anchor(knockdown_direct, "verb"),
            condition=condition,
        ))

    after_downregulation = re.search(
        r"After\s+downregulation\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+expression,\s+"
        r"the\s+expression\s+level\s+of\s+(?P<first>[A-Za-z][A-Za-z0-9-]*\s+protein)\s+"
        r"(?P<direction>decreased|increased),\s+but\s+it\s+did\s+not\s+affect\s+"
        r"the\s+protein\s+expression\s+of\s+(?P<second>[A-Za-z][A-Za-z0-9-]*)",
        value, re.I,
    )
    if after_downregulation:
        subject = f"{after_downregulation.group('entity')} knockdown"
        condition = f"in {state.cells[0]}" if len(state.cells) == 1 else None
        events.append(_event(
            value, subject_raw=after_downregulation.group("entity"), subject=subject,
            predicate=_predicate(after_downregulation.group("direction")),
            object_raw=after_downregulation.group("first"), object_=f"{after_downregulation.group('first')} expression",
            construction="contrast_after_intervention", anchor=_anchor(after_downregulation, "direction"),
            condition=condition,
        ))
        events.append(_event(
            value, subject_raw=after_downregulation.group("entity"), subject=subject,
            predicate="does_not_change", object_raw=after_downregulation.group("second"),
            object_=f"{after_downregulation.group('second')} protein expression",
            construction="contrast_after_intervention", anchor=_anchor(after_downregulation),
            condition=condition, polarity="negative", required=("polarity",),
        ))

    group_proliferation = re.search(
        r"proliferation\s+ability\s+of\s+(?:the\s+)?cells?\s+in\s+the\s+"
        r"(?P<group>[A-Za-z][A-Za-z0-9-]*\s+(?:knockdown|overexpression))\s+group\s+"
        r"was\s+(?:significantly\s+)?(?P<direction>increased|decreased)\s+"
        r"compared\s+(?:to|with)\s+that\s+in\s+the\s+control\s+group",
        value, re.I,
    )
    if group_proliferation:
        events.append(_event(
            value, subject_raw=group_proliferation.group("group"), subject=group_proliferation.group("group"),
            predicate=_predicate(group_proliferation.group("direction")),
            object_raw="proliferation ability", object_="cell proliferation",
            construction="group_proliferation_comparison", anchor=_anchor(group_proliferation, "direction"),
            condition=f"in {state.cells[0] if state.cells else 'cells'}",
            comparator="relative to control", required=("comparator",),
        ))

    rescue = re.search(
        r"proliferation\s+ability\s+of\s+the\s+cells\s+in\s+the\s+"
        r"(?P<primary>[A-Za-z][A-Za-z0-9-]*\s+knockdown)\s+group\s+with\s+"
        r"(?P<rescue>[A-Za-z][A-Za-z0-9-]*\s+overexpression)\s+at\s+the\s+same\s+time\s+"
        r"increased,\s+which\s+was\s+almost\s+the\s+same\s+as\s+that\s+of\s+the\s+control\s+group",
        value, re.I,
    )
    if rescue:
        events.append(_event(
            value, subject_raw=rescue.group("rescue"), subject=rescue.group("rescue"),
            predicate="rescues", object_raw="proliferation ability", object_=f"proliferation decreased by {rescue.group('primary')}",
            construction="rescue", anchor=_anchor(rescue),
            condition=(f"during {rescue.group('primary')}; "
                       f"in {state.cells[0] if state.cells else 'cells'}"),
            comparator="to approximately control level", required=("condition", "comparator"),
        ))

    mechanism = re.search(
        r"(?P<report>suggested|indicated|demonstrated)\s+that\s+"
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+(?P<verb>promoted|inhibited)\s+"
        r"(?:the\s+)?(?P<object>[^,.;]+?)\s+by\s+a\s+(?P<mechanism>[^,.;]+?\s+mechanism)",
        value, re.I,
    )
    if mechanism:
        events.append(_event(
            value, subject_raw=mechanism.group("subject"), subject=mechanism.group("subject"),
            predicate="promotes" if mechanism.group("verb").casefold() == "promoted" else "inhibits",
            object_raw=mechanism.group("object"),
            object_=re.sub(
                r"proliferation\s+of\s+(?P<cells>.+?)\s+cells$",
                lambda match: f"{match.group('cells')} cell proliferation",
                mechanism.group("object"), flags=re.I,
            ),
            construction="mechanistic_interpretation", anchor=_anchor(mechanism),
            modality="suggested" if mechanism.group("report").casefold().startswith("suggest") else "asserted",
            condition=f"through a {mechanism.group('mechanism')}", required=("modality", "condition"),
        ))

    # Keep only complete, nonempty and unique hypotheses. Ambiguity is bounded
    # per proposition by construction handlers, not by a global Cartesian menu.
    unique: list[EventHypothesis] = []
    seen: set[tuple[str, str, str, str | None, str | None]] = set()
    for event in events:
        key = (
            event.subject.normalized.casefold(), event.predicate,
            event.object.normalized.casefold(), event.qualifiers.modality,
            event.qualifiers.render(),
        )
        if event.complete and all((event.subject.normalized, event.predicate, event.object.normalized)) and key not in seen:
            seen.add(key)
            unique.append(event)

    # Prefer the most qualified reading when two handlers compile the same
    # semantic core. This removes a broad active-verb reading when another
    # construction preserves its cell line, comparator, or assay.
    best: dict[tuple[str, str, str, str | None, str], EventHypothesis] = {}
    order: list[tuple[str, str, str, str | None, str]] = []
    for event in unique:
        key = (
            event.subject.normalized.casefold(), event.predicate,
            event.object.normalized.casefold(), event.qualifiers.modality,
            event.qualifiers.polarity,
        )
        score = len(event.qualifiers.render() or "")
        if key not in best:
            best[key] = event
            order.append(key)
        elif score > len(best[key].qualifiers.render() or ""):
            best[key] = event
    return [best[key] for key in order]

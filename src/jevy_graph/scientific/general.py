"""Broad grammatical constructions for scientific Results prose.

These handlers cover recurring forms found across domains: intervention
effects, coordinated comparisons, diagnostic metrics, expression contrasts,
and model-performance statements.  They depend on syntax and units rather
than paper-specific entities.
"""
from __future__ import annotations

import re

from .mentions import clean_text, normalized_mention, split_coordination
from .model import EventHypothesis, ScientificContext, ScientificQualifiers, SourceSpan


def _span(source: str, match: re.Match[str], group: str | None = None) -> SourceSpan:
    start, end = match.span(group or 0)
    return SourceSpan(start, end, source[start:end])


def _event(
    source: str,
    match: re.Match[str],
    *,
    subject_raw: str,
    subject: str,
    predicate: str,
    object_raw: str,
    object_: str,
    construction: str,
    condition: str | None = None,
    comparator: str | None = None,
    measurement: str | None = None,
    modality: str = "asserted",
    polarity: str = "positive",
) -> EventHypothesis:
    qualifiers = ScientificQualifiers(
        modality=modality,
        polarity=polarity,
        comparator=comparator,
        conditions=((condition,) if condition else ()),
        measurements=((measurement,) if measurement else ()),
    )
    return EventHypothesis(
        normalized_mention(subject_raw, subject, source=source),
        predicate,
        normalized_mention(object_raw, object_, kind="outcome", source=source),
        qualifiers,
        _span(source, match),
        construction,
        provenance=(),
    )


def _items(value: str) -> tuple[str, ...]:
    return tuple(clean_text(item) for item in split_coordination(value) if clean_text(item))


def _condition(value: str) -> str | None:
    match = re.search(
        r"\b(?P<condition>(?:under|during|in|when)\s+"
        r"(?:normal|non-stress|non-stressed|drought|water[- ]deficient|both\b)[^,.;]*)",
        value,
        re.I,
    )
    if not match:
        return None
    condition = clean_text(match.group("condition"))
    return re.sub(r"\s+as\s+shown\s+in\s+Figures?.*$", "", condition, flags=re.I)


def _metric_name(value: str) -> str:
    key = re.sub(r"[^a-z]", "", value.casefold())
    return {
        "auroc": "AUROC", "auc": "AUC", "cvareaunderthecurveauc": "CV AUC",
        "sensitivity": "sensitivity", "specificity": "specificity",
        "overallaccuracy": "accuracy", "accuracy": "accuracy",
    }.get(key, clean_text(value))


def _metric_predicate(name: str) -> str:
    return "has_" + re.sub(r"\s+", "_", name.casefold())


def _model_subject(value: str) -> str:
    value = re.sub(r"^The\s+", "", clean_text(value), flags=re.I)
    acronym = re.search(r"\((?P<name>[A-Z][A-Z0-9/-]+)\)", value)
    return f"{acronym.group('name')} model" if acronym else value


def compile_general_constructions(
    text: str,
    state: ScientificContext,
) -> list[EventHypothesis]:
    value = clean_text(text)
    events: list[EventHypothesis] = []

    # "application of X exhibited no changes in A and B under C"
    no_changes = re.search(
        r"(?:^(?P<prefix>Under\s+[^,]+),\s*)?"
        r"(?P<subject>[^,.;]+?)\s+(?:exhibited|showed)\s+no\s+"
        r"(?:significant\s+)?changes?\s+in\s+(?P<objects>[^,.;]+?)"
        r"(?=,\s*(?:but|however)|$)", value, re.I,
    )
    if no_changes:
        condition = clean_text(no_changes.group("prefix")) if no_changes.group("prefix") else _condition(value)
        objects = re.sub(r"\s+in\s+(?:the\s+)?(?:leaves?|cells?)$", "", no_changes.group("objects"), flags=re.I)
        for object_ in _items(objects):
            events.append(_event(
                value, no_changes, subject_raw=no_changes.group("subject"),
                subject=clean_text(no_changes.group("subject")), predicate="does_not_change",
                object_raw=object_, object_=object_, construction="coordinated_no_change",
                condition=condition, polarity="negative",
            ))

    # "plants pretreated with X showed 28% higher A and 17% lower B ..."
    paired_comparison = re.search(
        r"(?P<actor>[^,.;]*?pretreated\s+with\s+(?P<treatment>[A-Za-z][A-Za-z0-9-]*))\s+"
        r"(?:showed|had)\s+(?P<v1>\d+(?:\.\d+)?%)\s+(?P<d1>higher|lower)\s+"
        r"(?P<o1>[^,.;]+?)\s+and\s+(?P<v2>\d+(?:\.\d+)?%)\s+"
        r"(?P<d2>higher|lower)\s+(?P<o2>[^,.;]+?)\s+when\s+compared\s+with\s+"
        r"(?P<comparator>[^,.;]+?)(?P<condition>\s+under\s+[^,.;]+)?$", value, re.I,
    )
    if paired_comparison:
        subject = f"{paired_comparison.group('treatment')} pretreatment"
        condition = clean_text(paired_comparison.group("condition") or "") or None
        comparator = f"relative to {clean_text(paired_comparison.group('comparator'))}"
        for value_group, direction_group, object_group in (("v1", "d1", "o1"), ("v2", "d2", "o2")):
            amount = paired_comparison.group(value_group)
            predicate = "increases" if paired_comparison.group(direction_group).casefold() == "higher" else "decreases"
            object_ = clean_text(paired_comparison.group(object_group))
            events.append(_event(
                value, paired_comparison, subject_raw=paired_comparison.group("treatment"),
                subject=subject, predicate=predicate, object_raw=object_,
                object_=f"{object_} by {amount}", construction="paired_treatment_comparison",
                condition=condition, comparator=comparator, measurement=amount,
            ))

    # Active directional statements with a coordinated outcome list.
    active_list = re.search(
        r"(?P<subject>(?:Exogenous\s+)?[^,.;]+?)\s+(?:significantly\s+|substantially\s+|markedly\s+)?"
        r"(?P<verb>increased|decreased|reduced)\s+(?:contents?\s+of\s+|the\s+)?"
        r"(?P<objects>[^.;]+?)(?=,?\s+(?:under|in)\s+[^,.;]+(?:,|$)|,\s*(?:but|however)|$)",
        value, re.I,
    )
    active_subject = clean_text(active_list.group("subject")) if active_list else ""
    active_objects = clean_text(active_list.group("objects")) if active_list else ""
    active_list_valid = bool(
        active_list
        and ("," in active_objects or re.search(r"\band\b", active_objects, re.I))
        and len(active_subject.split()) <= 8
        and not re.search(
            r"\b(?:or|was|were|is|are|whereas|however|but|unlike|evidenced|"
            r"accompanied|results?|findings?|reduction|inhibited|promoted)\b",
            active_subject,
            re.I,
        )
        and not re.search(
            r"\b(?:whereas|however|but|unlike|inhibited|promoted|increased|decreased)\b",
            active_objects,
            re.I,
        )
        and not active_subject.casefold().endswith(" by")
    )
    if active_list_valid:
        subject = clean_text(active_list.group("subject"))
        subject = re.sub(r"^Exogenous\s+", "", subject, flags=re.I)
        predicate = "increases" if active_list.group("verb").casefold() == "increased" else "decreases"
        tail = value[active_list.end("objects"):]
        condition_match = re.search(r"\b(?:under|in)\s+[^,.;]+", tail, re.I)
        condition = clean_text(condition_match.group(0)) if condition_match else None
        for object_ in _items(active_list.group("objects")):
            events.append(_event(
                value, active_list, subject_raw=active_list.group("subject"), subject=subject,
                predicate=predicate, object_raw=object_, object_=object_,
                construction="coordinated_directional_effect", condition=condition,
            ))

    unaffected_prefix = r"(?:however|but),?\s+" if re.search(r"\b(?:however|but),?\s+", value, re.I) else r"^"
    unaffected = re.search(
        unaffected_prefix + r"(?P<objects>[A-Za-z0-9/ -]+(?:,\s*[A-Za-z0-9/ -]+)*(?:,?\s+and\s+[A-Za-z0-9/ -]+)?)\s+"
        r"(?:remained|were)\s+unaffected\s+by\s+(?:the\s+)?(?P<subject>[A-Za-z][A-Za-z0-9-]*)"
        r"(?P<tail>[^.;]*)", value, re.I,
    )
    if unaffected:
        condition = _condition(unaffected.group("tail"))
        subject = f"{unaffected.group('subject')} pretreatment"
        for object_ in _items(unaffected.group("objects")):
            events.append(_event(
                value, unaffected, subject_raw=unaffected.group("subject"), subject=subject,
                predicate="does_not_change", object_raw=object_, object_=object_,
                construction="coordinated_unaffected", condition=condition, polarity="negative",
            ))

    contrast_no_effect = re.search(
        r"^(?P<subject>[^,.;]+?)\s+(?:significantly\s+|substantially\s+|markedly\s+)?"
        r"(?:increased|decreased|reduced)\s+[^.;]+?,\s+but\s+did\s+not\s+affect\s+"
        r"(?:the\s+)?(?P<objects>[^.;]+)", value, re.I,
    )
    if contrast_no_effect:
        for object_ in _items(contrast_no_effect.group("objects")):
            events.append(_event(
                value, contrast_no_effect, subject_raw=contrast_no_effect.group("subject"),
                subject=clean_text(contrast_no_effect.group("subject")), predicate="does_not_change",
                object_raw=object_, object_=object_, construction="contrast_no_effect",
                condition=_condition(value), polarity="negative",
            ))

    did_not_affect = re.search(
        r"(?P<subject>[^,.;]+?)\s+did\s+not\s+affect\s+(?:the\s+)?(?P<objects>[^,.;]+)",
        value, re.I,
    )
    if did_not_affect and clean_text(did_not_affect.group("subject")).casefold() not in {"but", "however"}:
        for object_ in _items(did_not_affect.group("objects")):
            events.append(_event(
                value, did_not_affect, subject_raw=did_not_affect.group("subject"),
                subject=clean_text(did_not_affect.group("subject")), predicate="does_not_change",
                object_raw=object_, object_=object_, construction="did_not_affect",
                condition=_condition(value), polarity="negative",
            ))

    no_effect = re.search(
        r"(?P<subject>[^,.;]+?)\s+had\s+no\s+(?:significant\s+)?effect\s+on\s+"
        r"(?P<objects>[^.;]+?)(?=\s+except\b|\s+under\s+|\s+in\s+|$)"
        r"(?P<tail>.*)$", value, re.I,
    )
    if no_effect:
        subject = clean_text(no_effect.group("subject"))
        subject = re.sub(r"^The\s+", "", subject, flags=re.I)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", subject):
            subject += " pretreatment"
        for object_ in _items(no_effect.group("objects")):
            events.append(_event(
                value, no_effect, subject_raw=no_effect.group("subject"), subject=subject,
                predicate="does_not_change", object_raw=object_, object_=object_,
                construction="no_effect_on", condition=(
                    clean_text(no_effect.group("tail"))
                    if no_effect.group("tail").strip().casefold().startswith("except")
                    else _condition(no_effect.group("tail"))
                ),
                polarity="negative",
            ))

    # Parallel measurements and outcomes: "16%, 7%, or 32% higher A, B, or C".
    aligned = re.search(
        r"(?P<subject>[^,.;]+?)\s+(?:demonstrated|showed|had)\s+(?:a\s+)?"
        r"(?P<values>\d+(?:\.\d+)?%(?:,\s*\d+(?:\.\d+)?%)*(?:,?\s+or\s+\d+(?:\.\d+)?%)?)\s+"
        r"(?:significantly\s+)?(?P<direction>higher|lower)\s+"
        r"(?P<objects>[^.;]+?)\s+than\s+(?P<comparator>[^.;]+)$", value, re.I,
    )
    if aligned:
        values = tuple(re.findall(r"\d+(?:\.\d+)?%", aligned.group("values")))
        objects = _items(aligned.group("objects").replace(" or ", " and "))
        if len(values) == len(objects):
            subject_raw = aligned.group("subject")
            treatment = re.search(r"(?P<name>[A-Za-z][A-Za-z0-9-]*)-pretreated", subject_raw, re.I)
            subject = f"{treatment.group('name')} pretreatment" if treatment else clean_text(subject_raw)
            comparator_raw = clean_text(aligned.group("comparator"))
            exposed = re.search(r"\bexposed\s+to\s+(?P<setting>.+)$", comparator_raw, re.I)
            condition = (f"under {clean_text(exposed.group('setting'))}" if exposed
                         else _condition(comparator_raw))
            comparator_core = re.sub(r"\s+(?:under|during|in|exposed\s+to)\s+.+$", "", comparator_raw, flags=re.I)
            comparator = f"relative to {comparator_core}"
            predicate = "increases" if aligned.group("direction").casefold() == "higher" else "decreases"
            for amount, object_ in zip(values, objects):
                events.append(_event(
                    value, aligned, subject_raw=subject_raw, subject=subject, predicate=predicate,
                    object_raw=object_, object_=f"{object_} by {amount}",
                    construction="aligned_measurement_comparison", condition=condition,
                    comparator=comparator, measurement=amount,
                ))

    # Reporting wrappers plus an intervention and a coordinated outcome list.
    reported_effect = re.search(
        r"(?:results?|findings?|data)\s+(?:proved|showed|demonstrated|revealed|confirmed)\s+that\s+"
        r"(?P<subject>[^,.;]+?)\s+(?:significantly\s+)?"
        r"(?P<verb>inhibited|promoted|increased|decreased|reduced)\s+"
        r"(?:the\s+)?(?P<objects>[^.;]+)", value, re.I,
    )
    if reported_effect:
        predicate = {"inhibited":"inhibits","promoted":"promotes","increased":"increases","decreased":"decreases","reduced":"decreases"}[reported_effect.group("verb").casefold()]
        objects = clean_text(reported_effect.group("objects"))
        cells = re.search(r"\bof\s+(?P<cells>[A-Za-z0-9-]+\s+cells)\b", objects, re.I)
        condition = f"in {clean_text(cells.group('cells'))}" if cells else None
        objects = re.sub(r"\s+of\s+[A-Za-z0-9-]+\s+cells.*$", "", objects, flags=re.I)
        object_items = list(_items(objects))
        if len(object_items) == 2 and object_items[1].casefold().endswith(" ability") and not object_items[0].casefold().endswith(" ability"):
            object_items[0] += " ability"
        for object_ in object_items:
            events.append(_event(
                value, reported_effect, subject_raw=reported_effect.group("subject"),
                subject=clean_text(reported_effect.group("subject")), predicate=predicate,
                object_raw=object_, object_=object_, construction="reported_coordinated_effect",
                condition=condition,
            ))

    role = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+(?P<modal>may|might|could)\s+play\s+"
        r"(?:an?\s+)?(?:important\s+)?role\s+in\s+(?:the\s+)?(?P<object>[^.;]+)", value, re.I,
    )
    if role:
        events.append(_event(
            value, role, subject_raw=role.group("subject"), subject=role.group("subject"),
            predicate="plays_role_in", object_raw=role.group("object"), object_=role.group("object"),
            construction="modal_role", modality="possible",
        ))

    signature = re.search(
        r"(?P<subject>(?:final\s+)?[^,.;]*?signature)\s+included\s+"
        r"(?P<prefix>weighted\s+expression\s+of\s+)?(?P<items>[^.;]+)", value, re.I,
    )
    if signature:
        subject = state.signature or re.sub(r"^The\s+final\s+", "", clean_text(signature.group("subject")), flags=re.I)
        prefix = clean_text(signature.group("prefix") or "")
        for item in _items(signature.group("items")):
            events.append(_event(
                value, signature, subject_raw=signature.group("subject"), subject=subject,
                predicate="includes", object_raw=item,
                object_=f"{prefix} {item}" if prefix else item,
                construction="signature_membership",
            ))

    signature_generation = re.search(
        r"(?P<subject>cross-validation(?:\s*\([^)]*\))?\s+procedure)\s+"
        r"(?P<action>relaxed\s+[^,.;]+?)\s+that\s+resulted\s+in\s+a\s+"
        r"(?P<object>\d+-gene\s+(?:diagnostic\s+)?signature)(?:\s+for\s+(?P<scope>[^,.;]+))?",
        value, re.I,
    )
    if signature_generation:
        subject = f"{clean_text(signature_generation.group('action'))} cross-validation"
        events.append(_event(
            value, signature_generation, subject_raw=signature_generation.group("subject"),
            subject=subject, predicate="produces", object_raw=signature_generation.group("object"),
            object_=signature_generation.group("object"), construction="signature_generation",
            condition=(f"for {clean_text(signature_generation.group('scope'))}"
                       if signature_generation.group("scope") else None),
        ))

    cv_auc = re.search(
        r"(?P<metric>CV[- ]area\s+under\s+the\s+curve\s*\[AUC\]|CV[- ]AUC|AUC)\s*=\s*"
        r"(?P<value>\d+(?:\.\d+)?)", value, re.I,
    )
    if cv_auc:
        subject = state.signature or state.heading or "model"
        events.append(_event(
            value, cv_auc, subject_raw=cv_auc.group("metric"), subject=subject,
            predicate="has_cv_auc", object_raw=cv_auc.group("value"), object_=cv_auc.group("value"),
            construction="cv_performance_metric", measurement=cv_auc.group("value"),
        ))

    expression_groups = re.search(
        r"(?P<genes>[A-Z][A-Z0-9-]*(?:,\s*[A-Z][A-Z0-9-]*)*(?:\s+and\s+[A-Z][A-Z0-9-]*)?)\s+"
        r"exhibiting\s+higher\s+expression\s+in\s+(?P<group>[^,.;]+?)"
        r"(?=\s+and\s+(?:the\s+)?(?:interferon-related\s+)?gene\b|$)", value,
    )
    if expression_groups:
        for gene in _items(expression_groups.group("genes")):
            events.append(_event(
                value, expression_groups, subject_raw=gene, subject=f"{gene} expression",
                predicate="higher_in", object_raw=expression_groups.group("group"),
                object_=expression_groups.group("group"), construction="coordinated_expression_group",
            ))
    for single in re.finditer(
        r"gene\s+(?P<gene>[A-Z][A-Z0-9-]*)\s+exhibiting\s+higher\s+expression\s+in\s+"
        r"(?P<group>[^,.;]+)", value,
    ):
        events.append(_event(
            value, single, subject_raw=single.group("gene"), subject=f"{single.group('gene')} expression",
            predicate="higher_in", object_raw=single.group("group"), object_=single.group("group"),
            construction="expression_group",
        ))

    group_contrast = re.search(
        r"(?P<genes>[A-Z][A-Z0-9-]*\s+and\s+[A-Z][A-Z0-9-]*)\s+expression\s+levels\s+"
        r"were\s+not\s+distinctly\s+different\s+between\s+(?P<groups>[^,.;]+)", value,
    )
    if group_contrast:
        for gene in _items(group_contrast.group("genes")):
            events.append(_event(
                value, group_contrast, subject_raw=gene, subject=f"{gene} expression levels",
                predicate="not_distinctly_different_between", object_raw=group_contrast.group("groups"),
                object_=group_contrast.group("groups"), construction="negative_group_contrast",
                polarity="negative",
            ))
    distinct = re.search(
        r"(?P<genes>[A-Z][A-Z0-9-]*\s+and\s+[A-Z][A-Z0-9-]*)\s+showed\s+"
        r"(?:clearly\s+)?distinct\s+patterns\s+in\s+(?:the\s+)?(?P<groups>[^,.;]+)", value,
    )
    if distinct:
        group_object = re.sub(r"\s*\([^)]*$", "", clean_text(distinct.group("groups")))
        for gene in _items(distinct.group("genes")):
            events.append(_event(
                value, distinct, subject_raw=gene, subject=f"{gene} expression",
                predicate="shows_distinct_patterns_across", object_raw=distinct.group("groups"),
                object_=group_object, construction="distinct_group_patterns",
            ))

    # Comparative model performance and data requirements.
    comparison = re.search(
        r"(?P<subject>[^,.;]+?models)\s+outperformed\s+(?P<object>[^,.;]+?models)"
        r"(?:\s+and\s+required\s+(?P<amount>less|more)\s+(?P<resource>training\s+data[^,.;]*))?",
        value, re.I,
    )
    if comparison:
        condition = clean_text(value[:comparison.start()].strip(" ,")) or None
        events.append(_event(
            value, comparison, subject_raw=comparison.group("subject"), subject=comparison.group("subject"),
            predicate="outperforms", object_raw=comparison.group("object"), object_=comparison.group("object"),
            construction="model_outperformance", condition=condition,
        ))
        if comparison.group("amount"):
            events.append(_event(
                value, comparison, subject_raw=comparison.group("subject"), subject=comparison.group("subject"),
                predicate="requires_less" if comparison.group("amount").casefold()=="less" else "requires_more",
                object_raw=comparison.group("resource"), object_=comparison.group("resource"),
                construction="model_resource_comparison", condition=condition,
            ))

    local_target_match = re.search(
        r"(?P<target>median\s+[A-Za-z][A-Za-z0-9]*\s+(?:greater\s+than|less\s+than|of)\s+\d+(?:\.\d+)?)",
        value, re.I,
    )
    local_target = clean_text(local_target_match.group("target")) if local_target_match else None
    for requirement in re.finditer(
        r"(?P<subject>[^,.;]+?models)\s+required\s+(?P<amount>(?:more|less)\s+than\s+"
        r"(?:\d+\s*min|an\s+hour))(?:\s+of\s+training\s+data)?(?:\s+to\s+(?P<target>[^,]+))?",
        value, re.I,
    ):
        target = clean_text(requirement.group("target") or "")
        if target.casefold() == "reach the same performance level" and state.performance_target:
            target = f"achieve {state.performance_target}"
        elif not target and local_target and (
            re.search(r"\bwhereas\b", value[:requirement.start()], re.I)
            or re.match(r"\s*whereas\b", requirement.group("subject"), re.I)
        ):
            target = f"achieve {local_target}"
        requirement_subject = re.sub(r"^(?:whereas|in\s+contrast,?)\s+", "", clean_text(requirement.group("subject")), flags=re.I)
        events.append(_event(
            value, requirement, subject_raw=requirement.group("subject"), subject=requirement_subject,
            predicate="requires", object_raw=requirement.group("amount"),
            object_=f"{clean_text(requirement.group('amount'))} of training data",
            construction="training_requirement", condition=target or None,
            measurement=clean_text(requirement.group("amount")),
        ))

    gain = re.search(
        r"(?P<subject>This\s+performance\s+gain)\s+was\s+observed\s+across\s+"
        r"(?P<object>all\s+tested\s+stimulus\s+domains)", value, re.I,
    )
    if gain:
        events.append(_event(
            value, gain, subject_raw=gain.group("subject"), subject="foundation-model performance gain",
            predicate="occurs_across", object_raw=gain.group("object"), object_=gain.group("object"),
            construction="performance_generalization",
            condition=("including out-of-distribution stimulus domains" if "out-of-distribution" in value
                       else "including new stimulus domains" if "new stimulus domains" in value else None),
        ))

    more_accurate = re.search(
        r"(?P<subject>[^,.;]+?models)\s+were\s+more\s+accurate\s+at\s+predicting\s+"
        r"(?P<object>[^,.;]+?)\s+and\s+required\s+(?:substantially\s+)?less\s+"
        r"(?P<resource>training\s+data[^,.;]*)", value, re.I,
    )
    if more_accurate:
        events.append(_event(
            value, more_accurate, subject_raw=more_accurate.group("subject"), subject=more_accurate.group("subject"),
            predicate="more_accurate_than", object_raw=more_accurate.group("object"),
            object_="individual models", construction="accuracy_comparison",
            condition=f"when predicting {clean_text(more_accurate.group('object'))}",
        ))
        events.append(_event(
            value, more_accurate, subject_raw=more_accurate.group("subject"), subject=more_accurate.group("subject"),
            predicate="requires_less", object_raw=more_accurate.group("resource"),
            object_=f"{clean_text(more_accurate.group('resource'))} than individual models",
            construction="resource_comparison",
            condition=f"when predicting {clean_text(more_accurate.group('object'))}",
        ))

    achievement = re.search(
        r"(?P<subject>[^,.;]+?models)\s+were\s+able\s+to\s+achieve\s+(?:a\s+performance\s+of\s+)?"
        r"(?P<target>median\s+[A-Za-z][A-Za-z0-9]*\s+(?:greater\s+than|less\s+than|of)\s+"
        r"\d+(?:\.\d+)?)\s+using\s+(?P<data>[^,.;]+)", value, re.I,
    )
    if achievement:
        lead = re.search(r"when\s+predicting\s+(?P<task>[^,]+)", value[:achievement.start()], re.I)
        condition = f"for {clean_text(lead.group('task'))} using {clean_text(achievement.group('data'))}" if lead else f"using {clean_text(achievement.group('data'))}"
        events.append(_event(
            value, achievement, subject_raw=achievement.group("subject"), subject=achievement.group("subject"),
            predicate="achieves", object_raw=achievement.group("target"), object_=achievement.group("target"),
            construction="performance_achievement", condition=condition,
        ))

    conclusion = re.search(
        r"training\s+(?P<subject>.+?)\s+produces\s+(?:a\s+)?"
        r"(?P<object>robust\s+and\s+transferable\s+representation\s+of\s+[^,.;]+?)\s+"
        r"that\s+generalizes\s+to\s+(?P<target>[^,.;]+?)\s+and\s+improves\s+"
        r"(?P<improvements>[^.;]+)", value, re.I,
    )
    if conclusion:
        representation = clean_text(conclusion.group("object"))
        training_subject = clean_text(conclusion.group("subject"))
        pooled = re.search(r"(?P<core>.+?)\s+on\s+(?P<context>natural\s+video\s+data.+)$", training_subject, re.I)
        core = clean_text(pooled.group("core")) if pooled else training_subject
        compact_subject = f"training {core}"
        training_condition = f"on {clean_text(pooled.group('context'))}" if pooled else None
        representation_subject = (
            re.sub(r"\s+", "-", re.sub(r"^an?\s+", "", core, flags=re.I)).casefold()
            + " representation"
        )
        events.append(_event(value, conclusion, subject_raw=conclusion.group("subject"), subject=compact_subject, predicate="produces", object_raw=conclusion.group("object"), object_=representation, construction="generalization_conclusion", condition=training_condition))
        events.append(_event(value, conclusion, subject_raw=conclusion.group("object"), subject=representation_subject, predicate="generalizes_to", object_raw=conclusion.group("target"), object_=conclusion.group("target"), construction="generalization_conclusion"))
        improvements = re.sub(r"^model\s+performance\s+", "", conclusion.group("improvements"), flags=re.I)
        improvements = re.sub(r"^for\s+", "", improvements, flags=re.I)
        for domain in _items(improvements.replace(" and for ", " and ")):
            events.append(_event(value, conclusion, subject_raw=conclusion.group("object"), subject=representation_subject, predicate="improves", object_raw=domain, object_=f"model performance for {domain}", construction="generalization_conclusion"))

    # Classifier statements with attached metrics.
    classifier = re.search(
        r"(?P<subject>(?:The\s+)?[^,.;]+?model)\s+classified\s+(?P<object>[^,.;]+?)\s+"
        r"with\s+(?P<quality>high\s+accuracy)\s+when\s+(?P<condition>[^:]+):",
        value, re.I,
    )
    model_subject = None
    if classifier:
        model_subject = _model_subject(classifier.group("subject"))
        events.append(_event(
            value, classifier, subject_raw=classifier.group("subject"), subject=model_subject,
            predicate="classifies", object_raw=classifier.group("object"),
            object_=f"{clean_text(classifier.group('object'))} with high accuracy",
            construction="classifier_performance", condition=clean_text(classifier.group("condition")),
        ))
    else:
        bare_model = re.search(r"(?P<subject>[A-Za-z][A-Za-z0-9/-]*(?:\s*\([^)]*\))?\s+model)", value)
        if bare_model:
            model_subject = _model_subject(bare_model.group("subject"))
    metric_pattern = re.compile(
        r"(?P<name>AUROC|AUC|sensitivity|specificity|overall\s+accuracy|accuracy)\s+of\s+"
        r"(?P<value>\d+(?:\.\d+)?%?)(?:\s*\((?P<ci>95%\s+CI\s+[^)]+)\))?",
        re.I,
    )
    metric_matches = list(metric_pattern.finditer(value))
    if metric_matches:
        subject = model_subject or "model"
        condition = "internal fivefold cross-validation" if "internally validated" in value else (
            state.validation_context
        )
        for metric in metric_matches:
            name = _metric_name(metric.group("name"))
            result = metric.group("value") + (f" ({clean_text(metric.group('ci'))})" if metric.group("ci") else "")
            events.append(_event(
                value, metric, subject_raw=metric.group("name"), subject=subject,
                predicate=_metric_predicate(name), object_raw=metric.group("value"), object_=result,
                construction="diagnostic_metric", condition=condition, measurement=result,
            ))

    stratified = re.search(
        r"(?P<subject>(?:The\s+)?model)\s+demonstrated\s+similar\s+performance\s+"
        r"after\s+stratifying\s+for\s+(?P<factors>[^.;]+)", value, re.I,
    )
    if stratified:
        subject = state.model or "model"
        factors = re.sub(r"\([^)]*\)", "", stratified.group("factors"))
        factors = re.sub(r"\s*\([^)]*$", "", factors)
        for factor in _items(factors.replace(" or ", " and ")):
            events.append(_event(
                value, stratified, subject_raw=stratified.group("subject"), subject=f"{subject} performance" if not subject.casefold().endswith("performance") else subject,
                predicate="remains_similar_after_stratifying_by", object_raw=factor, object_=factor,
                construction="stratified_performance",
            ))

    examples = re.search(
        r"(?P<subject>[A-Za-z][A-Za-z0-9/-]*)\s+discriminated\s+[^.;]+?,\s+such\s+as\s+"
        r"(?P<items>.+)$", value, re.I,
    )
    if examples:
        condition = clean_text(value[
            examples.end("subject"):examples.start("items")
        ])
        condition = re.sub(
            r"^(?:discriminated|distinguished)\s+", "", condition, flags=re.I,
        ).rstrip(" ,:;")
        raw_items = re.sub(r"\s*\([^)]*\)\s*$", "", examples.group("items"))
        raw_items = raw_items.rstrip(" .")
        for item in _items(raw_items):
            events.append(_event(
                value, examples, subject_raw=examples.group("subject"),
                subject=f"{examples.group('subject')} model" if not examples.group("subject").casefold().endswith("model") else examples.group("subject"),
                predicate="discriminates", object_raw=item, object_=item,
                construction="classifier_examples",
                condition=condition or None,
            ))

    # Dedupe semantic cores within this layer.
    unique: list[EventHypothesis] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    for event in events:
        key = (event.subject.normalized.casefold(), event.predicate,
               event.object.normalized.casefold(), event.qualifiers.render())
        if key not in seen and all((event.subject.normalized, event.predicate, event.object.normalized)):
            seen.add(key)
            unique.append(event)
    return unique

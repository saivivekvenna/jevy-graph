"""Optional dependency-tree compiler for scientific findings.

The core package has no NLP dependency.  This module imports spaCy only when
``DependencyScientificCompiler`` is constructed, so the existing lightweight
extractor continues to work unchanged.  The compiler is deliberately lexical
and structural: a relation is emitted only when one dependency tree supplies
both arguments.
"""
from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from .mentions import clean_text, normalize_intervention, normalized_mention
from .model import EventHypothesis, ScientificContext, ScientificQualifiers, SourceSpan


class DependencyParserUnavailable(RuntimeError):
    """Raised when the optional scientific parser is not installed."""


_PREDICATES = {
    "abrogate": "abrogates",
    "activate": "activates",
    "affect": "affects",
    "associate": "associated_with",
    "arise": "arises_from",
    "attribute": "attributed_to",
    "attenuate": "attenuates",
    "block": "blocks",
    "cause": "causes",
    "classify": "classifies",
    "correlate": "correlated_with",
    "decrease": "decreases",
    "differ": "differs_from",
    "diminish": "decreases",
    "demonstrate": "demonstrates",
    "discriminate": "discriminates",
    "enhance": "enhances",
    "elevate": "increases",
    "exhibit": "exhibits",
    "follow": "follows",
    "generalize": "generalizes_to",
    "improve": "improves",
    "impair": "impairs",
    "increase": "increases",
    "induce": "induces",
    "inhibit": "inhibits",
    "mediate": "mediates",
    "overlap": "overlaps_with",
    "outperform": "outperforms",
    "predict": "predicts",
    "promote": "promotes",
    "reduce": "decreases",
    "require": "requires",
    "result": "results_in",
    "suppress": "suppresses",
    "achieve": "achieves",
    "produce": "produces",
    "prevent": "prevents",
    "protect": "protects_against",
    "restore": "restores",
    "regulate": "regulates",
    "stimulate": "stimulates",
    "upregulate": "upregulated_in",
    "downregulate": "downregulated_in",
    "underperform": "underperforms",
    "depend": "depends_on",
    "link": "linked_to",
    "lead": "results_in",
}
_BASE_PREDICATE_LEMMAS = {
    "activate", "affect", "associate", "attenuate", "cause", "classify",
    "correlate", "decrease", "demonstrate", "discriminate", "enhance",
    "exhibit", "generalize", "improve", "increase", "induce", "inhibit",
    "mediate", "outperform", "predict", "promote", "reduce", "require",
    "result", "suppress", "achieve", "produce", "prevent", "protect",
    "restore", "regulate", "depend", "link",
}

_REPORTING = {
    "show", "reveal", "indicate", "suggest", "confirm", "find", "observe",
    "report", "prove", "support",
}
_PROCEDURE = {
    "analyze", "assess", "calculate", "collect", "conduct", "construct",
    "detect", "determine", "estimate", "evaluate", "examine", "fit", "measure",
    "perform", "sequence", "train", "use", "validate",
}
_MODALS = {"may", "might", "could", "can", "would", "should"}
_NOMINAL_DEPS = {
    "amod", "compound", "nummod", "poss", "quantmod", "dep", "appos", "flat",
    "fixed",
}
_ARG_DEPS = {"dobj", "obj", "attr", "oprd", "dative"}
_SUBJECT_DEPS = {"nsubj", "csubj"}
_PASSIVE_SUBJECT_DEPS = {"nsubjpass", "csubjpass"}


def _case_words(token: Any) -> tuple[str, ...]:
    return tuple(child.text.casefold() for child in token.children if child.dep_ == "case")


def _ordered(tokens: Iterable[Any]) -> list[Any]:
    return sorted({token.i: token for token in tokens}.values(), key=lambda token: token.i)


def _trim_phrase(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\s+([%°])", r"\1", value)
    value = re.sub(r"^(?:the|an?|these|those)\s+", "", value, flags=re.I)
    return value.strip(" ,.;:")


class DependencyScientificCompiler:
    """Assemble atomic scientific claims from dependency-bound spans."""

    def __init__(
        self, model: str = "en_core_sci_sm", *, nlp: Any | None = None,
        grammar: bool = True,
    ) -> None:
        self.grammar = grammar
        if nlp is not None:
            self.nlp = nlp
            self.model = model
            return
        try:
            import spacy
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise DependencyParserUnavailable(
                "Install the 'scientific-parser' extra and a scispaCy model "
                "such as en_core_sci_sm."
            ) from exc
        try:
            self.nlp = spacy.load(model)
        except OSError as exc:  # pragma: no cover - environment dependent
            raise DependencyParserUnavailable(
                f"spaCy model {model!r} is not installed."
            ) from exc
        self.model = model

    def compile(
        self,
        text: str,
        state: ScientificContext,
        *,
        classification: str = "finding",
    ) -> tuple[EventHypothesis, ...]:
        if classification in {"heading", "procedure", "purpose"}:
            return ()
        doc = self.nlp(text)
        events: list[EventHypothesis] = (
            list(self._idioms(doc, text)) if self.grammar else []
        )
        for sentence in doc.sents:
            reporting_modality = self._reporting_modality(sentence)
            for relation in self._relations(sentence):
                lemma = relation.lemma_.casefold()
                if lemma in _REPORTING or lemma in _PROCEDURE:
                    continue
                predicate = self._predicate(relation)
                if predicate is None:
                    continue
                passive = self._passive_subject(relation)
                if passive is not None:
                    subjects = self._agents(relation)
                    objects = self._coordinated(passive)
                else:
                    subjects = self._subjects(relation)
                    objects = self._objects(relation)
                if not subjects or not objects:
                    continue
                negated = self._negated(relation)
                if negated and lemma == "affect":
                    predicate = "does_not_change"
                elif negated and lemma == "differ":
                    predicate = "does_not_differ_from"
                modality = self._modality(relation, reporting_modality)
                conditions = self._conditions(relation, subjects, objects)
                measurements = self._measurements(relation)
                anchor = SourceSpan(
                    relation.idx, relation.idx + len(relation.text), relation.text,
                )
                for subject_head in subjects:
                    subject_raw = self._phrase(subject_head, role="subject")
                    subject = normalize_intervention(subject_raw)
                    for object_head in objects:
                        object_ = self._phrase(object_head, role="object")
                        object_ = self._directional_object(relation, object_)
                        if not self._valid_arguments(subject, object_):
                            continue
                        qualifiers = ScientificQualifiers(
                            polarity="negative" if negated else "positive",
                            modality=modality,
                            conditions=conditions,
                            measurements=measurements,
                        )
                        events.append(EventHypothesis(
                            normalized_mention(
                                subject_raw, subject, source=text,
                            ),
                            predicate,
                            normalized_mention(
                                self._phrase(object_head, role="object"), object_,
                                kind="outcome", source=text,
                            ),
                            qualifiers,
                            anchor,
                            "dependency_bound_event",
                            provenance=(anchor,),
                        ))
        return self._dedupe(events)

    def _relations(self, sentence: Any) -> tuple[Any, ...]:
        relations = []
        for token in sentence:
            lemma = token.lemma_.casefold()
            if (
                not self.grammar and lemma not in _BASE_PREDICATE_LEMMAS
                and not (
                    token.pos_ == "ADJ"
                    and lemma in {"high", "low", "greater", "less", "better", "worse"}
                )
            ):
                continue
            if lemma == "overlap" and token.dep_ in {"amod", "acl", "acl:relcl"}:
                continue
            if token.dep_ == "advcl" and any(
                child.text.casefold() == "when" for child in token.children
            ):
                continue
            if lemma in _PREDICATES or lemma == "affect":
                relations.append(token)
                continue
            # Comparative copular findings: "expression was higher/lower".
            if token.pos_ == "ADJ" and token.lemma_.casefold() in {
                "high", "low", "greater", "less", "better", "worse",
            } and (
                any(child.dep_ == "cop" for child in token.children)
                or (
                    token.dep_ == "amod"
                    and token.head.dep_ in _ARG_DEPS
                    and token.head.head.lemma_.casefold() in {"have", "show", "exhibit"}
                )
            ):
                relations.append(token)
        return tuple(relations)

    def _idioms(self, doc: Any, text: str) -> tuple[EventHypothesis, ...]:
        """Compile productive constructions without direct verb-object arcs."""
        events: list[EventHypothesis] = []
        for sentence in doc.sents:
            # Attribute with a measured value: "X has [attribute] of [value]".
            # The dependency tree supplies the three slots; qualifiers remain
            # separate from both the attribute relation and measured object.
            for relation in sentence:
                if relation.lemma_.casefold() != "have":
                    continue
                subjects = self._subjects(relation)
                attributes = self._direct_children(relation, _ARG_DEPS)
                for attribute in attributes:
                    values = [
                        child for child in attribute.children
                        if child.dep_ in {"nmod", "obl"}
                        and "of" in _case_words(child)
                        and any(token.like_num for token in child.subtree)
                    ]
                    if not values:
                        continue
                    attribute_tokens = [
                        child for child in attribute.children
                        if child.dep_ in {"amod", "compound"}
                    ] + [attribute]
                    attribute_name = _trim_phrase(" ".join(
                        token.text for token in _ordered(attribute_tokens)
                    ))
                    predicate = "has_" + re.sub(
                        r"[^a-z0-9]+", "_", attribute_name.casefold()
                    ).strip("_")
                    for subject_head in subjects:
                        for value_head in values:
                            subject_raw = self._phrase(subject_head, role="subject")
                            value = self._phrase(value_head, role="object")
                            anchor = SourceSpan(
                                relation.idx,
                                relation.idx + len(relation.text),
                                relation.text,
                            )
                            events.append(EventHypothesis(
                                normalized_mention(
                                    subject_raw,
                                    normalize_intervention(subject_raw),
                                    source=text,
                                ),
                                predicate,
                                normalized_mention(
                                    value, value, kind="measurement", source=text,
                                ),
                                ScientificQualifiers(
                                    conditions=self._conditions(
                                        relation, (subject_head,),
                                        (attribute, value_head),
                                    ),
                                    measurements=(value,),
                                ),
                                anchor,
                                "dependency_attribute_measurement",
                                provenance=(anchor,),
                            ))

            # "X was unaffected by Y" means Y did not change X.
            for relation in sentence:
                if relation.lemma_.casefold() != "unaffected":
                    continue
                outcomes = self._direct_children(
                    relation, _SUBJECT_DEPS | _PASSIVE_SUBJECT_DEPS,
                )
                agents = [
                    child for child in relation.children
                    if child.dep_ in {"nmod", "obl"} and "by" in _case_words(child)
                ]
                for agent in self._expand(agents):
                    for outcome in self._expand(outcomes):
                        event = self._make_event(
                            text, agent, "does_not_change", outcome, relation,
                            polarity="negative",
                            conditions=self._conditions(
                                relation, (agent,), (outcome,),
                            ),
                        )
                        if event:
                            events.append(event)

            # "A and B had an effect on C".
            for relation in sentence:
                if relation.lemma_.casefold() != "have":
                    continue
                effects = [
                    child for child in relation.children
                    if child.dep_ in _ARG_DEPS
                    and child.lemma_.casefold() == "effect"
                ]
                if not effects:
                    continue
                targets = [
                    child
                    for parent in (relation, *effects)
                    for child in parent.children
                    if child.dep_ in {"nmod", "obl"}
                    and "on" in _case_words(child)
                ]
                subjects = self._subjects(relation)
                interactive = any(
                    child.lemma_.casefold() == "interactive"
                    for child in effects[0].children
                )
                if interactive and len(subjects) > 1 and targets:
                    start = min(item.idx for item in subjects)
                    end = max(item.idx + len(item.text) for item in subjects)
                    subject_text = text[start:end]
                    subject_match = re.search(re.escape(subject_text), text)
                    if subject_match:
                        events.append(self._text_event(
                            text, subject_text, "interact_to_affect",
                            self._phrase(targets[0], role="object"), subject_match,
                            conditions=(self._phrase(effects[0], role="object"),),
                            construction="dependency_interactive_effect",
                        ))
                    continue
                for subject in subjects:
                    for target in self._expand(targets):
                        event = self._make_event(
                            text, subject, "affects", target, relation,
                            conditions=(self._phrase(effects[0], role="object"),),
                        )
                        if event:
                            events.append(event)

            # "outcome increased/decreased with factor" expresses a
            # directional association with the factor as graph subject.
            for relation in sentence:
                if relation.lemma_.casefold() not in {
                    "increase", "decrease", "reduce",
                } or self._direct_children(relation, _ARG_DEPS):
                    continue
                outcomes = self._direct_children(relation, _SUBJECT_DEPS)
                factors = [
                    child for child in relation.children
                    if child.dep_ in {"nmod", "obl"}
                    and "with" in _case_words(child)
                ]
                for factor in self._expand(factors):
                    for outcome in self._expand(outcomes):
                        event = self._make_event(
                            text, factor,
                            ("increases" if relation.lemma_.casefold() == "increase"
                             else "decreases"),
                            outcome, relation,
                            modality=("tended" if relation.head.lemma_.casefold() == "tend"
                                      else "asserted"),
                            conditions=self._conditions(
                                relation, (factor,), (outcome,),
                            ),
                        )
                        if event:
                            events.append(event)

        # Comparative group counts: "N patients (rate, CI) in group ... died."
        mortality = re.search(
            r"(?P<n1>\d+)\s+patients?\s*\((?P<rate1>\d+(?:\.\d+)?%)\s*,\s*"
            r"(?P<ci1>95%\s*CI:[^)]+)\)\s+in\s+the\s+(?P<g1>[^,]+?group)\s*,?\s*"
            r"and\s+(?P<n2>\d+)\s*\((?P<rate2>\d+(?:\.\d+)?%)\s*,\s*"
            r"(?P<ci2>95%\s*CI:[^)]+)\)\s+in\s+the\s+(?P<g2>[^,]+?group)\s+had\s+died",
            text, re.I,
        )
        if mortality:
            for group, rate, ci in (
                ("g1", "rate1", "ci1"), ("g2", "rate2", "ci2"),
            ):
                events.append(self._text_event(
                    text, mortality.group(group), "has_mortality_rate",
                    mortality.group(rate), mortality,
                    conditions=("day 28", clean_text(mortality.group(ci))),
                    construction="dependency_quantified_group_outcome",
                ))

        # "a 5.58% increase in outcome in group compared to comparator".
        for match in re.finditer(
            r"(?P<amount>\d+(?:\.\d+)?%)\s+"
            r"(?P<direction>increase|decrease|reduction)\s+in\s+(?:the\s+)?"
            r"(?P<outcome>[^,.;]+?)\s+in\s+(?:the\s+)?"
            r"(?P<group>[^,.;()]+?group)\s+compared\s+to\s+(?:the\s+)?"
            r"(?P<comparator>[^,.;()]+?group)",
            text, re.I,
        ):
            direction = match.group("direction").casefold()
            events.append(self._text_event(
                text, match.group("group"),
                "increases" if direction == "increase" else "decreases",
                f"{clean_text(match.group('outcome'))} by {match.group('amount')}",
                match,
                conditions=(f"versus {clean_text(match.group('comparator'))}",),
                construction="dependency_nominal_group_comparison",
            ))

        # "the rate ... was increased by 7.47% in group compared to ...".
        for match in re.finditer(
            r"(?P<outcome>(?:the\s+)?[^,.;]+?)\s+was\s+"
            r"(?P<direction>increased|decreased|reduced)\s+by\s+"
            r"(?P<amount>\d+(?:\.\d+)?%)\s+in\s+(?:the\s+)?"
            r"(?P<group>[^,.;()]+?group)\s+compared\s+to\s+(?:the\s+)?"
            r"(?P<comparator>[^,.;()]+?group)",
            text, re.I,
        ):
            events.append(self._text_event(
                text, match.group("group"),
                ("increases" if match.group("direction").casefold() == "increased"
                 else "decreases"),
                f"{clean_text(match.group('outcome'))} by {match.group('amount')}",
                match,
                conditions=(f"versus {clean_text(match.group('comparator'))}",),
                construction="dependency_passive_group_comparison",
            ))

        # "a decreased outcome was observed in group compared to control".
        for match in re.finditer(
            r"A\s+(?P<direction>decreased|increased|higher|lower)\s+"
            r"(?P<outcome>[^,.;]+?)\s+was\s+observed\s+in\s+(?:the\s+)?"
            r"(?P<group>[^,.;]+?group)\s+compared\s+to\s+(?:the\s+)?"
            r"(?P<comparator>[^,.;]+?group)(?P<tail>[^.;]*)",
            text, re.I,
        ):
            lower = match.group("direction").casefold() in {"decreased", "lower"}
            events.append(self._text_event(
                text, match.group("group"), "has_lower" if lower else "has_higher",
                match.group("outcome"), match,
                conditions=(
                    f"versus {clean_text(match.group('comparator'))}",
                    clean_text(match.group("tail")),
                ),
                construction="dependency_observed_group_comparison",
            ))
            difference = re.search(
                r"rate\s+difference\s+(?:at|of|was)\s+(?P<value>\d+(?:\.\d+)?%)"
                r"\s*\((?P<ci>95%\s*CI:[^)]+)\)", match.group("tail"), re.I,
            )
            if difference:
                events.append(self._text_event(
                    text,
                    f"{clean_text(match.group('group'))} versus "
                    f"{clean_text(match.group('comparator'))}",
                    "has_rate_difference", difference.group("value"), match,
                    conditions=(clean_text(difference.group("ci")),),
                    construction="dependency_observed_group_comparison",
                ))

        # Preserve the primary and comparator values printed after a group
        # comparison, e.g. ``(90.20% vs 84.62%)``.
        for match in re.finditer(
            r"(?P<outcome>(?:rate\s+of\s+)?[A-Za-z -]+?)\s+(?:on|by)\s+day\s+"
            r"(?P<day>\d+)[^.;]*?in\s+(?:the\s+)?(?P<group>[^,.;()]+?group)\s+"
            r"compared\s+to\s+(?:the\s+)?(?P<comparator>[^,.;()]+?group)\s*"
            r"\((?P<v1>\d+(?:\.\d+)?%)\s+vs\s+(?P<v2>\d+(?:\.\d+)?%)\)",
            text, re.I,
        ):
            metric = re.sub(r"\s+", "_", clean_text(match.group("outcome")).casefold())
            events.append(self._text_event(
                text, match.group("group"), f"has_{metric}", match.group("v1"), match,
                conditions=(
                    f"day {match.group('day')}",
                    f"{clean_text(match.group('comparator'))} {match.group('v2')}",
                ), construction="dependency_group_rate_assignment",
            ))

        # Conditional directional change: "when X increased by A, Y
        # increased/decreased by B".
        for match in re.finditer(
            r"when\s+(?P<factor>[^,.;]+?)\s+(?:increased|decreased)\s+by\s+"
            r"(?P<factor_amount>[^,.;]+),\s*(?P<outcome>[^,.;]+?)\s+"
            r"(?P<direction>increased|decreased|reduced)\s+by\s+"
            r"(?P<amount>\d+(?:\.\d+)?%)(?P<tail>[^.;]*)",
            text, re.I,
        ):
            events.append(self._text_event(
                text,
                f"{clean_text(match.group('factor'))} increase by "
                f"{clean_text(match.group('factor_amount'))}",
                "increases" if match.group("direction").casefold() == "increased" else "decreases",
                f"{clean_text(match.group('outcome'))} by {match.group('amount')}",
                match, conditions=(clean_text(match.group("tail")),),
                construction="dependency_conditional_direction",
            ))

        # "X resulted in better performance than Y".
        for match in re.finditer(
            r"(?P<subject>[A-Za-z][A-Za-z0-9-]*)\s+resulted\s+in\s+"
            r"better\s+(?P<metric>[^,.;]+?)\s+than\s+"
            r"(?P<comparator>[A-Za-z][A-Za-z0-9-]*)",
            text, re.I,
        ):
            events.append(self._text_event(
                text, match.group("subject"), "has_better_performance_than",
                match.group("comparator"), match,
                conditions=(f"metric: {clean_text(match.group('metric'))}",),
                construction="dependency_comparative_performance",
            ))

        # Nominal paired change: "X increases Y, accompanied by a decrease in Z".
        for match in re.finditer(
            r"(?P<subject>[^,.;]+?)\s+(?P<first>increases|decreases|reduces)\s+"
            r"(?P<object1>[^,.;]+),\s*accompanied\s+by\s+(?:an?\s+)?"
            r"(?P<direction>increase|decrease|reduction)\s+in\s+"
            r"(?P<object2>[^,.;()]+)", text, re.I,
        ):
            events.append(self._text_event(
                text, match.group("subject"),
                "increases" if match.group("direction").casefold() == "increase" else "decreases",
                match.group("object2"), match,
                construction="dependency_accompanied_change",
            ))
        events.extend(self._metric_events(text))

        # Comparative performance with an ellipsed subject after percentages.
        for match in re.finditer(
            r"For\s+(?P<context>[^,.;]+),\s*(?P<range>[^,.;]+?)\s+"
            r"(?P<subject>[A-Z][A-Z0-9-]*\s+models?)\s+"
            r"(?P<better>outperformed)\s+(?:the\s+)?(?P<object1>[^,.;]+?)\s+"
            r"but\s+(?P<worse>underperformed)\s+(?:the\s+)?(?P<object2>[^,.;]+?)(?:\.|$)",
            text, re.I,
        ):
            condition = f"for {clean_text(match.group('context'))}; {clean_text(match.group('range'))}"
            events.append(self._text_event(
                text, match.group("subject"), "outperforms",
                match.group("object1"), match,
                conditions=(condition,), construction="dependency_elliptic_comparison",
            ))
            events.append(self._text_event(
                text, match.group("subject"), "underperforms",
                match.group("object2"), match,
                conditions=(condition,), construction="dependency_elliptic_comparison",
            ))
        return tuple(events)

    def _metric_events(self, text: str) -> tuple[EventHypothesis, ...]:
        """Bind quantities to entities using scientific unit grammar."""
        events: list[EventHypothesis] = []
        value = (
            r"\d+(?:\.\d+)?(?:\s*[×x]\s*10[−–-]?\d+)?\s*"
            r"(?:mS\s*cm[⁻−–-]?1|S\s*cm[⁻−–-]?1|eV)"
        )
        # ``compile`` already receives one clause.  Avoid punctuation based
        # splitting here because decimal measurements contain periods.
        for sentence_match in re.finditer(r"[\s\S]+", text):
            sentence = sentence_match.group(0)
            lower = sentence.casefold()
            if "activation energy" in lower:
                predicate = "has_activation_energy"
            elif "electronic conductiv" in lower:
                predicate = "has_electronic_conductivity"
            elif "conductiv" in lower:
                predicate = "has_ionic_conductivity"
            else:
                predicate = ""
            if predicate:
                # Values preceding an explicit entity: "0.31 eV for X".
                for match in re.finditer(
                    rf"(?P<value>{value})\s+for\s+(?P<entity>[A-Za-z][A-Za-z0-9+−-]+)",
                    sentence, re.I,
                ):
                    events.append(self._text_event(
                        text, match.group("entity"), predicate,
                        match.group("value"), self._absolute_match(sentence_match, match),
                        construction="dependency_unit_assignment",
                    ))
                # Entity introduced first: "For X, ... conductivity of VALUE".
                for match in re.finditer(
                    rf"For\s+(?P<entity>[A-Za-z][A-Za-z0-9+−-]+),[^.;]*?"
                    rf"(?:conductivity|energy)[^.;]*?(?:of|to|is)\s+(?P<value>{value})",
                    sentence, re.I,
                ):
                    events.append(self._text_event(
                        text, match.group("entity"), predicate,
                        match.group("value"), self._absolute_match(sentence_match, match),
                        construction="dependency_unit_assignment",
                    ))
                # Relative-clause value: "that of X (0.38 eV)".
                for match in re.finditer(
                    rf"(?:that|those)\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9+−-]+)\s*"
                    rf"\((?P<value>{value})\)", sentence, re.I,
                ):
                    events.append(self._text_event(
                        text, match.group("entity"), predicate,
                        match.group("value"), self._absolute_match(sentence_match, match),
                        construction="dependency_unit_assignment",
                    ))

            # A metric shared across an elliptical list:
            # "DA had a median accuracy of X, whereas LR had Y and FCNN had Z".
            metric_list = re.search(
                r"(?P<e1>[A-Za-z][A-Za-z0-9-]*(?:\s+model)?)\s+had\s+(?:an?\s+)?"
                r"(?P<metric>[A-Za-z -]+?)\s+of\s+(?P<v1>\d+(?:\.\d+)?)"
                r"(?P<tail>.+)", sentence, re.I,
            )
            if metric_list:
                metric = _trim_phrase(metric_list.group("metric"))
                predicate_name = "has_" + re.sub(r"[^a-z0-9]+", "_", metric.casefold()).strip("_")
                base = self._absolute_match(sentence_match, metric_list)
                events.append(self._text_event(
                    text, metric_list.group("e1"), predicate_name,
                    metric_list.group("v1"), base,
                    construction="dependency_shared_metric",
                ))
                for match in re.finditer(
                    r"(?P<entity>[A-Z][A-Z0-9-]*)\s+had\s+(?P<value>\d+(?:\.\d+)?)",
                    metric_list.group("tail"),
                ):
                    events.append(self._text_event(
                        text, match.group("entity"), predicate_name,
                        match.group("value"), base,
                        construction="dependency_shared_metric",
                    ))
        return tuple(events)

    @staticmethod
    def _absolute_match(outer: re.Match[str], inner: re.Match[str]) -> re.Match[str]:
        """Return a match-like object whose offsets are absolute in source."""
        class AbsoluteMatch:
            def start(self) -> int:
                return outer.start() + inner.start()

            def end(self) -> int:
                return outer.start() + inner.end()

            def group(self, *args):
                return inner.group(*args)

        return AbsoluteMatch()  # type: ignore[return-value]

    def _make_event(
        self, text: str, subject_head: Any, predicate: str, object_head: Any,
        relation: Any, *, polarity: str = "positive", modality: str = "asserted",
        conditions: tuple[str, ...] = (),
    ) -> EventHypothesis | None:
        subject_raw = self._phrase(subject_head, role="subject")
        object_raw = self._phrase(object_head, role="object")
        if not self._valid_arguments(subject_raw, object_raw):
            return None
        anchor = SourceSpan(
            relation.idx, relation.idx + len(relation.text), relation.text,
        )
        return EventHypothesis(
            normalized_mention(
                subject_raw, normalize_intervention(subject_raw), source=text,
            ),
            predicate,
            normalized_mention(
                object_raw, object_raw, kind="outcome", source=text,
            ),
            ScientificQualifiers(
                polarity=polarity, modality=modality, conditions=conditions,
                measurements=self._measurements(relation),
            ),
            anchor, "dependency_structural_idiom", provenance=(anchor,),
        )

    def _text_event(
        self, text: str, subject: str, predicate: str, object_: str,
        match: re.Match[str], *, conditions: tuple[str, ...] = (),
        construction: str,
    ) -> EventHypothesis:
        anchor = SourceSpan(match.start(), match.end(), match.group(0))
        return EventHypothesis(
            normalized_mention(subject, _trim_phrase(subject), source=text),
            predicate,
            normalized_mention(
                object_, _trim_phrase(object_), kind="outcome", source=text,
            ),
            ScientificQualifiers(conditions=conditions), anchor, construction,
            provenance=(anchor,),
        )

    def _predicate(self, relation: Any) -> str | None:
        lemma = relation.lemma_.casefold()
        if lemma in {"high", "greater", "better"}:
            return "has_higher" if relation.dep_ == "amod" else "higher_than"
        if lemma in {"low", "less", "worse"}:
            return "has_lower" if relation.dep_ == "amod" else "lower_than"
        return _PREDICATES.get(lemma)

    def _direct_children(self, token: Any, deps: set[str]) -> list[Any]:
        return [child for child in token.children if child.dep_ in deps]

    def _inherited(self, relation: Any, deps: set[str]) -> list[Any]:
        direct = self._direct_children(relation, deps)
        if direct:
            return direct
        current = relation
        for _ in range(3):
            if current.head is current:
                break
            current = current.head
            direct = self._direct_children(current, deps)
            if direct:
                return direct
        return []

    def _subjects(self, relation: Any) -> tuple[Any, ...]:
        return self._expand(self._inherited(relation, _SUBJECT_DEPS))

    def _passive_subject(self, relation: Any) -> Any | None:
        values = self._direct_children(relation, _PASSIVE_SUBJECT_DEPS)
        return values[0] if values else None

    def _agents(self, relation: Any) -> tuple[Any, ...]:
        agents = [
            child for child in relation.children
            if child.dep_ in {"nmod", "obl", "agent"} and "by" in _case_words(child)
            and not re.search(r"\d+(?:\.\d+)?\s*%", self._phrase(child, role="subject"))
        ]
        return self._expand(agents)

    def _objects(self, relation: Any) -> tuple[Any, ...]:
        direct = self._direct_children(relation, _ARG_DEPS)
        # scispaCy occasionally attaches a coordinated verb as an adjectival
        # modifier of its object ("increased X but reduced Y").
        if relation.dep_ == "amod" and relation.head.pos_ in {"NOUN", "PROPN"}:
            direct.append(relation.head)
        if not direct and relation.lemma_.casefold() in {"depend", "associate", "correlate", "link", "result", "protect", "arise", "attribute"}:
            direct = [
                child for child in relation.children
                if child.dep_ in {"nmod", "obl", "advcl"}
                and set(_case_words(child)) & {"on", "with", "to", "in", "against", "from", "by"}
            ]
        if not direct and relation.lemma_.casefold() in {"differ", "overlap"}:
            direct = [
                child for child in relation.children
                if child.dep_ in {"nmod", "obl", "advcl"}
                and set(_case_words(child)) & {"from", "with"}
            ]
        if not direct:
            # Coordinated predicates frequently share a trailing object:
            # "knockdown decreases and overexpression increases migration".
            siblings = [
                child for child in relation.children if child.dep_ == "conj"
            ]
            if relation.dep_ == "conj":
                siblings.append(relation.head)
            for sibling in siblings:
                direct.extend(self._direct_children(sibling, _ARG_DEPS))
        if self.grammar and not direct and relation.lemma_.casefold() in {
            "increase", "decrease", "reduce",
        }:
            direct = [
                child for child in relation.children
                if child.dep_ in {"nmod", "obl"} and "by" in _case_words(child)
            ]
        if not direct and relation.pos_ == "ADJ":
            direct = [
                child for child in relation.children
                if child.dep_ in {"advcl", "nmod", "obl"} and "than" in _case_words(child)
            ]
        expanded: list[Any] = []
        if len(direct) > 1:
            direct = [
                head for head in direct
                if not re.fullmatch(r"\d+(?:\.\d+)?%?", self._phrase(head, role="object"))
            ] or direct
        for head in direct:
            # The small scientific parser sometimes analyzes "cell growth and
            # migration" as dobj(cell) -> dep(growth) -> conj(migration).
            dep_nouns = [
                child for child in head.children
                if child.dep_ == "dep" and child.pos_ in {"NOUN", "PROPN"}
            ]
            expanded.extend(self._expand(dep_nouns or (head,)))
        # If an object carries another directional verb ("increased X but
        # reduced Y"), it belongs to that embedded relation, not this one.
        return tuple(
            head for head in expanded
            if not any(
                child.i != relation.i and child.lemma_.casefold() in _PREDICATES
                for child in head.children
            )
        )

    def _expand(self, heads: Iterable[Any]) -> tuple[Any, ...]:
        values: list[Any] = []
        for head in heads:
            values.append(head)
            queue = [head]
            while queue:
                current = queue.pop(0)
                for child in current.children:
                    if child.dep_ == "conj" and child.pos_ in {"NOUN", "PROPN", "PRON"}:
                        values.append(child)
                        queue.append(child)
        return tuple(dict.fromkeys(values))

    def _coordinated(self, head: Any) -> tuple[Any, ...]:
        return self._expand((head,))

    def _phrase(self, head: Any, *, role: str) -> str:
        if role == "subject" and head.pos_ == "VERB":
            return _trim_phrase(" ".join(
                token.text for token in _ordered(head.subtree)
                if token.dep_ != "punct"
            ))
        tokens = [head]
        for child in head.children:
            if child.dep_ in _NOMINAL_DEPS:
                if child.lemma_.casefold() not in _PREDICATES and child.lemma_.casefold() not in {
                    "high", "low", "greater", "less", "better", "worse",
                }:
                    tokens.extend(child.subtree)
            elif child.dep_ == "det" and child.text.casefold() not in {"those", "these"}:
                continue
            elif child.dep_ in {"acl", "relcl"} and role == "subject":
                tokens.extend(child.subtree)
            elif child.dep_ in {"nmod", "obl"} and (
                "of" in _case_words(child)
                or (
                    role == "object"
                    and head.lemma_.casefold() in {
                        "decline", "increase", "decrease", "reduction", "change",
                        "improvement", "difference", "effect",
                    }
                    and set(_case_words(child)) & {"in", "of"}
                )
            ):
                tokens.extend(child.subtree)
        # A conjunct inherits compounds from its coordination head (cell
        # growth and migration -> cell growth; cell migration).
        if head.dep_ == "conj" and head.head.pos_ in {"NOUN", "PROPN"}:
            tokens.extend(
                child for child in head.head.children if child.dep_ == "compound"
            )
        # Share an ``of X`` complement across coordinated nominal subjects:
        # Share an ``of X`` complement across coordinated interventions.
        coordination = head.head if head.dep_ == "conj" else head
        group = [coordination, *(
            child for child in coordination.children if child.dep_ == "conj"
        )]
        if not any(
            child.dep_ in {"nmod", "obl"} and "of" in _case_words(child)
            for child in head.children
        ):
            for member in group:
                for child in member.children:
                    if child.dep_ in {"nmod", "obl"} and "of" in _case_words(child):
                        tokens.extend(child.subtree)
                        break
        if head.dep_ == "dep" and head.head.pos_ in {"NOUN", "PROPN"}:
            # Recover an unusual shared noun modifier from the parse above.
            if head.head.dep_ in _ARG_DEPS:
                tokens.append(head.head)
        if (
            head.dep_ == "conj" and head.head.dep_ == "dep"
            and head.head.head.dep_ in _ARG_DEPS
        ):
            tokens.append(head.head.head)
        return _trim_phrase(" ".join(token.text for token in _ordered(tokens)))

    def _conditions(
        self, relation: Any, subjects: tuple[Any, ...], objects: tuple[Any, ...]
    ) -> tuple[str, ...]:
        argument_ids = {item.i for item in (*subjects, *objects)}
        found: list[str] = []
        search = [relation, *objects]
        if relation.dep_ == "amod" and relation.head.head is not relation.head:
            search.append(relation.head.head)
        for parent in search:
            for child in parent.children:
                if child.i in argument_ids or child.dep_ not in {"nmod", "obl", "advcl"}:
                    continue
                if parent in objects and parent.lemma_.casefold() in {
                    "decline", "increase", "decrease", "reduction", "change",
                    "improvement", "difference", "effect",
                } and set(_case_words(child)) & {"in", "of"}:
                    continue
                cases = _case_words(child)
                if not cases or set(cases) <= {"of", "by", "than", "to", "with", "on", "in", "against"} and relation.lemma_.casefold() in {"depend", "associate", "correlate", "link", "result", "protect"}:
                    continue
                phrase_tokens = list(child.subtree)
                case_tokens = [token for token in phrase_tokens if token.dep_ == "case"]
                if case_tokens and case_tokens[0].text.casefold() == "of":
                    continue
                value = _trim_phrase(" ".join(token.text for token in _ordered(phrase_tokens)))
                if "than" in cases:
                    value = "than " + re.sub(r"^than\s+", "", value, flags=re.I)
                if value and value.casefold() not in {item.casefold() for item in found}:
                    found.append(value)
        sentence_text = relation.sent.text
        for value in re.findall(r"\bin\s+(?:vivo|vitro)\b", sentence_text, re.I):
            if value.casefold() not in {item.casefold() for item in found}:
                found.append(value)
        return tuple(found)

    def _measurements(self, relation: Any) -> tuple[str, ...]:
        text = relation.sent.text
        return tuple(dict.fromkeys(
            match.group(0).strip()
            for match in re.finditer(
                r"\b(?:\d+(?:\.\d+)?\s*%|(?:AUC|AUROC|accuracy|sensitivity|specificity)\s+(?:of\s+)?\d+(?:\.\d+)?%?|p\s*[<=>≤≥]\s*0?\.\d+)",
                text, re.I,
            )
        ))

    def _directional_object(self, relation: Any, value: str) -> str:
        # Preserve comparative magnitude as part of the proposition.
        descendants = " ".join(token.text for token in relation.subtree)
        amount = re.search(r"\b\d+(?:\.\d+)?\s*%", descendants)
        if amount and amount.group(0) not in value and relation.lemma_.casefold() in {
            "increase", "decrease", "reduce", "improve",
        }:
            return f"{value} by {amount.group(0)}"
        return value

    def _negated(self, relation: Any) -> bool:
        return any(child.dep_ == "neg" for child in relation.children)

    def _modality(self, relation: Any, reporting: str | None) -> str:
        for child in relation.children:
            if child.dep_ in {"aux", "auxpass"} and child.lemma_.casefold() in _MODALS:
                return child.lemma_.casefold()
        return reporting or "asserted"

    def _reporting_modality(self, sentence: Any) -> str | None:
        for token in sentence:
            lemma = token.lemma_.casefold()
            if lemma in {"suggest", "indicate"} and any(
                child.dep_ in {"ccomp", "xcomp"} for child in token.children
            ):
                return "suggested"
        return None

    def _valid_arguments(self, subject: str, object_: str) -> bool:
        if not subject or not object_ or subject.casefold() == object_.casefold():
            return False
        if len(subject.split()) > 18 or len(object_.split()) > 24:
            return False
        if subject.casefold() in {"result", "results", "finding", "findings", "data"}:
            return False
        if re.fullmatch(r"(?:it|which|who|that|this|these|those|while|\d+(?:\.\d+)?%?)", subject, re.I):
            return False
        return True

    def _dedupe(self, events: list[EventHypothesis]) -> tuple[EventHypothesis, ...]:
        unique: list[EventHypothesis] = []
        seen: set[tuple[str, str, str, str, str, str | None]] = set()
        for event in events:
            key = (
                event.subject.normalized.casefold(), event.predicate,
                event.object.normalized.casefold(), event.qualifiers.modality or "",
                event.qualifiers.polarity, event.qualifiers.render(),
            )
            if key not in seen:
                seen.add(key)
                unique.append(event)
        return tuple(unique)

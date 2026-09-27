"""Conservative clause assembly for ordinary prose and standalone rules.

The fallback extractor is intentionally broad.  This module handles the
small set of grammatical structures where broad trigger-local slicing loses
meaning: carried subjects, coordinated predicates, anaphora, and qualifiers.
It only returns a result when every top-level branch can be assembled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .models import RelationFrame
from .normalize import canonical_entity, normalize_space


_MODALS = "shall|may|must|can|could|will|would|should"
_ORG_SUFFIX = re.compile(
    r"\b(?:labs?|laborator(?:y|ies)|robotics|systems?|technologies|technology|"
    r"sensors?|company|corporation|corp\.?|inc\.?|ltd\.?|university|agency|"
    r"association|foundation|institute|department|commission|bank)\b",
    re.I,
)
_PERSON = re.compile(
    r"^[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){1,3}$"
)
_DESCRIPTIVE_ORG = re.compile(
    r"^(?:the\s+)?(?:company|organization|firm|business|agency|institution)$",
    re.I,
)
_PRONOUN = re.compile(r"^(?:he|she|it|they)$", re.I)
_LEADING_DEPENDENT = re.compile(
    r"^(?P<condition>(?:if|when|whenever|unless|until|after|before|during)\b.+?),\s*"
    r"(?P<main>.+)$",
    re.I,
)
_BRANCH = re.compile(r",\s*(?:but|although)\s+", re.I)
_ACTIVATION = re.compile(
    r"^(?:if|when|whenever|unless|until|after|before|during)\b.+?,|"
    r"^(?:he|she|it|they|the\s+(?:company|organization|firm|business|agency|institution))\b|"
    r",\s*(?:but|although)\s+|"
    r"\b(?:within\s+\d+|the\s+following\s+(?:day|week|month|year)|"
    r"in\s+(?:\d{4}|(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4})|for\s+\$[\d,.]+)",
    re.I,
)
_LEGAL_OR_CONSTITUTION_UNIT = re.compile(r"^(?:ARTICLE|AMENDMENT|PREAMBLE)(?:_|$)")
_SCIENTIFIC_UNIT = re.compile(
    r"^(?:ABSTRACT|INTRODUCTION|BACKGROUND|RESULTS?|DISCUSSION|METHODS?|"
    r"MATERIALS|CONCLUSIONS?|SUPPLEMENTARY)(?:_|$)"
)

_VERB_MAP = {
    "announced": "announced",
    "announce": "announces",
    "acquired": "acquired",
    "acquire": "acquires",
    "became": "became",
    "become": "becomes",
    "cause": "causes",
    "caused": "caused",
    "deduct": "deducts",
    "deducted": "deducted",
    "founded": "founded",
    "found": "founds",
    "hired": "hired",
    "hire": "hires",
    "joined": "joined",
    "join": "joins",
    "kept": "kept",
    "keep": "keeps",
    "moved": "moved",
    "move": "moves",
    "approved": "approved",
    "approve": "approves",
    "rejected": "rejected",
    "reject": "rejects",
    "sold": "sold",
    "sell": "sells",
    "provided": "provided",
    "provide": "provides",
    "returned": "returned",
    "return": "returns",
}
_KNOWN_VERBS = "|".join(sorted(_VERB_MAP, key=len, reverse=True))
_SIMPLE = re.compile(
    rf"^(?P<subject>.+?)\s+(?P<verb>{_KNOWN_VERBS}|"
    r"[A-Za-z][A-Za-z'’-]*(?:ed|ates|izes|ifies|ects|uces|ains|ires))\s+"
    r"(?P<object>.+)$",
    re.I,
)
_MODAL = re.compile(
    rf"^(?P<subject>.+?)\s+(?P<modal>{_MODALS})\s+"
    rf"(?P<negative>not\s+)?(?P<verb>{_KNOWN_VERBS}|[A-Za-z][A-Za-z'’-]*)\s+"
    r"(?P<object>.+)$",
    re.I,
)
_AUX_NEGATIVE = re.compile(
    rf"^(?P<subject>.+?)\s+(?:has|have|had|does|do|did)\s+not\s+"
    rf"(?P<verb>{_KNOWN_VERBS}|[A-Za-z][A-Za-z'’-]*)\s+(?P<object>.+)$",
    re.I,
)
_ENTITLED = re.compile(
    r"^(?P<subject>.+?)\s+(?:is|are|was|were)\s+entitled\s+to\s+"
    r"(?P<object>.+)$",
    re.I,
)
_SHARED_MODAL = re.compile(
    rf"^(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?"
    rf"(?P<verb>{_KNOWN_VERBS}|[A-Za-z][A-Za-z'’-]*)\s+(?P<object>.+)$",
    re.I,
)
_SHARED_AUX_NEGATIVE = re.compile(
    rf"^(?:has|have|had|does|do|did)\s+not\s+"
    rf"(?P<verb>{_KNOWN_VERBS}|[A-Za-z][A-Za-z'’-]*)\s+(?P<object>.+)$",
    re.I,
)
_SHARED_SIMPLE = re.compile(
    rf"^(?P<verb>{_KNOWN_VERBS})\s+(?P<object>.+)$",
    re.I,
)


@dataclass(slots=True)
class ProseState:
    """Document-local antecedents used only for unambiguous references."""

    last_subject: str | None = None
    last_person: str | None = None
    last_organization: str | None = None
    descriptions: dict[str, str] = field(default_factory=dict)

    def resolve_subject(self, value: str) -> str | None:
        surface = normalize_space(value).strip(" ,.;:")
        folded = surface.casefold()
        if folded in {"he", "she"}:
            return self.last_person
        if folded in {"it", "they"}:
            return self.last_subject
        if _DESCRIPTIVE_ORG.fullmatch(surface):
            return self.last_organization
        canonical = canonical_entity(surface)
        described = self.descriptions.get(canonical.casefold())
        if described:
            return described
        if (
            self.last_organization
            and len(canonical.split()) == 1
            and self.last_organization.casefold().startswith(canonical.casefold() + " ")
        ):
            return self.last_organization
        return canonical or None

    def observe(self, subject: str, object_: str) -> None:
        self.last_subject = subject
        subject_key = canonical_entity(subject).casefold()
        if subject_key:
            self.descriptions.setdefault(subject_key, subject)
        if _PERSON.fullmatch(subject) and not _ORG_SUFFIX.search(subject):
            self.last_person = subject
        if _ORG_SUFFIX.search(subject):
            self.last_organization = subject
        if self.last_organization is None and _ORG_SUFFIX.search(object_):
            self.last_organization = object_
            first = object_.split()[0].casefold()
            self.descriptions.setdefault(first, object_)


@dataclass(frozen=True, slots=True)
class _ParsedBranch:
    subject: str
    predicate: str
    object: str
    modality: str | None
    polarity: str
    condition: str | None


def _conditions(*values: str | None) -> str | None:
    parts: list[str] = []
    for value in values:
        if not value:
            continue
        for part in value.split("; "):
            part = normalize_space(part).strip(" ,.;")
            if part and part.casefold() not in {item.casefold() for item in parts}:
                parts.append(part)
    return "; ".join(parts) or None


def _detach_qualifiers(value: str) -> tuple[str, str | None]:
    """Separate event scope from the entity affected by the event."""
    text = normalize_space(value).strip(" .")
    qualifiers: list[tuple[int, str]] = []
    patterns = (
        r"\b(?:if|when|whenever|unless|provided\s+that)\b.+$",
        r"\bwithin\s+\d+(?:\.\d+)?\s+[^,;.]+$",
        r"\bthe\s+following\s+(?:day|week|month|year)\b.*$",
        r"\bfor\s+\$[\d,.]+(?:\s+(?:thousand|million|billion))?\b",
        r"\bin\s+(?:\d{4}|(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{4})\b",
        r"\bon\s+(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)(?:\s+\d{4})?\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            qualifiers.append((match.start(), normalize_space(match.group())))
    if not qualifiers:
        return text, None
    qualifiers.sort()
    start = qualifiers[0][0]
    object_ = text[:start].rstrip(" ,")
    condition = "; ".join(
        dict.fromkeys(item for position, item in qualifiers if position >= start)
    )
    return object_, condition or None


def _predicate(verb: str, object_: str) -> tuple[str, str]:
    word = verb.casefold().replace("’", "'")
    predicate = _VERB_MAP.get(word, word)
    if word in {"keep", "kept"} and re.search(r"\s+open$", object_, re.I):
        return "kept_open" if word == "kept" else "keeps_open", re.sub(
            r"\s+open$", "", object_, flags=re.I
        )
    return predicate, object_


def _clean_object(value: str) -> str:
    value = normalize_space(value).strip(" ,.;")
    value = re.sub(r"^(?:his|her|its|their)\s+", "", value, flags=re.I)
    return canonical_entity(value)


def _parse_branch(
    text: str,
    state: ProseState,
    *,
    shared_subject: str | None,
    inherited_condition: str | None,
) -> _ParsedBranch | None:
    branch = normalize_space(text).strip(" ,.;")
    match = _SHARED_MODAL.match(branch) if shared_subject else None
    polarity = "positive"
    modality: str | None = None
    if match:
        raw_subject = shared_subject
        modality = match.group("modal").casefold()
        polarity = "negative" if match.group("negative") else "positive"
    else:
        match = _SHARED_AUX_NEGATIVE.match(branch) if shared_subject else None
        if match:
            raw_subject = shared_subject
            polarity = "negative"
        else:
            match = _SHARED_SIMPLE.match(branch) if shared_subject else None
            if match:
                raw_subject = shared_subject
            else:
                entitled = _ENTITLED.match(branch)
                if entitled:
                    subject = state.resolve_subject(entitled.group("subject"))
                    object_, local_condition = _detach_qualifiers(entitled.group("object"))
                    if not subject or not object_:
                        return None
                    return _ParsedBranch(
                        subject, "entitled_to", _clean_object(object_), None,
                        "positive", _conditions(inherited_condition, local_condition),
                    )
                match = _AUX_NEGATIVE.match(branch)
                if match:
                    raw_subject = match.group("subject")
                    polarity = "negative"
                else:
                    match = _MODAL.match(branch)
                    if match:
                        raw_subject = match.group("subject")
                        modality = match.group("modal").casefold()
                        polarity = "negative" if match.group("negative") else "positive"
                    else:
                        match = _SIMPLE.match(branch)
                        if not match:
                            return None
                        raw_subject = match.group("subject")
    subject = state.resolve_subject(raw_subject)
    if not subject or _PRONOUN.fullmatch(subject):
        return None
    object_, local_condition = _detach_qualifiers(match.group("object"))
    predicate, object_ = _predicate(match.group("verb"), object_)
    object_ = _clean_object(object_)
    if not object_:
        return None
    return _ParsedBranch(
        subject, predicate, object_, modality, polarity,
        _conditions(inherited_condition, local_condition),
    )


def assemble_prose(
    text: str,
    *,
    context: str,
    sentence_index: int,
    start: int,
    end: int,
    source_unit: str | None,
    state: ProseState,
) -> list[RelationFrame]:
    """Assemble a complete qualified clause, or return no frames."""
    unit = (source_unit or "").upper()
    if (
        _LEGAL_OR_CONSTITUTION_UNIT.match(unit)
        or _SCIENTIFIC_UNIT.match(unit)
        or not _ACTIVATION.search(text)
    ):
        return []

    main = normalize_space(text)
    inherited_condition: str | None = None
    dependent = _LEADING_DEPENDENT.match(main)
    if dependent:
        inherited_condition = normalize_space(dependent.group("condition"))
        # A modal inside the leading branch usually means two coordinated
        # legal rules (for example, approval followed by a veto alternative),
        # rather than one condition attached to the later rule.
        if re.search(rf"\b(?:{_MODALS})\b", inherited_condition, re.I):
            return []
        main = dependent.group("main")

    branches = _BRANCH.split(main)
    parsed: list[_ParsedBranch] = []
    shared_subject: str | None = None
    for index, branch in enumerate(branches):
        if index and re.match(r"^(?:if|when|unless)\b", branch.strip(), re.I):
            return []
        item = _parse_branch(
            branch,
            state,
            shared_subject=shared_subject if index else None,
            inherited_condition=inherited_condition if index == 0 else None,
        )
        if item is None:
            return []
        parsed.append(item)
        shared_subject = item.subject

    frames: list[RelationFrame] = []
    for item in parsed:
        frames.append(RelationFrame(
            subject_options=(item.subject,),
            predicate_options=(item.predicate,),
            object_options=(item.object,),
            evidence=text,
            context=context,
            sentence_index=sentence_index,
            start=start,
            end=end,
            modality=item.modality,
            polarity=item.polarity,
            source_unit=source_unit,
            condition=item.condition,
            conditions=tuple(item.condition.split("; ")) if item.condition else (),
            origin="prose",
        ))
        state.observe(item.subject, item.object)
    return frames

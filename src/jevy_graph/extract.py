from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .models import CandidateTriple, RelationFrame
from .normalize import (
    canonical_entity,
    find_aliases,
    normalize_space,
    object_kind,
)


@dataclass(frozen=True, slots=True)
class RelationPattern:
    expression: re.Pattern[str]
    predicates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RelationHit:
    start: int
    end: int
    predicates: tuple[str, ...]
    modality: str | None = None
    polarity: str = "positive"
    priority: int = 0


@dataclass(frozen=True, slots=True)
class Clause:
    text: str
    context: str
    sentence_index: int
    start: int
    end: int
    continuation: bool = False


_MODALS = r"shall|may|must|can|could|will|would|should"
_STATIC_RELATIONS: tuple[RelationPattern, ...] = (
    RelationPattern(
        re.compile(r"\b(?:has|have|had)\s+to\b", re.I),
        ("required_to",),
    ),
    RelationPattern(
        re.compile(
            r"\b(?:is|are|was|were)\s+based\s+(?:solely\s+|entirely\s+)?on\b",
            re.I,
        ),
        ("based_on",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?be\s+"
            r"Commander\s+in\s+Chief\s+of\b",
            re.I,
        ),
        ("commander_in_chief_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be\s+)?vested\s+in\b",
            re.I,
        ),
        ("vested_in",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?consists?\s+of\b", re.I
        ),
        ("consists_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be)\s+composed\s+of\b",
            re.I,
        ),
        ("composed_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be)\s+"
            r"(?:directly\s+)?(?:located|based)\s+in\b",
            re.I,
        ),
        ("located_in", "based_in"),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?:{_MODALS})\s+)?(?:not\s+)?(?:is|are|was|were|be)\s+part\s+of\b",
            re.I,
        ),
        ("part_of",),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?have\s+"
            r"(?:(?:the\s+)?sole\s+)?power\s+to\b",
            re.I,
        ),
        ("authorized_to",),
    ),
    RelationPattern(
        re.compile(r"\bworks?\s+for\b", re.I),
        ("works_for", "employed_by"),
    ),
    RelationPattern(
        re.compile(r"\b(?:was|were)\s+founded\s+by\b", re.I),
        ("founded_by",),
    ),
    RelationPattern(
        re.compile(r"\b(?:was|were)\s+created\s+by\b", re.I),
        ("created_by",),
    ),
    RelationPattern(
        re.compile(r"\b(?:was|were)\s+acquired\s+by\b", re.I),
        ("acquired_by",),
    ),
    RelationPattern(
        re.compile(r"\b(?:acquires?|acquired|acquiring)\b", re.I),
        ("acquired", "purchased"),
    ),
    RelationPattern(
        re.compile(r"\b(?:activates?|activated|activating)\b", re.I),
        ("activates", "increases_activity_of"),
    ),
    RelationPattern(
        re.compile(r"\b(?:affects?|affected|affecting)\b", re.I),
        ("affects", "influences"),
    ),
    RelationPattern(
        re.compile(r"\b(?:causes?|caused|causing)\b", re.I),
        ("causes", "contributes_to"),
    ),
    RelationPattern(
        re.compile(r"\b(?:contains?|contained|containing)\b", re.I),
        ("contains", "includes"),
    ),
    RelationPattern(
        re.compile(r"\b(?:creates?|created|creating)\b", re.I),
        ("created", "produced"),
    ),
    RelationPattern(
        re.compile(r"\b(?:develops?|developed|developing)\b", re.I),
        ("developed", "created"),
    ),
    RelationPattern(
        re.compile(r"\b(?:employs?|employed|employing)\b", re.I),
        ("employs", "uses"),
    ),
    RelationPattern(
        re.compile(r"\b(?:founds?|founded|founding)\b", re.I),
        ("founded", "created"),
    ),
    RelationPattern(
        re.compile(
            rf"\b(?:(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?)?"
            r"(?:has|have|had)\b(?!\s+(?:been|become|becomes|becoming|[A-Za-z'-]+(?:ed|en))\b)",
            re.I,
        ),
        ("has", "possesses", "authorized_to"),
    ),
    RelationPattern(
        re.compile(r"\b(?:inhibits?|inhibited|inhibiting)\b", re.I),
        ("inhibits", "decreases_activity_of"),
    ),
    RelationPattern(
        re.compile(r"\b(?:knows?|knew)\b", re.I),
        ("knows", "aware_of"),
    ),
    RelationPattern(
        re.compile(r"\b(?:owns?|owned|owning)\b", re.I),
        ("owns", "possesses"),
    ),
    RelationPattern(
        re.compile(r"\b(?:produces?|produced|producing)\b", re.I),
        ("produces", "creates"),
    ),
    RelationPattern(
        re.compile(r"\b(?:provides?|provided|providing)\b", re.I),
        ("provides", "supplies"),
    ),
    RelationPattern(
        re.compile(r"\b(?:requires?|required|requiring)\b", re.I),
        ("requires", "depends_on"),
    ),
    RelationPattern(
        re.compile(r"\b(?:supports?|supported|supporting)\b", re.I),
        ("supports", "enables"),
    ),
    RelationPattern(
        re.compile(r"\b(?:uses?|used|using)\b", re.I),
        ("uses", "applies", "used_with", "used_for", "encoded_with"),
    ),
)

_PASSIVE = re.compile(
    rf"\b(?:(?P<modal>{_MODALS})\s+)?(?P<negative>not\s+)?"
    r"(?:is|are|was|were|be)\s+(?:also\s+)?"
    r"(?P<verb>vested|composed|chosen|elected|appointed|removed|divided|"
    r"determined|made|passed|held|admitted|prohibited|deprived|required|"
    r"provided|established|called|accused|convicted|attainted|questioned|"
    r"diminished|increased|denied|abridged|construed|taxed|vacated|entitled|"
    r"apportioned|bound|directed|obliged|presented|approved|disapproved|entered|"
    r"reconsidered|sent|published|suspended|assembled)"
    r"(?:\s+(?P<prep>in|by|of|to|from|into|upon|on|with|for|as))?\b",
    re.I,
)
_PERFECT_MODAL = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?have\s+"
    r"(?P<verb>[A-Za-z][A-Za-z'-]*(?:ed|en))"
    r"(?:\s+(?P<prep>in|by|of|to|from|into|upon|on|with|for|as))?\b",
    re.I,
)
_MODAL_ACTIVE = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?"
    r"(?:(?:then|also|thereupon|immediately|by\s+law)\s+){0,2}"
    r"(?P<verb>[A-Za-z][A-Za-z'-]*)"
    r"(?:\s+(?:only\s+)?(?P<prep>in|of|to|by|from|with|for|on|at))?\b",
    re.I,
)
_MODAL_COPULA_BARE = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?be\s+"
    r"(?=(?-i:[A-Z])[A-Za-z'-]*\b)",
    re.I,
)
_TYPE_RELATION = re.compile(r"\b(?:is|are|was|were)\s+(?:an?|the)\b", re.I)
_MODAL_TYPE = re.compile(
    rf"\b(?P<modal>{_MODALS})\s+(?P<negative>not\s+)?"
    r"(?:,\s*[^,]{1,60},\s*)?be\s+(?:an?|the)\b",
    re.I,
)
_GENERIC_ACTIVE = re.compile(
    r"\b(?P<verb>[A-Za-z][A-Za-z'-]*(?:ed|ing|ates|izes|ifies|ects|uces|"
    r"ains|ires))"
    r"(?:\s+(?P<prep>in|on|by|of|to|from|into|upon|with|for|as|around))?\b",
    re.I,
)
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’./+_-]*")
_CAPITALIZED = re.compile(
    r"\b[A-Z][A-Za-z0-9'’_-]*(?:\s+[A-Z][A-Za-z0-9'’_-]*){0,6}\b"
)
_LEADING = re.compile(
    r"^(?:however|therefore|then|also|instead|accordingly|according to [^,]+),?\s*",
    re.I,
)
_TRAILING_AUXILIARY = re.compile(
    rf"\s+(?:(?:do|does|did|{_MODALS}|has|have|had|is|are|was|were|be|been|being)"
    r"(?:\s+not|\s+n't)?|not)$",
    re.I,
)
_TRAILING_FUNCTION_WORD = re.compile(
    r"\s+(?:a|an|the|and|or|to|of|in|on|for|with|by|from)$", re.I
)
_LEADING_COMPLEMENT = re.compile(
    r"^(?:(?:in\s+)?conjunction\s+with|with|to|of|in|on|for|by|from|as)\s+",
    re.I,
)
_PRONOUN = re.compile(
    r"^(?:he|she|it|they|this|that|these|those|which|who)$", re.I
)
_BAD_ENTITY = re.compile(
    r"^(?:he|she|it|they|we|i|you|this|that|these|those|who|which|there)$",
    re.I,
)
_BAD_STANDALONE = re.compile(
    rf"^(?:a|an|the|and|or|to|of|in|on|for|with|by|from|{_MODALS}|"
    r"is|are|was|were|be|been|being|first|second|third|another|one|all|each|"
    r"previously|highly|different|usual|as|when|before|after|only|left|right)$",
    re.I,
)
_BAD_ENTITY_START = re.compile(
    rf"^(?:{_MODALS}|do|does|did|is|are|was|were|be|been|being|previously|"
    r"highly|usually|typically|when|before|after|as)\b|^(?:left|right)\s*\)",
    re.I,
)
_GENERIC_VERB_STOP = {
    "united",
    "states",
    "representatives",
    "years",
    "members",
    "powers",
    "rights",
    "amendments",
    "persons",
    "things",
    "proceedings",
    "buildings",
    "according",
    "including",
    "excluding",
    "following",
    "during",
    "being",
    "hundred",
}
_MODAL_VERB_STOP = {
    "after",
    "any",
    "at",
    "before",
    "by",
    "during",
    "for",
    "from",
    "hereafter",
    "if",
    "in",
    "nevertheless",
    "of",
    "on",
    "otherwise",
    "thereafter",
    "therein",
    "thereof",
    "thereupon",
    "to",
    "unless",
    "when",
    "where",
    "with",
}
_IRREGULAR_VERBS = {
    "has": "has",
    "have": "has",
    "had": "has",
    "be": "type",
    "chuse": "chooses",
    "choose": "chooses",
    "chosen": "chosen_by",
    "made": "makes",
    "make": "makes",
    "laid": "lays",
    "lay": "lays",
    "held": "holds",
    "hold": "holds",
    "met": "meets",
    "meet": "meets",
    "paid": "pays",
    "pay": "pays",
    "receive": "receives",
    "consist": "consists_of",
    "appoint": "appoints",
    "nominate": "nominates",
    "establish": "establishes",
    "ordain": "ordains",
    "direct": "directs",
    "declare": "declares",
    "provide": "provides",
    "borrow": "borrows",
    "regulate": "regulates",
    "coin": "coins",
    "punish": "punishes",
    "define": "defines",
    "exercise": "exercises",
    "issue": "issues",
    "fill": "fills",
    "sign": "signs",
    "vote": "votes",
    "return": "returns",
    "pass": "passes",
    "originate": "originates",
    "extend": "extends_to",
    "having": "has",
    "chusing": "chooses",
    "taking": "takes",
    "take": "takes",
    "acting": "acts",
    "voting": "votes",
    "holding": "holds",
    "implemented": "implements",
    "designed": "designs",
    "evaluated": "evaluates",
    "experimented": "experiments_with",
    "replaced": "replaces",
    "reduced": "reduces",
    "computed": "computes",
    "optimized": "optimizes",
    "generated": "generates",
    "depicted": "depicted_in",
    "applied": "applied_to",
    "centered": "centered_around",
    "averaged": "averaged",
    "compared": "compared_to",
    "trained": "trained",
    "described": "described_in",
    "represented": "represented_as",
    "running": "runs",
    "using": "uses",
    "replacing": "replaces",
    "improving": "improves",
    "involving": "involves",
    "setting": "sets",
    "encoding": "encodes",
    "making": "makes",
    "parsing": "parses",
    "embedding": "embeds",
    "computing": "computes",
    "beginning": "begins",
    "reducing": "reduces",
    "averaging": "averages",
    "relating": "relates_to",
    "consisting": "consists_of",
}
_ACTION_VERBS = {
    "appoint",
    "borrow",
    "call",
    "coin",
    "collect",
    "constitute",
    "declare",
    "define",
    "dispose",
    "establish",
    "exercise",
    "fix",
    "govern",
    "grant",
    "lay",
    "maintain",
    "make",
    "organize",
    "promote",
    "provide",
    "punish",
    "raise",
    "regulate",
    "support",
}


def clean_document(text: str) -> str:
    """Remove common PDF extraction noise while preserving paragraph boundaries."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", text)
    raw_lines = [normalize_space(line.replace("\f", "")) for line in text.splitlines()]
    counts = Counter(line.casefold() for line in raw_lines if line)
    lines: list[str] = []
    for line in raw_lines:
        repeated_header = (
            line
            and counts[line.casefold()] >= 3
            and (line.isupper() or "literal print" in line.casefold())
        )
        if re.fullmatch(r"\d{1,4}", line) or repeated_header:
            continue
        lines.append(line)

    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(normalize_space(" ".join(current)))
            current = []
    if current:
        paragraphs.append(normalize_space(" ".join(current)))
    return "\n".join(paragraphs)


def _clauses(text: str) -> list[Clause]:
    prepared = clean_document(text)
    clauses: list[Clause] = []
    sentence_index = 0
    for sentence_match in _SENTENCE.finditer(prepared):
        sentence = normalize_space(sentence_match.group())
        if not sentence:
            continue
        parts = list(re.finditer(r"(?:^|;|—)\s*([^;—]+)", sentence))
        for part_index, part in enumerate(parts):
            clause = normalize_space(part.group(1))
            if not clause:
                continue
            clauses.append(
                Clause(
                    text=clause,
                    context=sentence,
                    sentence_index=sentence_index,
                    start=sentence_match.start() + part.start(1),
                    end=sentence_match.start() + part.end(1),
                    continuation=part_index > 0,
                )
            )
        sentence_index += 1
    return clauses


def _modal_and_polarity(value: str) -> tuple[str | None, str]:
    modal_match = re.search(rf"\b({_MODALS})\b", value, re.I)
    negative = bool(re.search(r"\b(?:not|never|no)\b", value, re.I))
    return (
        modal_match.group(1).casefold() if modal_match else None,
        "negative" if negative else "positive",
    )


def _predicate_for(verb: str, prep: str | None = None) -> str:
    word = verb.casefold().replace("’", "'")
    predicate = _IRREGULAR_VERBS.get(word)
    if predicate is None:
        if word.endswith("ing"):
            predicate = word[:-3] or word
        else:
            predicate = word
    if word in {"consist", "consists"} and prep:
        predicate = f"consists_{prep.casefold()}"
        prep = None
    predicate = re.sub(r"[^a-z0-9]+", "_", predicate).strip("_")
    if prep and not predicate.endswith(f"_{prep.casefold()}"):
        predicate = f"{predicate}_{prep.casefold()}"
    return predicate


def _overlaps(hit: RelationHit, accepted: list[RelationHit]) -> bool:
    return any(hit.start < other.end and other.start < hit.end for other in accepted)


def _relation_hits(clause: str) -> list[RelationHit]:
    proposed: list[RelationHit] = []
    for pattern in _STATIC_RELATIONS:
        for match in pattern.expression.finditer(clause):
            modality, polarity = _modal_and_polarity(match.group())
            proposed.append(
                RelationHit(
                    match.start(),
                    match.end(),
                    pattern.predicates,
                    modality,
                    polarity,
                    4,
                )
            )
    for match in _PASSIVE.finditer(clause):
        predicate = _predicate_for(match.group("verb"), match.group("prep"))
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (predicate,),
                match.group("modal").casefold() if match.group("modal") else None,
                "negative" if match.group("negative") else "positive",
                3,
            )
        )
    for match in _PERFECT_MODAL.finditer(clause):
        if match.group("verb").casefold() == "been":
            continue
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (_predicate_for(match.group("verb"), match.group("prep")),),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                3,
            )
        )
    for match in _MODAL_TYPE.finditer(clause):
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                ("type",),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                3,
            )
        )
    for match in _MODAL_COPULA_BARE.finditer(clause):
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                ("type",),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                2,
            )
        )
    for match in _TYPE_RELATION.finditer(clause):
        proposed.append(
            RelationHit(
                match.start(), match.end(), ("type", "equivalent_to"), priority=2
            )
        )
    for match in _MODAL_ACTIVE.finditer(clause):
        verb = match.group("verb")
        if (
            len(verb) < 3
            or verb.casefold() == "be"
            or verb.casefold() in _MODAL_VERB_STOP
        ):
            continue
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (_predicate_for(verb, match.group("prep")),),
                match.group("modal").casefold(),
                "negative" if match.group("negative") else "positive",
                2,
            )
        )
    for match in _GENERIC_ACTIVE.finditer(clause):
        verb = match.group("verb")
        followed_by_relation = re.match(
            rf"\s+(?:(?:{_MODALS})\b|(?:is|are|was|were)\b)",
            clause[match.end() :],
            re.I,
        )
        inside_hyphenated_word = (
            (match.start() > 0 and clause[match.start() - 1] == "-")
            or (match.end() < len(clause) and clause[match.end()] == "-")
        )
        if (
            verb.casefold() in _GENERIC_VERB_STOP
            or followed_by_relation
            or inside_hyphenated_word
        ):
            continue
        proposed.append(
            RelationHit(
                match.start(),
                match.end(),
                (_predicate_for(verb, match.group("prep")),),
                priority=1,
            )
        )

    accepted: list[RelationHit] = []
    for hit in sorted(
        proposed,
        key=lambda item: (-item.priority, item.start, -(item.end - item.start)),
    ):
        if not _overlaps(hit, accepted):
            accepted.append(hit)
    ordered = sorted(accepted, key=lambda item: item.start)
    filtered: list[RelationHit] = []
    for hit in ordered:
        gap = clause[filtered[-1].end : hit.start] if filtered else ""
        if (
            hit.priority == 1
            and filtered
            and (filtered[-1].modality or filtered[-1].priority >= 4)
            and re.fullmatch(r"\s*(?:a|an|the)?\s*", gap, re.I)
        ):
            continue
        filtered.append(hit)
    return filtered


def _trim_left(value: str) -> str:
    value = _LEADING.sub("", normalize_space(value))
    value = re.split(r"[;:]", value)[-1]
    value = re.split(r"\b(?:and|but)\b", value, flags=re.I)[-1]
    value = _TRAILING_AUXILIARY.sub("", value)
    value = re.sub(r",?\s+(?:which|who)$", "", value, flags=re.I)
    return canonical_entity(value)


def _trim_right(value: str) -> str:
    value = normalize_space(value)
    value = re.split(
        r"[;:]|\b(?:but|because|although|while|when)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = re.split(r",\s*(?:which|who)\b", value, maxsplit=1, flags=re.I)[0]
    value = re.split(
        rf"\s+(?:who|which|that)\s+(?:{_MODALS}|has|have|is|are)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return canonical_entity(value)


def _valid_entity(value: str) -> bool:
    if not value or not canonical_entity(value) or _BAD_ENTITY.fullmatch(value):
        return False
    words = value.split()
    canonical_words = canonical_entity(value).split()
    return (
        len(words) <= 64
        and not (len(words) == 1 and _BAD_STANDALONE.fullmatch(value))
        and not (
            len(canonical_words) == 1
            and _BAD_STANDALONE.fullmatch(canonical_words[0])
        )
        and not _BAD_ENTITY.fullmatch(words[0])
        and not _BAD_ENTITY.fullmatch(words[-1])
        and not _BAD_ENTITY_START.match(value)
        and any(character.isalnum() for character in value)
    )


def _unique(values: list[str], limit: int = 64) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = normalize_space(value).strip(" \t\n\r.,;:!?()[]{}\"'“”‘’")
        key = canonical_entity(value).casefold()
        if not _valid_entity(value) or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) == limit:
            break
    return tuple(result)


def _tokens(value: str) -> list[str]:
    return _TOKEN.findall(value)


def _subject_options(
    value: str,
    aliases: dict[str, str],
    context_entities: tuple[str, ...],
) -> tuple[str, ...]:
    primary = _trim_left(value)
    values = [canonical_entity(primary, aliases)]
    segment = re.split(
        r"[,;:]|\b(?:and|but)\b", normalize_space(value), flags=re.I
    )[-1]
    tokens = _tokens(segment)
    values.extend(
        canonical_entity(match.group(), aliases)
        for match in _CAPITALIZED.finditer(value)
    )
    for width in range(min(14, len(tokens)), 0, -1):
        phrase = " ".join(tokens[-width:])
        values.extend((phrase, canonical_entity(phrase, aliases)))
        without_auxiliary = _TRAILING_AUXILIARY.sub("", phrase)
        values.extend(
            (without_auxiliary, canonical_entity(without_auxiliary, aliases))
        )
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            values.extend((phrase, canonical_entity(phrase, aliases)))
    if not primary or _PRONOUN.fullmatch(primary):
        values.extend(context_entities)
    return tuple(
        value
        for value in _unique(values)
        if not re.match(r"^\d+(?:\.\d+)?(?:\s+|$)", value)
    )


def _object_options(value: str, aliases: dict[str, str]) -> tuple[str, ...]:
    primary = _trim_right(value)
    values = [canonical_entity(primary, aliases)]
    complement = _LEADING_COMPLEMENT.sub("", primary)
    if complement != primary:
        values.extend((complement, canonical_entity(complement, aliases)))
    tokens = _tokens(value)
    for width in range(1, min(18, len(tokens)) + 1):
        phrase = " ".join(tokens[:width])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            values.extend((phrase, canonical_entity(phrase, aliases)))
        without_power = re.sub(
            r"^(?:the\s+)?power\s+to\s+", "", phrase, flags=re.I
        )
        if without_power != phrase:
            values.extend((without_power, canonical_entity(without_power, aliases)))
    for width in range(1, min(14, len(tokens)) + 1):
        phrase = " ".join(tokens[-width:])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            values.extend((phrase, canonical_entity(phrase, aliases)))
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            if not _TRAILING_FUNCTION_WORD.search(phrase):
                values.extend((phrase, canonical_entity(phrase, aliases)))
    return _unique(values)


def _context_entities(text: str) -> tuple[str, ...]:
    values = [
        canonical_entity(match.group()) for match in _CAPITALIZED.finditer(text)
    ]
    return _unique(list(reversed(values)), limit=24)


def _looks_clause_like(value: str) -> bool:
    words = {word.casefold() for word in _TOKEN.findall(value)}
    bare_verbs = set(_IRREGULAR_VERBS) - {"be", "has", "have", "had"}
    return bool(
        re.search(rf"\b(?:{_MODALS}|is|are|was|were|has|have|had)\b", value, re.I)
        or words.intersection(bare_verbs)
        or _PASSIVE.search(value)
    )


def _split_list(value: str) -> tuple[str, ...]:
    value = canonical_entity(value)
    if re.search(r"\b(?:but|unless|except|provided)\b", value, re.I):
        return (value,)
    if not re.search(r",|\band\b", value, re.I):
        return (value,)
    if "," not in value and re.search(
        r"\b(?:of|in|on|to|from|with|for|by)\b.*\band\b", value, re.I
    ):
        return (value,)
    parts = [
        canonical_entity(re.sub(r"^(?:and|or)\s+", "", part, flags=re.I))
        for part in re.split(r"\s*,\s*|\s+and\s+", value, flags=re.I)
        if canonical_entity(part)
    ]
    if any(_PRONOUN.fullmatch(part) for part in parts):
        return (value,)
    if (
        2 <= len(parts) <= 8
        and len(value.split()) <= 16
        and all(len(part.split()) <= 8 for part in parts)
        and not _looks_clause_like(value)
    ):
        return tuple(parts)
    return (value,)


def _subject_branches(value: str) -> tuple[str, ...]:
    primary = _trim_left(value)
    branches = _split_list(primary)
    return branches if len(branches) > 1 else (primary,)


def _object_branches(value: str, predicate: str) -> tuple[str, ...]:
    primary = _trim_right(value)
    suffix = predicate.rsplit("_", 1)[-1]
    if suffix in {"in", "of", "to", "by", "from", "with", "for", "on", "at"}:
        primary = re.sub(rf"^{suffix}\s+", "", primary, flags=re.I)
    if predicate == "authorized_to":
        action = re.match(
            r"^(?P<first>[A-Za-z'-]+)\s+and\s+(?P<second>[A-Za-z'-]+)\s+"
            r"(?P<objects>.+)$",
            primary,
            re.I,
        )
        if action:
            shared_objects = re.split(
                r",\s+to\s+", action.group("objects"), maxsplit=1, flags=re.I
            )[0]
            objects = _split_list(shared_objects)
            if len(objects) <= 8:
                return tuple(
                    f"{verb} {object_}"
                    for verb in (action.group("first"), action.group("second"))
                    for object_ in objects
                )
        verbs = "|".join(sorted(_ACTION_VERBS, key=len, reverse=True))
        matches = list(
            re.finditer(
                rf"(?:^|,\s*|\s+and\s+(?:to\s+)?)(?P<verb>{verbs})\b",
                primary,
                re.I,
            )
        )
        if len(matches) > 1:
            actions: list[str] = []
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(primary)
                phrase = normalize_space(f"{match.group('verb')} {primary[match.end():end]}")
                phrase = phrase.rstrip(" ,")
                if phrase:
                    actions.append(phrase)
            if actions:
                return tuple(actions)
    return _split_list(primary)


def extract_frames(text: str) -> list[RelationFrame]:
    """Build relation frames from clauses using open modal and verb discovery."""
    prepared = clean_document(text)
    aliases = find_aliases(prepared)
    clauses = _clauses(text)
    frames: list[RelationFrame] = []
    seen: set[tuple[str, str, str, int, str, str]] = set()
    recent_subjects: tuple[str, ...] = ()
    carried_authority = False
    authority_subjects: tuple[str, ...] = ()

    for clause in clauses:
        if re.match(r"^(?:Section|Article|Amendment)\b", clause.text, re.I):
            carried_authority = False
            authority_subjects = ()
        hits = _relation_hits(clause.text)
        continuation = re.match(r"^(?:and\s+)?to\s+", clause.text, re.I)
        if carried_authority and continuation:
            hits = [
                RelationHit(
                    continuation.start(),
                    continuation.end(),
                    ("authorized_to",),
                    "shall",
                    "positive",
                    5,
                )
            ]
        if not hits:
            continue

        context_entities = recent_subjects + _context_entities(clause.context)
        prior_hit_end = 0
        local_antecedents = recent_subjects
        clause_subjects: tuple[str, ...] = ()
        for hit_index, hit in enumerate(hits):
            subject_text = clause.text[prior_hit_end : hit.start]
            if clause_subjects and re.match(
                r"^\s*,?\s*and\s+(?:by|with|after|before|in|on|at|from)\b",
                subject_text,
                re.I,
            ):
                raw_subjects = clause_subjects
            else:
                raw_subjects = _subject_branches(subject_text)
            if not any(_valid_entity(value) for value in raw_subjects):
                fallback = (
                    authority_subjects
                    if hit.priority == 5
                    else clause_subjects or local_antecedents or recent_subjects
                )
                raw_subjects = fallback[:1]
            next_start = (
                hits[hit_index + 1].start
                if hit_index + 1 < len(hits)
                else len(clause.text)
            )
            object_text = clause.text[hit.end : next_start]
            if hit_index + 1 < len(hits) and re.match(r"^\s*,", object_text):
                shared_object = clause.text[hits[hit_index + 1].end :]
                if normalize_space(shared_object):
                    object_text = shared_object
            if not normalize_space(object_text):
                prior_hit_end = hit.end
                continue

            subjects = tuple(value for value in raw_subjects if _valid_entity(value))
            if not subjects:
                subjects = recent_subjects[:1]
            primary_predicate = hit.predicates[0]
            if subjects and not clause_subjects:
                clause_subjects = subjects[:1]
            object_branches = _object_branches(object_text, primary_predicate)[:16]
            for subject_branch in subjects[:8]:
                subject_options = _subject_options(
                    subject_branch, aliases, context_entities
                )
                if not subject_options:
                    continue
                for object_branch in object_branches:
                    object_options = _object_options(object_branch, aliases)
                    if not object_options:
                        continue
                    polarity = hit.polarity
                    if re.match(r"^(?:no|not|never)\b", subject_branch, re.I) or re.match(
                        r"^(?:no|not|never)\b", object_branch, re.I
                    ) or re.search(
                        r"\b(?:not|never)\s*$", subject_text, re.I
                    ) or re.match(
                        r"^\s*(?:no|not|never)\b", object_text, re.I
                    ) or re.match(
                        r"^\s*no\b", subject_text, re.I
                    ):
                        polarity = "negative"
                    key = (
                        canonical_entity(subject_options[0]).casefold(),
                        "/".join(hit.predicates),
                        canonical_entity(object_options[0]).casefold(),
                        clause.sentence_index,
                        hit.modality or "",
                        polarity,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    frames.append(
                        RelationFrame(
                            subject_options=subject_options,
                            predicate_options=hit.predicates,
                            object_options=object_options,
                            evidence=clause.text,
                            context=clause.context,
                            sentence_index=clause.sentence_index,
                            start=clause.start,
                            end=clause.end,
                            modality=hit.modality,
                            polarity=polarity,
                        )
                    )
            if primary_predicate == "authorized_to":
                carried_authority = True
                if subjects:
                    authority_subjects = subjects[:1]
            if object_branches:
                local_antecedents = tuple(
                    value for value in object_branches if _valid_entity(value)
                )[:4]
            prior_hit_end = hit.end

            first_subjects = _subject_options(subject_text, aliases, context_entities)
            if first_subjects and not _PRONOUN.fullmatch(first_subjects[0]):
                recent_subjects = first_subjects[:4]
    return frames


def extract_candidates(text: str) -> list[CandidateTriple]:
    """Return the deterministic first choice from each relation frame."""
    return [
        CandidateTriple(
            subject=canonical_entity(frame.subject_options[0]),
            predicate=frame.predicate_options[0],
            object=canonical_entity(frame.object_options[0]),
            evidence=frame.evidence,
            sentence_index=frame.sentence_index,
            start=frame.start,
            end=frame.end,
            modality=frame.modality,
            polarity=frame.polarity,
            object_kind=object_kind(frame.object_options[0]),
        )
        for frame in extract_frames(text)
    ]

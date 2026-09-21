from __future__ import annotations

import re
from dataclasses import dataclass

from .models import CandidateTriple, RelationFrame
from .normalize import canonical_label, find_aliases, normalize_space


@dataclass(frozen=True, slots=True)
class RelationPattern:
    expression: re.Pattern[str]
    predicates: tuple[str, ...]


_RELATIONS: tuple[RelationPattern, ...] = (
    RelationPattern(
        re.compile(r"\b(?:is|are|was|were)\s+(?:directly\s+)?(?:located|based)\s+in\b", re.I),
        ("located_in", "based_in"),
    ),
    RelationPattern(re.compile(r"\b(?:is|are|was|were)\s+part\s+of\b", re.I), ("part_of",)),
    RelationPattern(re.compile(r"\b(?:works?|worked)\s+for\b", re.I), ("works_for", "employed_by")),
    RelationPattern(re.compile(r"\b(?:was|were)\s+founded\s+by\b", re.I), ("founded_by",)),
    RelationPattern(re.compile(r"\b(?:was|were)\s+created\s+by\b", re.I), ("created_by",)),
    RelationPattern(re.compile(r"\b(?:was|were)\s+acquired\s+by\b", re.I), ("acquired_by",)),
    RelationPattern(re.compile(r"\b(?:acquires?|acquired|acquiring)\b", re.I), ("acquired", "purchased")),
    RelationPattern(re.compile(r"\b(?:activates?|activated|activating)\b", re.I), ("activates", "increases_activity_of")),
    RelationPattern(re.compile(r"\b(?:affects?|affected|affecting)\b", re.I), ("affects", "influences")),
    RelationPattern(re.compile(r"\b(?:causes?|caused|causing)\b", re.I), ("causes", "contributes_to")),
    RelationPattern(re.compile(r"\b(?:contains?|contained|containing)\b", re.I), ("contains", "includes")),
    RelationPattern(re.compile(r"\b(?:creates?|created|creating)\b", re.I), ("created", "produced")),
    RelationPattern(re.compile(r"\b(?:develops?|developed|developing)\b", re.I), ("developed", "created")),
    RelationPattern(re.compile(r"\b(?:employs?|employed|employing)\b", re.I), ("employs", "uses")),
    RelationPattern(re.compile(r"\b(?:founds?|founded|founding)\b", re.I), ("founded", "created")),
    RelationPattern(
        re.compile(
            r"\b(?:has|have|had)\b(?!\s+(?:been|become|becomes|becoming)\b)",
            re.I,
        ),
        ("has", "possesses", "authorized_to"),
    ),
    RelationPattern(re.compile(r"\b(?:inhibits?|inhibited|inhibiting)\b", re.I), ("inhibits", "decreases_activity_of")),
    RelationPattern(re.compile(r"\b(?:knows?|knew)\b", re.I), ("knows", "aware_of")),
    RelationPattern(re.compile(r"\b(?:owns?|owned|owning)\b", re.I), ("owns", "possesses")),
    RelationPattern(re.compile(r"\b(?:produces?|produced|producing)\b", re.I), ("produces", "creates")),
    RelationPattern(re.compile(r"\b(?:provides?|provided|providing)\b", re.I), ("provides", "supplies")),
    RelationPattern(re.compile(r"\b(?:requires?|required|requiring)\b", re.I), ("requires", "depends_on")),
    RelationPattern(re.compile(r"\b(?:supports?|supported|supporting)\b", re.I), ("supports", "enables")),
    RelationPattern(
        re.compile(r"\b(?:uses?|used|using)\b", re.I),
        ("uses", "applies", "used_with"),
    ),
)

_TYPE_RELATION = re.compile(r"\b(?:is|are|was|were)\s+(?:an?|the)\b", re.I)
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’./+_-]*")
_LEADING = re.compile(
    r"^(?:however|therefore|then|also|instead|according to [^,]+),\s*", re.I
)
_BAD_ENTITY = re.compile(
    r"^(?:he|she|it|they|we|i|you|this|that|these|those|who|which|there)$", re.I
)
_BAD_STANDALONE = re.compile(
    r"^(?:a|an|the|and|or|to|of|in|on|for|with|by|from|shall|will|would|"
    r"can|could|may|might|must|should|is|are|was|were|be|been|being)$",
    re.I,
)
_TRAILING_AUXILIARY = re.compile(
    r"\s+(?:(?:do|does|did|can|could|will|would|shall|may|might|must|should|has|have|had|is|are|was|were|be|been|being)"
    r"(?:\s+not|\s+n't)?|not)$",
    re.I,
)
_TRAILING_FUNCTION_WORD = re.compile(
    r"\s+(?:a|an|the|and|or|to|of|in|on|for|with|by|from)$", re.I
)
_LEADING_COMPLEMENT = re.compile(
    r"^(?:(?:in\s+)?conjunction\s+with|with|to|of|in|on|for|by|from)\s+",
    re.I,
)
_PRONOUN = re.compile(r"^(?:he|she|it|they|this|that|these|those)$", re.I)
_CAPITALIZED = re.compile(
    r"\b[A-Z][A-Za-z0-9'’_-]*(?:\s+[A-Z][A-Za-z0-9'’_-]*){0,5}\b"
)


def _prepare_text(text: str) -> str:
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return normalize_space(text)


def _trim_left(value: str) -> str:
    value = _LEADING.sub("", normalize_space(value))
    value = re.split(r"[;:]", value)[-1]
    value = re.split(r"\b(?:and|but)\b", value, flags=re.I)[-1]
    value = _TRAILING_AUXILIARY.sub("", value)
    return canonical_label(value)


def _trim_right(value: str) -> str:
    value = normalize_space(value)
    value = re.split(
        r"[,;:]|\b(?:and|but|because|although|while|when)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return canonical_label(value)


def _valid_entity(value: str) -> bool:
    if not value or _BAD_ENTITY.fullmatch(value):
        return False
    words = value.split()
    return (
        len(words) <= 14
        and not (len(words) == 1 and _BAD_STANDALONE.fullmatch(value))
        and not _BAD_ENTITY.fullmatch(words[0])
        and not _BAD_ENTITY.fullmatch(words[-1])
        and any(character.isalnum() for character in value)
    )


def _unique(values: list[str], limit: int = 48) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = normalize_space(value).strip(" \t\n\r.,;:!?()[]{}\"'“”‘’")
        key = value.casefold()
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
    value: str, aliases: dict[str, str], context_entities: tuple[str, ...]
) -> tuple[str, ...]:
    primary = _trim_left(value)
    values = [canonical_label(primary, aliases)]
    segment = re.split(r"[,;:]|\b(?:and|but)\b", normalize_space(value), flags=re.I)[-1]
    tokens = _tokens(segment)
    values.extend(
        canonical_label(match.group(), aliases)
        for match in _CAPITALIZED.finditer(segment)
    )
    for width in range(min(14, len(tokens)), 0, -1):
        phrase = " ".join(tokens[-width:])
        values.extend((phrase, canonical_label(phrase, aliases)))
        without_auxiliary = _TRAILING_AUXILIARY.sub("", phrase)
        values.extend((without_auxiliary, canonical_label(without_auxiliary, aliases)))

    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(0, len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            values.extend((phrase, canonical_label(phrase, aliases)))

    if _PRONOUN.fullmatch(primary):
        values.extend(reversed(context_entities))
    return _unique(values)


def _object_options(value: str, aliases: dict[str, str]) -> tuple[str, ...]:
    primary = _trim_right(value)
    values = [canonical_label(primary, aliases)]
    complement = _LEADING_COMPLEMENT.sub("", primary)
    if complement != primary:
        values.extend((complement, canonical_label(complement, aliases)))
    tokens = _tokens(value)
    for width in range(1, min(16, len(tokens)) + 1):
        phrase = " ".join(tokens[:width])
        if _TRAILING_FUNCTION_WORD.search(phrase):
            continue
        values.extend((phrase, canonical_label(phrase, aliases)))
        without_power = re.sub(r"^(?:the\s+)?power\s+to\s+", "", phrase, flags=re.I)
        if without_power != phrase:
            values.extend((without_power, canonical_label(without_power, aliases)))
    for width in range(1, min(14, len(tokens)) + 1):
        phrase = " ".join(tokens[-width:])
        if not _TRAILING_FUNCTION_WORD.search(phrase):
            values.extend((phrase, canonical_label(phrase, aliases)))
    for width in range(1, min(8, len(tokens)) + 1):
        for offset in range(0, len(tokens) - width + 1):
            phrase = " ".join(tokens[offset : offset + width])
            if _TRAILING_FUNCTION_WORD.search(phrase):
                continue
            values.extend((phrase, canonical_label(phrase, aliases)))
    return _unique(values)


def _context_entities(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _CAPITALIZED.finditer(text):
        value = canonical_label(match.group())
        if value.casefold() not in {"the", "a", "an"} and len(value) > 1:
            values.append(value)
    return _unique(values, limit=16)


def _sentences(text: str) -> list[tuple[str, int, int]]:
    prepared = _prepare_text(text)
    return [
        (normalize_space(match.group()), match.start(), match.end())
        for match in _SENTENCE.finditer(prepared)
        if normalize_space(match.group())
    ]


def extract_frames(text: str) -> list[RelationFrame]:
    """Build a deterministic lattice of possible relation components."""
    aliases = find_aliases(_prepare_text(text))
    sentences = _sentences(text)
    frames: list[RelationFrame] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], int]] = set()

    for sentence_index, (sentence, start, end) in enumerate(sentences):
        prior = " ".join(item[0] for item in sentences[max(0, sentence_index - 2) : sentence_index])
        context = normalize_space(f"{prior} {sentence}")
        entities = _context_entities(prior)
        matches: list[tuple[int, int, tuple[str, ...]]] = []
        for relation in _RELATIONS:
            matches.extend(
                (match.start(), match.end(), relation.predicates)
                for match in relation.expression.finditer(sentence)
            )
        matches.extend(
            (match.start(), match.end(), ("type", "equivalent_to"))
            for match in _TYPE_RELATION.finditer(sentence)
        )
        matches.sort()

        for relation_start, relation_end, predicates in matches:
            subjects = _subject_options(sentence[:relation_start], aliases, entities)
            objects = _object_options(sentence[relation_end:], aliases)
            if not subjects or not objects:
                continue
            key = (subjects, predicates, objects, sentence_index)
            if key in seen:
                continue
            seen.add(key)
            frames.append(
                RelationFrame(
                    subject_options=subjects,
                    predicate_options=predicates,
                    object_options=objects,
                    evidence=sentence,
                    context=context,
                    sentence_index=sentence_index,
                    start=start,
                    end=end,
                )
            )
    return frames


def extract_candidates(text: str) -> list[CandidateTriple]:
    """Return the deterministic first choice from each relation frame."""
    return [
        CandidateTriple(
            subject=frame.subject_options[0],
            predicate=frame.predicate_options[0],
            object=frame.object_options[0],
            evidence=frame.evidence,
            sentence_index=frame.sentence_index,
            start=frame.start,
            end=frame.end,
        )
        for frame in extract_frames(text)
    ]

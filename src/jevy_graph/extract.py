from __future__ import annotations

import re
from dataclasses import dataclass

from .models import CandidateTriple
from .normalize import canonical_label, find_aliases, normalize_space


@dataclass(frozen=True, slots=True)
class RelationPattern:
    expression: re.Pattern[str]
    predicate: str


_RELATIONS: tuple[RelationPattern, ...] = (
    RelationPattern(re.compile(r"\b(?:is|are|was|were)\s+(?:directly\s+)?(?:located|based)\s+in\b", re.I), "located_in"),
    RelationPattern(re.compile(r"\b(?:is|are|was|were)\s+part\s+of\b", re.I), "part_of"),
    RelationPattern(re.compile(r"\b(?:works?|worked)\s+for\b", re.I), "works_for"),
    RelationPattern(re.compile(r"\b(?:was|were)\s+founded\s+by\b", re.I), "founded_by"),
    RelationPattern(re.compile(r"\b(?:was|were)\s+created\s+by\b", re.I), "created_by"),
    RelationPattern(re.compile(r"\b(?:was|were)\s+acquired\s+by\b", re.I), "acquired_by"),
    RelationPattern(re.compile(r"\b(?:acquires?|acquired|acquiring)\b", re.I), "acquired"),
    RelationPattern(re.compile(r"\b(?:activates?|activated|activating)\b", re.I), "activates"),
    RelationPattern(re.compile(r"\b(?:affects?|affected|affecting)\b", re.I), "affects"),
    RelationPattern(re.compile(r"\b(?:causes?|caused|causing)\b", re.I), "causes"),
    RelationPattern(re.compile(r"\b(?:contains?|contained|containing)\b", re.I), "contains"),
    RelationPattern(re.compile(r"\b(?:creates?|created|creating)\b", re.I), "created"),
    RelationPattern(re.compile(r"\b(?:develops?|developed|developing)\b", re.I), "developed"),
    RelationPattern(re.compile(r"\b(?:employs?|employed|employing)\b", re.I), "employs"),
    RelationPattern(re.compile(r"\b(?:founds?|founded|founding)\b", re.I), "founded"),
    RelationPattern(re.compile(r"\b(?:has|have|had)\b", re.I), "has"),
    RelationPattern(re.compile(r"\b(?:inhibits?|inhibited|inhibiting)\b", re.I), "inhibits"),
    RelationPattern(re.compile(r"\b(?:knows?|knew|known)\b", re.I), "knows"),
    RelationPattern(re.compile(r"\b(?:owns?|owned|owning)\b", re.I), "owns"),
    RelationPattern(re.compile(r"\b(?:produces?|produced|producing)\b", re.I), "produces"),
    RelationPattern(re.compile(r"\b(?:provides?|provided|providing)\b", re.I), "provides"),
    RelationPattern(re.compile(r"\b(?:requires?|required|requiring)\b", re.I), "requires"),
    RelationPattern(re.compile(r"\b(?:supports?|supported|supporting)\b", re.I), "supports"),
    RelationPattern(re.compile(r"\b(?:uses?|used|using)\b", re.I), "uses"),
)

_TYPE_RELATION = re.compile(r"\b(?:is|are|was|were)\s+(?:an?|the)\b", re.I)
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|(?=\n)|$)")
_LEADING = re.compile(
    r"^(?:however|therefore|then|also|instead|according to [^,]+),\s*", re.I
)
_BAD_ENTITY = re.compile(
    r"^(?:he|she|it|they|we|i|you|this|that|these|those|who|which|there)$", re.I
)


def _trim_left(value: str) -> str:
    value = _LEADING.sub("", normalize_space(value))
    value = re.split(r"[;:]", value)[-1]
    value = re.split(r"\b(?:and|but)\b", value, flags=re.I)[-1]
    return canonical_label(value)


def _trim_right(value: str) -> str:
    value = normalize_space(value)
    value = re.split(r"[,;:]|\b(?:and|but|because|although|while|when)\b", value, maxsplit=1, flags=re.I)[0]
    return canonical_label(value)


def _valid_entity(value: str) -> bool:
    if not value or _BAD_ENTITY.fullmatch(value):
        return False
    words = value.split()
    return len(words) <= 10 and any(character.isalnum() for character in value)


def _sentences(text: str) -> list[tuple[str, int, int]]:
    return [
        (normalize_space(match.group()), match.start(), match.end())
        for match in _SENTENCE.finditer(text)
        if normalize_space(match.group())
    ]


def extract_candidates(text: str) -> list[CandidateTriple]:
    """Extract conservative subject/relation/object candidates from plain text."""
    aliases = find_aliases(text)
    candidates: list[CandidateTriple] = []
    seen: set[tuple[str, str, str, int]] = set()

    for sentence_index, (sentence, start, end) in enumerate(_sentences(text)):
        matches: list[tuple[int, int, str]] = []
        for relation in _RELATIONS:
            matches.extend(
                (match.start(), match.end(), relation.predicate)
                for match in relation.expression.finditer(sentence)
            )
        matches.extend(
            (match.start(), match.end(), "type") for match in _TYPE_RELATION.finditer(sentence)
        )
        matches.sort()

        for relation_start, relation_end, predicate in matches:
            subject = canonical_label(_trim_left(sentence[:relation_start]), aliases)
            object_ = canonical_label(_trim_right(sentence[relation_end:]), aliases)
            if not (_valid_entity(subject) and _valid_entity(object_)):
                continue
            key = (subject.casefold(), predicate, object_.casefold(), sentence_index)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                CandidateTriple(
                    subject=subject,
                    predicate=predicate,
                    object=object_,
                    evidence=sentence,
                    sentence_index=sentence_index,
                    start=start,
                    end=end,
                )
            )
    return candidates


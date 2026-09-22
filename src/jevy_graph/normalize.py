from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"\s+")
_ACRONYM = re.compile(
    r"\b([A-Z][A-Za-z0-9'-]*(?:\s+[A-Za-z][A-Za-z0-9'-]*){1,7})"
    r"\s*\(([A-Z][A-Z0-9-]{1,11})\)"
)
_LEADING_QUANTIFIER = re.compile(
    r"^(?:each|every|any|all|either|neither|such|no)\s+", re.IGNORECASE
)
_LEADING_ARTICLE = re.compile(r"^(?:a|an|the)\s+", re.IGNORECASE)
_LEADING_REFERENCE = re.compile(r"^(?:thereof|hereof)\s+", re.IGNORECASE)
_INTEGER = re.compile(r"[+-]?\d[\d,]*")
_DECIMAL = re.compile(r"[+-]?(?:\d[\d,]*\.\d+|\.\d+)")
_PERCENT = re.compile(r"[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*%")
_DOUBLE = re.compile(
    r"[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)[eE][+-]?\d+"
)
_NODE_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’./+_-]*")
_BARE_HEADING = re.compile(
    r"^(?:sections?|articles?|chapters?|parts?|appendices|appendix)"
    r"(?:[\s._-]*(?:\d+|[IVXLC]+))?$",
    re.IGNORECASE,
)
MAX_NODE_WORDS = 14
MAX_NODE_CHARACTERS = 160


def normalize_space(value: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def find_aliases(text: str) -> dict[str, str]:
    """Return explicit long-form/acronym aliases declared by the document."""
    aliases: dict[str, str] = {}
    for match in _ACRONYM.finditer(text):
        long_form = normalize_space(match.group(1))
        acronym = match.group(2)
        initials = "".join(word[0] for word in long_form.split() if word[0].isalnum())
        if initials.casefold() == acronym.replace("-", "").casefold():
            aliases[acronym.casefold()] = long_form
    return aliases


def canonical_label(value: str, aliases: dict[str, str] | None = None) -> str:
    value = normalize_space(value).strip(" \t\n\r.,;:!?\"'“”‘’•")
    if (
        len(value) >= 2
        and (value[0], value[-1]) in {("(", ")"), ("[", "]"), ("{", "}")}
        and value[1:-1].count(value[0]) == value[1:-1].count(value[-1])
    ):
        value = value[1:-1].strip()
    value = _LEADING_ARTICLE.sub("", value)
    if aliases and value.casefold() in aliases:
        return aliases[value.casefold()]
    return value


def canonical_entity(value: str, aliases: dict[str, str] | None = None) -> str:
    """Normalize harmless surface variation without inventing an entity link."""
    value = canonical_label(value, aliases)
    value = _LEADING_QUANTIFIER.sub("", value)
    value = _LEADING_REFERENCE.sub("", value)
    return normalize_space(value)


def graphable_node(value: str) -> bool:
    """Return whether a value is compact enough to be an RDF graph node."""
    value = canonical_entity(value)
    words = _NODE_WORD.findall(value)
    return bool(
        value
        and words
        and not _BARE_HEADING.fullmatch(value)
        and len(words) <= MAX_NODE_WORDS
        and len(value) <= MAX_NODE_CHARACTERS
    )


def object_kind(value: str) -> str:
    """Classify values that are safe to encode as RDF literals."""
    value = normalize_space(value)
    if _INTEGER.fullmatch(value):
        return "integer"
    if _DECIMAL.fullmatch(value):
        return "decimal"
    if _PERCENT.fullmatch(value):
        return "percent"
    if _DOUBLE.fullmatch(value):
        return "double"
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'", "“", "”"}
    ):
        return "string"
    return "entity"

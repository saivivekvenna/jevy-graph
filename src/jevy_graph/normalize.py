from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"\s+")
_ACRONYM = re.compile(
    r"\b([A-Z][A-Za-z0-9'-]*(?:\s+[A-Za-z][A-Za-z0-9'-]*){1,7})"
    r"\s*\(([A-Z][A-Z0-9-]{1,11})\)"
)


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
    value = normalize_space(value).strip(" \t\n\r.,;:!?()[]{}\"'“”‘’")
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.IGNORECASE)
    if aliases and value.casefold() in aliases:
        return aliases[value.casefold()]
    return value


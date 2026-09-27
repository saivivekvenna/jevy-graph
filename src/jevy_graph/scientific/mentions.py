from __future__ import annotations

import re

from .model import Mention, SourceSpan


def clean_text(value: str) -> str:
    value = re.sub(
        r"\s*\(\s*(?:Supplementary\s+)?(?:Figures?|Fig\.?|Table)\s+[^)]*\)",
        "",
        value,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", value).strip(" ,.;")


def normalized_mention(
    raw: str, normalized: str, *, kind: str = "entity", source: str
) -> Mention:
    start = source.casefold().find(raw.casefold())
    if start < 0:
        start = 0
    span = SourceSpan(start, start + len(raw), raw)
    normalized = clean_text(normalized)
    head = normalized.split()[-1] if normalized else ""
    return Mention(span, head, kind, normalized, (span,))


def normalize_intervention(value: str) -> str:
    value = clean_text(value)
    patterns = (
        (r"(?:the\s+)?knockdown\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "knockdown"),
        (r"knocking\s+down\s+(?:the\s+expression\s+of\s+)?(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "knockdown"),
        (r"(?:the\s+)?downregulation\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)(?:\s+expression)?", "downregulation"),
        (r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)[- ]deplet(?:ed|ion)(?:\s+group)?", "depletion"),
        (r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+silencing", "silencing"),
        (r"(?:the\s+)?overexpression\s+of\s+(?P<entity>[A-Za-z][A-Za-z0-9-]*)", "overexpression"),
        (r"(?P<entity>[A-Za-z][A-Za-z0-9-]*)\s+overexpression(?:\s+group)?", "overexpression"),
    )
    for pattern, operation in patterns:
        found = re.fullmatch(pattern, value, re.I)
        if found:
            return f"{found.group('entity')} {operation}"
    return value


def split_coordination(value: str) -> tuple[str, ...]:
    value = clean_text(value)
    value = re.sub(r"(?<=[A-Za-z0-9])and\s+(?=[A-Za-z])", " and ", value)
    return tuple(
        item.strip(" ,.;")
        for item in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", value)
        if item.strip(" ,.;")
    )


def measurements(value: str) -> tuple[str, ...]:
    found = []
    for pattern in (
        r"\b\d+(?:\.\d+)?\s*(?:times|fold)\b[^,.;]{0,30}",
        r"\bP\s*[<=>≤≥]\s*\d+(?:\.\d+)?",
        r"\b\d+(?:\.\d+)?%",
    ):
        for match in re.finditer(pattern, value, re.I):
            item = clean_text(match.group(0))
            if item not in found:
                found.append(item)
    return tuple(found)

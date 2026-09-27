from __future__ import annotations

import re


_PURPOSE = re.compile(
    r"^(?:(?:To\s+)?|We\s+)(?:independently\s+)?(?:investigate|investigated|explore|explored|determine|determined|assess|assessed|examine|examined|validate|validated|"
    r"further\s+detect)\b",
    re.I,
)
_PROCEDURE = re.compile(
    r"^(?:(?:Significant\s+)?[^,.;]{0,50}\banalysis\b[^.;]{0,100}\bwas\s+performed\b|"
    r"(?:We|The\s+(?:heatmap|box\s+plot|interaction\s+profile|"
    r"clinicopathological\s+associations)|Photos?\b|Table\b).{0,80}\b"
    r"(?:conducted|performed|employed|used|collected|constructed|displayed|provided|"
    r"shown|represents?|was\s+used|were\s+used)\b)",
    re.I,
)
_REPORTING = re.compile(
    r"^(?:Taken\s+together,?\s*)?(?:In\s+conclusion,?\s*)?"
    r"(?:We|Our|The|These|Collectively,?\s+these|The\s+above)\s+"
    r"(?:results?|findings?|data|analysis|observations?)\s+"
    r"(?:showed|show|revealed|indicated|indicate|demonstrated|confirmed|"
    r"confirm|suggested|suggest|implied|support|found|observed)\b",
    re.I,
)


def is_heading(text: str) -> bool:
    value = text.strip()
    if value.casefold() == "results":
        return True
    if re.search(r"[.!?]$", value) or len(value.split()) > 18:
        return False
    if re.match(r"^(?:We|The\s+results|These\s+results|To\s+)", value, re.I):
        return False
    return bool(re.search(
        r"\b(?:is|are|promotes?|suppresses?|accelerates?|inhibits?|"
        r"linked|analysis\s+of)\b",
        value,
        re.I,
    ))


def classify_clause(text: str) -> str:
    if is_heading(text):
        return "heading"
    if _PURPOSE.match(text):
        return "purpose"
    if _REPORTING.match(text):
        return "interpretation"
    if re.match(
        r"^(?:We\s+conducted\s+[^.;]+?\s+to\s+(?:develop|train|fit|measure)|"
        r"Additional\s+performance\s+characteristics\s+are\s+shown\b|"
        r"After\s+training\s+[^.;]+?,\s+[^.;]+?\s+(?:was|were)\s+"
        r"(?:fixed|applied)\b|We\s+incorporated\s+both\b|"
        r"Notably,?\s+no\s+[^.;]+?\s+were\s+used\s+to\s+train\b)",
        text,
        re.I,
    ):
        return "procedure"
    if _PROCEDURE.match(text):
        # Procedure wrappers may still contain relative-clause findings. The
        # compiler runs construction handlers and emits only the embedded fact.
        return (
            "mixed"
            if re.search(
                r"\b(?:showed|revealed|indicated|demonstrated|confirmed)\s+that\b",
                text,
                re.I,
            )
            else "procedure"
        )
    return "finding"

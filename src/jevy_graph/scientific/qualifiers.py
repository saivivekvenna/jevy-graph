from __future__ import annotations

import re


def modality(text: str, *, reporting: str | None = None) -> str:
    value = text.casefold()
    for marker in ("might", "may", "could", "can", "likely", "potential"):
        if re.search(rf"\b{marker}\b", value):
            return marker
    if reporting and reporting.casefold() in {"suggested", "suggest", "implied"}:
        return "suggested"
    if re.search(r"\bpredicted\b", value):
        return "predicted"
    return "asserted"

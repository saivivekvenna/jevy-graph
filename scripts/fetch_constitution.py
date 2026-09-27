"""Freeze the National Archives Constitution transcripts for long-document audits."""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SOURCES = {
    "articles": "https://www.archives.gov/founding-docs/constitution-transcript",
    "bill_of_rights": "https://www.archives.gov/founding-docs/bill-of-rights-transcript",
    "later_amendments": "https://www.archives.gov/founding-docs/amendments-11-27",
}


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain(fragment: str) -> str:
    parser = Text()
    parser.feed(fragment)
    return re.sub(r"\s+", " ", html.unescape("".join(parser.parts))).strip()


def blocks(page: str, start: int, end: int, *, heading: str) -> list[str]:
    result = []
    for match in re.finditer(r"<(h2|h3|p)\b([^>]*)>(.*?)</\1>", page[start:end], re.I | re.S):
        tag, attrs = match.group(1).lower(), match.group(2)
        if re.search(r'class=["\'][^"\']*smaller', attrs, re.I):
            continue
        value = plain(match.group(3))
        if not value or value.startswith(("Back to ", "Amendments 11-27", "Note:", "*Superseded")):
            continue
        if tag == heading or (tag == "h3" and heading == "h2"):
            result.append(value)
        elif tag == "p":
            result.append(value)
    return result


def fetch() -> tuple[str, dict[str, object]]:
    pages = {
        name: urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
        for name, url in SOURCES.items()
    }
    articles = pages["articles"]
    a_start = articles.index('<p><span class="larger"><strong>We the People')
    a_end = articles.index("<p>Attest William Jackson", a_start)
    rights = pages["bill_of_rights"]
    r_start = rights.index("<h3>Amendment I</h3>")
    r_end = rights.index("<p><a class=", rights.index("<h3>Amendment X</h3>", r_start))
    later = pages["later_amendments"]
    l_start = later.index("AMENDMENT XI</h3>")
    l_start = later.rfind("<h3", 0, l_start)
    l_end = later.index("<p><a class=", later.index("AMENDMENT XXVII</h2>", l_start))
    parts = [
        *blocks(articles, a_start, a_end, heading="h2"),
        *blocks(rights, r_start, r_end, heading="h3"),
        *blocks(later, l_start, l_end, heading="h2"),
    ]
    text = "\n\n".join(parts) + "\n"
    metadata = {
        "sources": SOURCES,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "bytes": len(text.encode()),
        "review_status": "source_frozen_claims_unreviewed",
    }
    return text, metadata


if __name__ == "__main__":
    text, metadata = fetch()
    root = Path("benchmarks/corpus")
    root.mkdir(parents=True, exist_ok=True)
    (root / "constitution.txt").write_text(text, encoding="utf-8")
    (root / "constitution-source.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))

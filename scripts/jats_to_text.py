"""Convert a full JATS article to the text used for a graph benchmark.

Includes the title, abstract, body, and figure/table captions in document order.
References and publisher metadata are excluded because they are not article claims.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree as ET


def normalized_text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def article_text(xml: bytes) -> str:
    root = ET.fromstring(xml)
    title = root.find("./front/article-meta/title-group/article-title")
    body = root.find("body")
    if title is None or body is None:
        raise ValueError("JATS article needs a title and body")
    blocks = [normalized_text(title)]

    abstract = root.find("./front/article-meta/abstract")
    if abstract is not None:
        blocks.append("Abstract")
        for element in abstract.iter():
            if element.tag in {"title", "p"}:
                value = normalized_text(element)
                if value:
                    blocks.append(value)

    parents = {child: parent for parent in body.iter() for child in parent}

    def inside(element: ET.Element, tag: str) -> bool:
        while element in parents:
            element = parents[element]
            if element.tag == tag:
                return True
        return False

    for element in body.iter():
        if element.tag == "title" and parents.get(element, body).tag == "sec":
            value = normalized_text(element)
            if value:
                blocks.append(value)
        elif element.tag == "p" and not inside(element, "caption"):
            value = normalized_text(element)
            if value:
                blocks.append(value)
        elif element.tag == "caption":
            # JATS titles and panel descriptions are sibling elements. Joining
            # their raw text turns "CRC" + "(A)" into the false entity "CRC(A)".
            caption_parts = [
                normalized_text(child)
                for child in element
                if child.tag in {"title", "p"}
            ]
            blocks.extend(value for value in caption_parts if value)
        elif element.tag == "tr":
            cells = [normalized_text(cell) for cell in element if cell.tag in {"th", "td"}]
            if cells:
                blocks.append(" | ".join(cells))
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(article_text(args.xml.read_bytes()), encoding="utf-8")


if __name__ == "__main__":
    main()

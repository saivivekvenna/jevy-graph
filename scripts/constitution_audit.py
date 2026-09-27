"""Inventory every official Constitution provision and its extraction coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from jevy_graph.extract import _source_markers, clean_document, extract_frames
from jevy_graph.jev import _triple_options


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("benchmarks/corpus/constitution.txt"))
    parser.add_argument("--output", type=Path, default=Path("out/constitution-audit.json"))
    parser.add_argument("--benchmark", type=Path, help="live benchmark JSON for section decisions")
    parser.add_argument("--fixtures", type=Path, default=Path("benchmarks/fixtures"),
                        help="directory containing reviewed section annotations")
    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8")
    prepared = clean_document(text)
    markers = _source_markers(prepared)
    frames = extract_frames(text)
    counts = Counter(frame.source_unit for frame in frames)
    candidates = Counter(
        frame.source_unit for frame in frames if _triple_options(frame)
    )
    by_unit: dict[str | None, list[dict[str, object]]] = {}
    for frame in frames:
        by_unit.setdefault(frame.source_unit, []).append({
            "evidence": frame.evidence,
            "origin": frame.origin,
            "option_count": len(_triple_options(frame)),
            "first_options": _triple_options(frame)[:3],
        })
    benchmark = json.loads(args.benchmark.read_text()) if args.benchmark else None
    if benchmark:
        if benchmark["metrics"]["document_sha256"] != hashlib.sha256(text.encode()).hexdigest():
            parser.error("benchmark document hash differs from the audit input")
        frame_hash = hashlib.sha256()
        option_hash = hashlib.sha256()
        for frame in frames:
            frame_hash.update(json.dumps(asdict(frame), sort_keys=True).encode())
            option_hash.update(json.dumps(_triple_options(frame)).encode())
        if benchmark["metrics"].get("frame_sha256") != frame_hash.hexdigest() or benchmark["metrics"].get("option_sha256") != option_hash.hexdigest():
            parser.error("benchmark frames or candidates differ from the current extractor")
    accepted = Counter(
        item["candidate"]["source_unit"] for item in benchmark["claims"]
    ) if benchmark else Counter()
    filtered = Counter(
        item["claim"]["candidate"]["source_unit"]
        for item in benchmark["rejected_claims"]
    ) if benchmark else Counter()
    abstained = Counter(
        item["frame"]["source_unit"] for item in benchmark.get("selection_rejections", [])
    ) if benchmark else Counter()
    reviewed: dict[str, list[dict[str, object]]] = {}
    for fixture_path in sorted(args.fixtures.glob("*.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if (fixture.get("domain") != "legal"
                or fixture.get("annotation_scope") != "exhaustive"
                or fixture.get("review_status") not in {"codex_reviewed", "human_reviewed"}):
            continue
        labels = {item.get("source_unit") for item in fixture.get("gold", [])}
        if len(labels) == 1 and None not in labels:
            reviewed.setdefault(next(iter(labels)), []).append({
                "fixture_id": fixture["id"],
                "fixture_text": fixture.get("text", ""),
                "gold_claims": len(fixture["gold"]),
                "review_status": fixture["review_status"],
            })

    def normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    units = []
    for index, (start, label) in enumerate(markers):
        start = max(0, start)
        end = markers[index + 1][0] if index + 1 < len(markers) else len(prepared)
        words = len(prepared[start:end].split())
        source_text = prepared[start:end].strip()
        complete_fixtures = [
            item for item in reviewed.get(label, [])
            if normalized(source_text) in normalized(str(item["fixture_text"]))
        ]
        review = complete_fixtures[0] if complete_fixtures else None
        units.append({
            "source_unit": label,
            "normalized_start": start,
            "normalized_end": end,
            "text_words": words,
            "source_text": source_text,
            "frames": counts[label],
            "frames_with_candidates": candidates[label],
            "proposals": by_unit.get(label, []),
            "accepted": accepted[label] if benchmark else None,
            "final_filtered": filtered[label] if benchmark else None,
            "jev_abstained": abstained[label] if benchmark else None,
            "gold_claims": review["gold_claims"] if review else None,
            "review_fixture": review["fixture_id"] if review else None,
            "review_status": review["review_status"] if review else (
                "unreviewed" if words >= 8 else "heading_only"
            ),
        })
    report = {
        "source": "https://www.archives.gov/founding-docs/constitution-transcript",
        "articles": len({label.split("_SECTION_")[0] for _, label in markers if label.startswith("ARTICLE_")}),
        "amendments": len({label.split("_SECTION_")[0] for _, label in markers if label.startswith("AMENDMENT_")}),
        "units": units,
        "unreviewed_units": sum(unit["review_status"] == "unreviewed" for unit in units),
        "reviewed_units": sum(unit["review_status"] in {"codex_reviewed", "human_reviewed"} for unit in units),
        "zero_frame_units": [unit["source_unit"] for unit in units if unit["review_status"] == "unreviewed" and not unit["frames"]],
        "benchmark": str(args.benchmark) if args.benchmark else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "units"}, indent=2))


if __name__ == "__main__":
    main()

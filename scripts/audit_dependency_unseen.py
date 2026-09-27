"""Run the frozen unseen scientific parser suite without paid model calls."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from jevy_graph.extract import extract_frames
from jevy_graph.scientific import DependencyScientificCompiler


ROOT = Path(__file__).resolve().parents[1]
GOLD = (
    ROOT
    / "benchmarks/audits/dependency-unseen-five-paper-frozen-gold-2026-09-27.json"
)
OUTPUT = (
    ROOT
    / "benchmarks/audits/dependency-unseen-five-paper-output-2026-09-27.json"
)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value: str | None) -> str:
    return re.sub(
        r"\s+",
        " ",
        (value or "").casefold().replace("“", "").replace("”", ""),
    ).strip()


def scientific_frames(items: list) -> list[dict]:
    return [
        asdict(frame)
        for frame in items
        if frame.origin in {"event", "semantic"}
    ]


def main() -> None:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    cold_parser = DependencyScientificCompiler(grammar=False)
    parser = DependencyScientificCompiler(nlp=cold_parser.nlp)
    rows = []

    for document in gold["documents"]:
        source = ROOT / document["source"]
        if file_hash(source) != document["source_sha256"]:
            raise RuntimeError(f"Frozen source changed: {source}")
        text = source.read_text(encoding="utf-8")

        started = time.perf_counter()
        baseline = extract_frames(text)
        baseline_seconds = time.perf_counter() - started

        cold_trace: list[dict] = []
        started = time.perf_counter()
        cold = extract_frames(
            text,
            scientific_trace=cold_trace,
            scientific_dependency_compiler=cold_parser,
        )
        cold_seconds = time.perf_counter() - started

        parser_trace: list[dict] = []
        claims = []
        started = time.perf_counter()
        parsed = extract_frames(
            text,
            scientific_trace=parser_trace,
            scientific_dependency_compiler=parser,
            scientific_claims=claims,
        )
        parser_seconds = time.perf_counter() - started

        claim_rows = [asdict(claim) for claim in claims]
        gold_keys = {
            (
                normalized(item["subject"]),
                normalized(item["predicate"]),
                normalized(item["object"]),
            )
            for item in document["gold"]
        }
        claim_keys = {
            (
                normalized(item["subject"]),
                normalized(item["relation"]),
                normalized(item["object"]),
            )
            for item in claim_rows
        }
        rows.append(
            {
                "pmcid": document["pmcid"],
                "split": document["split"],
                "gold": len(document["gold"]),
                "baseline_seconds": round(baseline_seconds, 4),
                "cold_parser_seconds": round(cold_seconds, 4),
                "parser_seconds": round(parser_seconds, 4),
                "baseline_frames": scientific_frames(baseline),
                "cold_parser_frames": scientific_frames(cold),
                "parser_frames": scientific_frames(parsed),
                "cold_scientific_trace": cold_trace,
                "parser_claims": claim_rows,
                "raw_exact_gold_matches": len(gold_keys & claim_keys),
                "scientific_trace": parser_trace,
            }
        )

    report = {
        "id": "dependency-unseen-five-paper-output-2026-09-27",
        "gold": str(GOLD.relative_to(ROOT)),
        "gold_sha256": file_hash(GOLD),
        "local_model": "en_core_sci_sm-0.5.4",
        "paid_model_calls": 0,
        "rows": rows,
    }
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "documents": len(rows),
                "gold": sum(row["gold"] for row in rows),
                "baseline_frames": sum(len(row["baseline_frames"]) for row in rows),
                "cold_parser_frames": sum(
                    len(row["cold_parser_frames"]) for row in rows
                ),
                "parser_frames": sum(len(row["parser_frames"]) for row in rows),
                "structured_claims": sum(
                    len(row["parser_claims"]) for row in rows
                ),
                "raw_exact_gold_matches": sum(
                    row["raw_exact_gold_matches"] for row in rows
                ),
                "baseline_seconds": round(
                    sum(row["baseline_seconds"] for row in rows), 3
                ),
                "cold_parser_seconds": round(
                    sum(row["cold_parser_seconds"] for row in rows), 3
                ),
                "parser_seconds": round(
                    sum(row["parser_seconds"] for row in rows), 3
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Run the claim-quality suite. Jev calls occur only with --live."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from jevy_graph.config import load_dotenv
from jevy_graph.demo_server import extract_upload
from jevy_graph.evaluation import (
    constitution_review_coverage, quality_summary, release_gate, score_fixture,
)
from jevy_graph.extract import candidates_from_frames, extract_frames
from jevy_graph.jev import JevClient, _triple_options
from jevy_graph.models import VerifiedTriple


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=Path("benchmarks/fixtures"))
    parser.add_argument("--test-manifest", type=Path,
                        default=Path("benchmarks/test-manifest.json"),
                        help="hash-locked inventory of held-out fixtures")
    parser.add_argument("--output", type=Path, default=Path("out/quality-report.json"))
    parser.add_argument("--live", action="store_true", help="make paid Jev calls")
    parser.add_argument("--allow-reject", action="store_true", help="experiment with Jev none-of-these selection")
    parser.add_argument("--no-compact-choices", action="store_false", dest="compact_choices",
                        help="compare against full Jev choice criteria")
    parser.add_argument("--id", action="append", help="run only this fixture ID; repeatable")
    args = parser.parse_args()
    if args.allow_reject and not args.live:
        parser.error("--allow-reject requires --live")
    if not args.compact_choices and not args.live:
        parser.error("--no-compact-choices requires --live")
    fixtures = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(args.fixtures.glob("*.json"))
    ]
    fixtures = [
        (path, fixture) for path, fixture in fixtures
        if fixture.get("id")
        and ("text" in fixture or "source_file" in fixture)
        and not fixture.get("superseded_by")
    ]
    manifest_bytes = args.test_manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("fixtures"), dict):
        raise SystemExit("Invalid held-out test manifest")
    frozen = manifest["fixtures"]
    current: dict[str, str] = {}
    for path, fixture in fixtures:
        if fixture.get("split") != "test":
            continue
        fixture_id = fixture["id"]
        if fixture_id in current:
            raise SystemExit(f"Duplicate held-out fixture ID: {fixture_id}")
        if (fixture.get("review_status") not in {"codex_reviewed", "human_reviewed"}
                or fixture.get("annotation_scope") != "exhaustive"):
            raise SystemExit(f"Held-out fixture lacks exhaustive review: {fixture_id}")
        current[fixture_id] = hashlib.sha256(path.read_bytes()).hexdigest()
    if current != frozen:
        missing = sorted(frozen.keys() - current.keys())
        new = sorted(current.keys() - frozen.keys())
        changed = sorted(key for key in frozen.keys() & current.keys()
                         if frozen[key] != current[key])
        raise SystemExit(
            f"Held-out fixture manifest mismatch: missing={missing}, new={new}, "
            f"changed={changed}. Review changes before updating the manifest."
        )
    constitution_coverage = constitution_review_coverage(
        Path("benchmarks/corpus/constitution.txt").read_text(encoding="utf-8"),
        [fixture for _, fixture in fixtures],
    )
    if args.id:
        fixtures = [(path, fixture) for path, fixture in fixtures if fixture["id"] in args.id]
    if not fixtures:
        raise SystemExit("No matching fixtures found")
    if args.live:
        load_dotenv()
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            raise SystemExit("TYPESAFE_API_KEY is required for --live")
    reports = []
    for path, fixture in fixtures:
        started = time.perf_counter()
        if source_file := fixture.get("source_file"):
            source = (path.parent / source_file).resolve()
            text = extract_upload(source.read_bytes(), source.name)
        else:
            text = fixture["text"]
        converted = time.perf_counter()
        frames = extract_frames(text)
        extracted = time.perf_counter()
        instruction = fixture.get("instruction", "")
        if args.live:
            client = JevClient(api_key, allow_reject=args.allow_reject,
                               compact=args.compact_choices)
            intent = client.interpret_instruction(instruction) if instruction else None
            after_intent = asdict(client.usage)
            candidates = client.resolve(frames)
            after_selection = asdict(client.usage)
            selected = time.perf_counter()
            verified = client.verify(candidates, instruction=instruction)
            usage = asdict(client.usage)
            for metric in ("requests", "request_bytes", "input_tokens", "output_tokens"):
                usage[f"intent_{metric}"] = after_intent[metric]
                usage[f"selection_{metric}"] = after_selection[metric] - after_intent[metric]
                usage[f"verification_{metric}"] = usage[metric] - after_selection[metric]
            group_by = intent.group_by if intent else "none"
            selection_rejections = [
                {"reason": "jev_none_of_these", "frame": asdict(frame),
                 "options": _triple_options(frame)}
                for frame in client.selection_rejections
            ]
        else:
            candidates = candidates_from_frames(frames)
            selected = time.perf_counter()
            verified = [VerifiedTriple(candidate, 1.0, 1.0) for candidate in candidates]
            usage = {}
            group_by = "unscored"
            selection_rejections = []
        finished = time.perf_counter()
        report = score_fixture(
            fixture, converted_text=text, frames=frames, candidates=candidates,
            verified=verified, usage=usage,
            timing={
                "conversion_seconds": round(converted - started, 4),
                "extraction_seconds": round(extracted - converted, 4),
                "selection_seconds": round(selected - extracted, 4),
                "verification_seconds": round(finished - selected, 4),
                "total_seconds": round(finished - started, 4),
            },
        )
        report["group_by"] = group_by
        report["fixture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        report["converted_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        report["selection_rejections"] = selection_rejections
        report["mode"] = "live" if args.live else "offline_candidate_probe"
        report["allow_reject"] = args.allow_reject
        report["compact_choices"] = args.compact_choices
        if not args.live:
            report["release_eligible"] = False
            report["metrics"]["precision"] = None
            report["metrics"]["recall"] = None
            report["metrics"]["scope_leaks"] = None
            report["metrics"]["unsupported_critical"] = None
            for loss in report["losses"]:
                if loss["stage"] not in {"source_conversion", "frame_generation", "candidate_generation"}:
                    loss["stage"] = "not_scored_offline"
            report["metrics"]["loss_stages"] = dict(Counter(
                loss["stage"] for loss in report["losses"]
            ))
            early_losses = sum(
                loss["stage"] in {"source_conversion", "frame_generation", "candidate_generation"}
                for loss in report["losses"]
            )
            expected = report["metrics"]["gold_in_scope"]
            report["metrics"]["candidate_recall_probe"] = (
                (expected - early_losses) / expected if expected else None
            )
        reports.append(report)
    result = {"mode": "live" if args.live else "offline_candidate_probe",
              "test_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "allow_reject": args.allow_reject,
              "gate": release_gate(reports, constitution_coverage=constitution_coverage),
              "summary": quality_summary(reports), "reports": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "mode": result["mode"], "gate": result["gate"],
        "summary": result["summary"],
        "fixtures": [
            {"id": report["fixture_id"], **report["metrics"]}
            for report in reports
        ],
    }, indent=2))


if __name__ == "__main__":
    main()

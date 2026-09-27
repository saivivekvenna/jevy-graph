"""Measure a fresh upload; --live explicitly enables paid Jev requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from jevy_graph.compiler import rejection_reason, select
from jevy_graph.config import load_dotenv
from jevy_graph.demo_server import extract_upload
from jevy_graph.extract import extract_frames
from jevy_graph.jev import JevClient, JevError, _triple_options


class MeasuredClient(JevClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_seconds = []

    def _post(self, payload):
        started = time.perf_counter()
        try:
            return super()._post(payload)
        finally:
            with self._stats_lock:
                self.request_seconds.append(time.perf_counter() - started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--compact", action="store_true", default=True)
    parser.add_argument("--no-compact", action="store_false", dest="compact")
    parser.add_argument("--allow-reject", action="store_true", help="experiment with Jev none-of-these selection")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instruction", default="", help="optional focused graph instruction")
    parser.add_argument(
        "--scientific-parser", action="store_true",
        help="use the optional local scispaCy dependency compiler",
    )
    parser.add_argument("--scientific-parser-model", default="en_core_sci_sm")
    args = parser.parse_args()
    if args.instruction and not args.live:
        parser.error("--instruction requires --live")
    started = time.perf_counter()
    text = extract_upload(args.input.read_bytes(), args.input.name)
    converted = time.perf_counter()
    scientific_trace = []
    dependency_compiler = None
    if args.scientific_parser:
        from jevy_graph.scientific import DependencyScientificCompiler
        dependency_compiler = DependencyScientificCompiler(args.scientific_parser_model)
    frames = extract_frames(
        text, scientific_trace=scientific_trace,
        scientific_dependency_compiler=dependency_compiler,
    )
    extracted = time.perf_counter()
    total_frames = len(frames)
    if args.sample and args.sample < len(frames):
        frames = [frames[i * len(frames) // args.sample] for i in range(args.sample)]

    verified = []
    usage = {}
    error = None
    group_by = "none"
    selection_rejections = []
    if args.live:
        load_dotenv()
        client = MeasuredClient(
            os.environ["TYPESAFE_API_KEY"],
            choice_batch_size=args.batch_size,
            verification_batch_size=48,
            max_workers=args.workers,
            compact=args.compact,
            allow_reject=args.allow_reject,
        )
        try:
            if args.instruction:
                group_by = client.interpret_instruction(args.instruction).group_by
            if args.reference:
                verified = client.verify(client.resolve(frames), instruction=args.instruction)
            else:
                for batch in client.iter_score_batches(frames, instruction=args.instruction):
                    verified.extend(batch)
        except (JevError, RuntimeError) as caught:
            error = str(caught)
        usage = {
            **asdict(client.usage),
            "rate_limit_detail": client.rate_limit_detail,
            "request_mean_seconds": round(sum(client.request_seconds) / max(1, len(client.request_seconds)), 3),
            "request_max_seconds": round(max(client.request_seconds, default=0), 3),
        }
        selection_rejections = [
            {"reason": "jev_none_of_these", "frame": asdict(frame),
             "options": _triple_options(frame)}
            for frame in client.selection_rejections
        ]
    processed = time.perf_counter()
    accepted = select(verified)
    rejected = [
        {"claim": asdict(item), "reason": rejection_reason(item)}
        for item in verified if rejection_reason(item)
    ]
    assembled = time.perf_counter()
    # Compute fingerprints after timing so audit work is excluded from the upload.
    frame_hash = hashlib.sha256()
    option_hash = hashlib.sha256()
    for frame in frames:
        frame_hash.update(json.dumps(asdict(frame), sort_keys=True).encode())
        option_hash.update(json.dumps(_triple_options(frame)).encode())
    metrics = {
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "frames": total_frames,
        "evaluated_frames": len(frames),
        "resolved": len(verified),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "candidate_options": sum(len(_triple_options(frame)) for frame in frames),
        "frames_without_options": sum(not _triple_options(frame) for frame in frames),
        "selection_abstentions": len(selection_rejections),
        "allow_reject": args.allow_reject,
        "group_by": group_by,
        "instruction": args.instruction,
        "frame_sha256": frame_hash.hexdigest(),
        "option_sha256": option_hash.hexdigest(),
        "scientific_compiler": {
            "dependency_parser": args.scientific_parser,
            "dependency_model": (
                args.scientific_parser_model if args.scientific_parser else None
            ),
            "clauses": len(scientific_trace),
            "hypotheses": sum(len(item["hypotheses"]) for item in scientific_trace),
            "candidate_generation_misses": sum(
                any(
                    trace["stage"] == "candidate_generation"
                    and trace["decision"] == "miss"
                    for trace in item["trace"]
                )
                for item in scientific_trace
            ),
            "constructions": dict(Counter(
                hypothesis["construction"]
                for item in scientific_trace
                for hypothesis in item["hypotheses"]
            )),
        },
        "pdf_or_text_seconds": round(converted - started, 3),
        "extraction_seconds": round(extracted - converted, 3),
        "jev_and_candidates_seconds": round(processed - extracted, 3),
        "compute_seconds": round(processed - started, 3),
        "filter_seconds": round(assembled - processed, 3),
        "workers": args.workers,
        "batch_size": args.batch_size,
        "error": error,
        **usage,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "metrics": metrics,
        "claims": [asdict(item) for item in accepted],
        "rejected_claims": rejected,
        "selection_rejections": selection_rejections,
        "scientific_trace": scientific_trace,
    }, indent=2))
    print(json.dumps(metrics, indent=2))
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

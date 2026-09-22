"""Measure a fresh upload; --live explicitly enables paid Jev requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from jevy_graph.compiler import select
from jevy_graph.config import load_dotenv
from jevy_graph.demo_server import extract_upload
from jevy_graph.extract import extract_frames
from jevy_graph.jev import JevClient, _triple_options


class MeasuredClient(JevClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0
        self.request_seconds = []

    def _post(self, payload):
        started = time.perf_counter()
        result = super()._post(payload)
        with self._stats_lock:
            self.requests += 1
            self.input_tokens += result.get("usage", {}).get("input_tokens", 0)
            self.output_tokens += result.get("usage", {}).get("output_tokens", 0)
            self.request_seconds.append(time.perf_counter() - started)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    text = extract_upload(args.input.read_bytes(), args.input.name)
    converted = time.perf_counter()
    frames = extract_frames(text)
    extracted = time.perf_counter()
    total_frames = len(frames)
    if args.sample and args.sample < len(frames):
        frames = [frames[i * len(frames) // args.sample] for i in range(args.sample)]

    verified = []
    usage = {}
    if args.live:
        load_dotenv()
        client = MeasuredClient(
            os.environ["TYPESAFE_API_KEY"],
            choice_batch_size=args.batch_size,
            verification_batch_size=48,
            max_workers=args.workers,
        )
        if args.reference:
            verified = client.verify(client.resolve(frames))
        else:
            verified = [v for batch in client.iter_score_batches(frames) for v in batch]
        usage = {
            "requests": client.requests,
            "input_tokens": client.input_tokens,
            "output_tokens": client.output_tokens,
            "retries": client.usage.retries,
            "request_mean_seconds": round(sum(client.request_seconds) / max(1, client.requests), 3),
            "request_max_seconds": round(max(client.request_seconds, default=0), 3),
        }
    processed = time.perf_counter()
    accepted = select(verified)
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
        "frame_sha256": frame_hash.hexdigest(),
        "option_sha256": option_hash.hexdigest(),
        "pdf_or_text_seconds": round(converted - started, 3),
        "extraction_seconds": round(extracted - converted, 3),
        "jev_and_candidates_seconds": round(processed - extracted, 3),
        "compute_seconds": round(processed - started, 3),
        "filter_seconds": round(assembled - processed, 3),
        "workers": args.workers,
        "batch_size": args.batch_size,
        **usage,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "metrics": metrics,
        "claims": [asdict(item) for item in accepted],
    }, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

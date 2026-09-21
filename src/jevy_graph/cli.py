from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .extract import extract_candidates, extract_frames
from .jev import JevClient, JevError
from .models import VerifiedTriple
from .rdf import render_turtle


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jevy-graph",
        description="Compile UTF-8 text into source-grounded RDF/Turtle.",
    )
    parser.add_argument("input", nargs="?", default="-", help="text file, or - for stdin")
    parser.add_argument("-o", "--output", help="output Turtle path; defaults to stdout")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.65,
        help="minimum exact-triple support probability (default: 0.65)",
    )
    parser.add_argument(
        "--entity-threshold",
        type=float,
        default=0.40,
        help="minimum RDF node-label quality probability (default: 0.40)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip Jev and emit all deterministic candidates",
    )
    return parser


def _read_text(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 0 <= args.threshold <= 1:
        raise SystemExit("--threshold must be between 0 and 1")
    if not 0 <= args.entity_threshold <= 1:
        raise SystemExit("--entity-threshold must be between 0 and 1")

    text = _read_text(args.input)
    frames = extract_frames(text)
    if args.no_verify:
        candidates = extract_candidates(text)
        verified = [VerifiedTriple(candidate, 1.0, 1.0) for candidate in candidates]
    else:
        _load_dotenv()
        api_key = os.environ.get("TYPESAFE_API_KEY", "")
        if not api_key:
            raise SystemExit("TYPESAFE_API_KEY is missing; set it in the environment or .env")
        try:
            verified = JevClient(api_key).score(frames)
            candidates = [item.candidate for item in verified]
        except JevError as error:
            raise SystemExit(str(error)) from error

    accepted = [
        item
        for item in verified
        if item.support >= args.threshold
        and item.entity_quality >= args.entity_threshold
    ]
    output = render_turtle(text, accepted)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)

    print(
        f"frames={len(frames)} resolved={len(candidates)} accepted={len(accepted)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

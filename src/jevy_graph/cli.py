from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .compiler import Thresholds, compile_text
from .jev import JevClient, JevError


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
        default=0.45,
        help="minimum exact-triple support probability (default: 0.45)",
    )
    parser.add_argument(
        "--entity-threshold",
        type=float,
        default=0.10,
        help="minimum RDF node-label quality probability (default: 0.10)",
    )
    parser.add_argument(
        "--joint-threshold",
        type=float,
        default=0.70,
        help="minimum support plus entity-quality score (default: 0.70)",
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
    if not 0 <= args.joint_threshold <= 2:
        raise SystemExit("--joint-threshold must be between 0 and 2")

    text = _read_text(args.input)
    client = None
    if not args.no_verify:
        _load_dotenv()
        api_key = os.environ.get("TYPESAFE_API_KEY", "")
        if not api_key:
            raise SystemExit("TYPESAFE_API_KEY is missing; set it in the environment or .env")
        client = JevClient(api_key)

    try:
        result = compile_text(
            text,
            client=client,
            thresholds=Thresholds(
                args.threshold, args.entity_threshold, args.joint_threshold
            ),
        )
    except JevError as error:
        raise SystemExit(str(error)) from error
    if args.output:
        Path(args.output).write_text(result.turtle, encoding="utf-8")
    else:
        sys.stdout.write(result.turtle)

    print(
        f"frames={result.frames} resolved={result.resolved} accepted={result.accepted}"
        f" singletons={result.singletons}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

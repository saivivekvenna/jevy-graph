from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import sys
from pathlib import Path

from .compiler import Thresholds, compile_text
from .config import load_dotenv
from .jev import JevClient, JevError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jevy-graph",
        description="Compile UTF-8 text into source-grounded RDF/Turtle.",
    )
    parser.add_argument("input", nargs="?", default="-", help="text file, or - for stdin")
    parser.add_argument("-o", "--output", help="output Turtle path; defaults to stdout")
    instruction = parser.add_mutually_exclusive_group()
    instruction.add_argument("--instruction", help="natural-language graph focus and organization")
    instruction.add_argument("--instruction-file", type=Path, help="UTF-8 file containing graph instructions")
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
    parser.add_argument(
        "--allow-reject",
        action="store_true",
        help="experiment with Jev declining every candidate for a relation frame",
    )
    parser.add_argument(
        "--scientific-parser", action="store_true",
        help="use the optional local scispaCy parser for structured scientific claims",
    )
    parser.add_argument("--scientific-parser-model", default="en_core_sci_sm")
    parser.add_argument(
        "--claims-output", type=Path,
        help="write structured scientific claims as JSON",
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
    graph_instruction = (
        args.instruction_file.read_text(encoding="utf-8")
        if args.instruction_file else args.instruction
    )
    if graph_instruction and args.no_verify:
        raise SystemExit("Graph instructions require Jev; remove --no-verify")
    if args.allow_reject and args.no_verify:
        raise SystemExit("--allow-reject requires Jev; remove --no-verify")
    client = None
    if not args.no_verify:
        load_dotenv()
        api_key = os.environ.get("TYPESAFE_API_KEY", "")
        if not api_key:
            raise SystemExit("TYPESAFE_API_KEY is missing; set it in the environment or .env")
        client = JevClient(api_key, allow_reject=args.allow_reject)

    try:
        dependency_compiler = None
        if args.scientific_parser:
            from .scientific import DependencyScientificCompiler
            dependency_compiler = DependencyScientificCompiler(
                args.scientific_parser_model,
            )
        result = compile_text(
            text,
            client=client,
            thresholds=Thresholds(
                args.threshold, args.entity_threshold, args.joint_threshold
            ),
            instruction=graph_instruction,
            scientific_dependency_compiler=dependency_compiler,
        )
    except (JevError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    if args.output:
        Path(args.output).write_text(result.turtle, encoding="utf-8")
    else:
        sys.stdout.write(result.turtle)
    if args.claims_output:
        args.claims_output.parent.mkdir(parents=True, exist_ok=True)
        args.claims_output.write_text(
            json.dumps([asdict(claim) for claim in result.claims], indent=2)
            + "\n",
            encoding="utf-8",
        )

    print(
        f"frames={result.frames} resolved={result.resolved} accepted={result.accepted}"
        f" singletons={result.singletons}",
        f" group_by={result.group_by}",
        file=sys.stderr,
    )
    if client is not None:
        print(
            f"jev_requests={client.usage.requests} "
            f"jev_input_tokens={client.usage.input_tokens} "
            f"jev_output_tokens={client.usage.output_tokens}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

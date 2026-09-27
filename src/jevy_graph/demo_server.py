from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import zipfile
from contextlib import closing
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

from .compiler import select
from .config import load_dotenv
from .extract import extract_frames
from .jev import JevClient, JevError
from .models import VerifiedTriple

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
BULK_GRAPH_FRAME_THRESHOLD = 2_000
SCIENTIFIC_DEPENDENCY_COMPILER = None
WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def claim_payload(item: VerifiedTriple, group_by: str = "none") -> dict[str, object]:
    """Convert one verified claim into the demo's streaming representation."""
    candidate = item.candidate
    predicate = candidate.predicate
    if candidate.polarity == "negative":
        predicate = f"not {predicate}"
    claim: dict[str, object] = {
        "subject": candidate.subject,
        "predicate": predicate,
        "object": candidate.object,
        "evidence": candidate.evidence,
        "polarity": candidate.polarity,
    }
    optional = {
        "claim_type": candidate.claim_type,
        "comparison": candidate.comparison,
        "conditions": candidate.conditions,
        "measurements": candidate.measurements,
        "modality": candidate.modality,
    }
    claim.update({key: value for key, value in optional.items() if value})
    if group_by != "none":
        claim["group"] = {
            "source": candidate.source_unit or "Document",
            "entity": candidate.subject,
            "relation": candidate.predicate,
        }[group_by]
    return claim


def extract_upload(payload: bytes, filename: str) -> str:
    """Convert a supported upload to the UTF-8 text accepted by the compiler."""
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf":
        executable = shutil.which("pdftotext")
        if not executable:
            raise ValueError("PDF support requires the pdftotext command.")
        with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
            source.write(payload)
            source.flush()
            result = subprocess.run(
                [executable, source.name, "-"],
                check=False,
                capture_output=True,
            )
        if result.returncode:
            raise ValueError("The PDF could not be read.")
        return result.stdout.decode("utf-8", errors="replace")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                document = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as error:
            raise ValueError("The DOCX file could not be read.") from error
        root = ElementTree.fromstring(document)
        paragraphs: list[str] = []
        for paragraph in root.iter(f"{WORD_NAMESPACE}p"):
            text = "".join(
                node.text or "" for node in paragraph.iter(f"{WORD_NAMESPACE}t")
            ).strip()
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Upload a UTF-8 text file, PDF, or DOCX document.") from error


class DemoHandler(SimpleHTTPRequestHandler):
    server_version = "JevyGraphDemo/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _event(self, event: dict[str, object]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.wfile.write(line.encode("utf-8"))
        self.wfile.flush()

    def do_GET(self) -> None:
        if self.path == "/healthz":
            payload = b'{"status":"ok"}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in {"", "/"}:
            self.send_response(302)
            self.send_header("Location", "/demo/")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/compile":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self.send_error(413, "Upload must be between 1 byte and 30 MB")
            return

        filename = urllib.parse.unquote(self.headers.get("X-Filename", "document.txt"))
        instruction = urllib.parse.unquote(self.headers.get("X-Graph-Instruction", "")).strip()
        if len(instruction) > 2_000:
            self.send_error(400, "Graph instruction must be at most 2,000 characters")
            return
        payload = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        try:
            text = extract_upload(payload, filename)
            if not text.strip():
                raise ValueError("The document contains no extractable text.")

            frames = extract_frames(
                text,
                scientific_dependency_compiler=SCIENTIFIC_DEPENDENCY_COMPILER,
            )
            api_key = os.environ.get("TYPESAFE_API_KEY", "")
            if not api_key:
                raise ValueError("TYPESAFE_API_KEY is missing from the server environment.")

            bulk = len(frames) >= BULK_GRAPH_FRAME_THRESHOLD
            client = JevClient(
                api_key,
                choice_batch_size=48 if bulk else 24,
                verification_batch_size=48 if bulk else 40,
                max_workers=12,
            )
            intent = client.interpret_instruction(instruction) if instruction else None
            if intent:
                self._event({
                    "type": "profile",
                    "instruction": instruction,
                    "group_by": intent.group_by,
                })
            seen: set[tuple[str, ...]] = set()
            claim_count = 0
            graph: list[dict[str, object]] = []
            last_heartbeat = time.monotonic()
            batches = (
                client.iter_score_batches(frames, instruction=instruction)
                if instruction else client.iter_score_batches(frames)
            )
            with closing(batches) as verified_batches:
                for verified_batch in verified_batches:
                    if bulk and time.monotonic() - last_heartbeat >= 1.0:
                        # Blank NDJSON lines detect a cancelled upload without
                        # streaming graph data or scheduling a browser layout.
                        self.wfile.write(b"\n")
                        self.wfile.flush()
                        last_heartbeat = time.monotonic()
                    accepted = select(verified_batch, seen=seen)
                    for item in accepted:
                        claim = claim_payload(
                            item,
                            intent.group_by if intent else "none",
                        )
                        if bulk:
                            graph.append(claim)
                        else:
                            self._event({"type": "claim", "claim": claim})
                        claim_count += 1
            if bulk:
                self._event({"type": "graph", "claims": graph})
            self._event({
                "type": "done", "claims": claim_count, "usage": asdict(client.usage)
            })
        except (BrokenPipeError, ConnectionResetError):
            return
        except (JevError, OSError, ValueError) as error:
            try:
                self._event({"type": "error", "message": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Jevy Graph demo.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument(
        "--scientific-parser", action="store_true",
        help="use the optional local scispaCy parser for scientific claims",
    )
    parser.add_argument("--scientific-parser-model", default="en_core_sci_sm")
    args = parser.parse_args(argv)

    load_dotenv()
    if args.scientific_parser:
        from .scientific import DependencyScientificCompiler
        global SCIENTIFIC_DEPENDENCY_COMPILER
        SCIENTIFIC_DEPENDENCY_COMPILER = DependencyScientificCompiler(
            args.scientific_parser_model,
        )
    package_root = Path(__file__).resolve().parent
    # Wheels bundle the frontend under jevy_graph/demo. Keep a source-tree
    # fallback so `PYTHONPATH=src python -m jevy_graph.demo_server` also works.
    content_root = (
        package_root
        if (package_root / "demo").is_dir()
        else package_root.parents[1]
    )
    handler = partial(DemoHandler, directory=str(content_root))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Jevy Graph demo: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

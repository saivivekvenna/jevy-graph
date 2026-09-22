from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

from .compiler import select
from .config import load_dotenv
from .extract import extract_frames
from .jev import JevClient, JevError

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


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

            frames = extract_frames(text)
            api_key = os.environ.get("TYPESAFE_API_KEY", "")
            if not api_key:
                raise ValueError("TYPESAFE_API_KEY is missing from the server environment.")

            client = JevClient(api_key)
            seen: set[tuple[str, str, str, str, str, str]] = set()
            claim_count = 0
            for verified_batch in client.iter_score_batches(frames):
                accepted = select(verified_batch, seen=seen)
                for item in accepted:
                    candidate = item.candidate
                    predicate = candidate.predicate
                    if candidate.polarity == "negative":
                        predicate = f"not {predicate}"
                    self._event(
                        {
                            "type": "claim",
                            "claim": {
                                "subject": candidate.subject,
                                "predicate": predicate,
                                "object": candidate.object,
                                "evidence": candidate.evidence,
                            },
                        }
                    )
                    claim_count += 1
            self._event({"type": "done", "claims": claim_count})
        except (BrokenPipeError, ConnectionResetError):
            return
        except (JevError, OSError, ValueError) as error:
            try:
                self._event({"type": "error", "message": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Jevy Graph demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    load_dotenv()
    repository_root = Path(__file__).resolve().parents[2]
    handler = partial(DemoHandler, directory=str(repository_root))
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

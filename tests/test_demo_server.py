from __future__ import annotations

import io
import json
import http.client
import os
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest import mock

from jevy_graph.demo_server import DemoHandler, extract_upload
from jevy_graph.extract import candidates_from_frames
from jevy_graph.jev import Usage
from jevy_graph.models import GraphIntent, VerifiedTriple


class DemoServerTests(unittest.TestCase):
    def test_health_endpoint_requires_no_api_key(self) -> None:
        with mock.patch.object(DemoHandler, "log_message"):
            server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            try:
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                payload = json.loads(response.read())
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join()
        self.assertEqual(response.status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_instruction_streams_profile_and_grouped_claim(self) -> None:
        class LocalClient:
            usage = Usage(requests=1)

            def interpret_instruction(self, instruction):
                self.instruction = instruction
                return GraphIntent(instruction, "relation")

            def iter_score_batches(self, frames, *, instruction=""):
                assert instruction == self.instruction
                for candidate in candidates_from_frames(frames):
                    yield [VerifiedTriple(candidate, 0.9, 0.9, 0.9)]

        with (
            mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}),
            mock.patch("jevy_graph.demo_server.JevClient", return_value=LocalClient()),
            mock.patch.object(DemoHandler, "log_message"),
        ):
            server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            try:
                connection.request(
                    "POST", "/api/compile", b"Alice founded Acme.",
                    {"X-Filename": "test.txt", "X-Graph-Instruction": "Group%20by%20relation%20type"},
                )
                response = connection.getresponse()
                events = [json.loads(line) for line in response.read().splitlines() if line]
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join()
        self.assertEqual([event["type"] for event in events], ["profile", "claim", "done"])
        self.assertEqual(events[0]["group_by"], "relation")
        self.assertEqual(events[1]["claim"]["group"], "founded")

    def test_bulk_upload_emits_one_complete_graph_and_usage(self) -> None:
        class LocalClient:
            usage = Usage(requests=2, input_tokens=123)

            def iter_score_batches(self, frames):
                for candidate in candidates_from_frames(frames):
                    yield [VerifiedTriple(candidate, 0.9, 0.9)]

        with (
            mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}),
            mock.patch("jevy_graph.demo_server.BULK_GRAPH_FRAME_THRESHOLD", 1),
            mock.patch("jevy_graph.demo_server.JevClient", return_value=LocalClient()),
            mock.patch.object(DemoHandler, "log_message"),
        ):
            server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            try:
                connection.request(
                    "POST", "/api/compile", b"Alice founded Acme. Acme uses RDF.",
                    {"X-Filename": "test.txt"},
                )
                response = connection.getresponse()
                events = [json.loads(line) for line in response.read().splitlines() if line]
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join()
        self.assertEqual(response.status, 200)
        self.assertEqual([event["type"] for event in events], ["graph", "done"])
        self.assertEqual(len(events[0]["claims"]), 2)
        self.assertEqual(events[1]["claims"], 2)
        self.assertEqual(events[1]["usage"]["input_tokens"], 123)

    def test_reads_utf8_text(self) -> None:
        self.assertEqual(
            extract_upload(b"Alice founded Acme.", "claims.txt"),
            "Alice founded Acme.",
        )

    def test_reads_docx_paragraphs(self) -> None:
        document = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body>'
            '<w:p><w:r><w:t>First claim.</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Second claim.</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("word/document.xml", document)
        self.assertEqual(
            extract_upload(payload.getvalue(), "paper.docx"),
            "First claim.\n\nSecond claim.",
        )

    @mock.patch("jevy_graph.demo_server.subprocess.run")
    @mock.patch(
        "jevy_graph.demo_server.shutil.which", return_value="/usr/bin/pdftotext"
    )
    def test_reads_pdf_in_document_order(
        self, _which: mock.Mock, run: mock.Mock
    ) -> None:
        run.return_value = mock.Mock(returncode=0, stdout=b"First. Second.")

        self.assertEqual(extract_upload(b"%PDF", "paper.pdf"), "First. Second.")

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/pdftotext")
        self.assertEqual(command[-1], "-")
        self.assertNotIn("-layout", command)


if __name__ == "__main__":
    unittest.main()

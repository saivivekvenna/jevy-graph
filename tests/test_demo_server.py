from __future__ import annotations

import io
import unittest
import zipfile
from unittest import mock

from jevy_graph.demo_server import extract_upload


class DemoServerTests(unittest.TestCase):
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

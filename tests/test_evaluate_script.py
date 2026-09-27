from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EvaluateScriptTests(unittest.TestCase):
    def test_changed_heldout_fixture_fails_before_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            fixture_dir.mkdir()
            fixture_path = fixture_dir / "probe.json"
            fixture = {
                "id": "probe", "domain": "general", "split": "test",
                "review_status": "codex_reviewed", "annotation_scope": "exhaustive",
                "text": "Alice founded Acme.", "gold": [],
            }
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            frozen_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps({
                "schema_version": 1, "fixtures": {"probe": frozen_hash},
            }), encoding="utf-8")
            fixture["text"] = "Alice acquired Acme."
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "scripts/evaluate.py", "--fixtures", str(fixture_dir),
                 "--test-manifest", str(manifest_path), "--id", "probe"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("changed=['probe']", result.stderr)


if __name__ == "__main__":
    unittest.main()

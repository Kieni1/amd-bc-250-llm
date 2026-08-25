from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))

import modelctl


MODEL = {
    "repository": "example/model",
    "revision": "latest",
    "gguf": "model.gguf",
    "sha256": "",
}


class StateTests(unittest.TestCase):
    def test_matching_state_reuses_moving_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            state = {**MODEL, "schema": 1, "sha256": modelctl.sha256(output)}
            self.assertTrue(modelctl.state_matches(state, MODEL, output))

    def test_changed_provenance_or_checksum_does_not_reuse_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            state = {**MODEL, "schema": 1, "sha256": modelctl.sha256(output)}
            for changed in (
                {**MODEL, "repository": "example/other"},
                {**MODEL, "revision": "new"},
                {**MODEL, "gguf": "other.gguf"},
                {**MODEL, "sha256": "0" * 64},
            ):
                with self.subTest(changed=changed):
                    self.assertFalse(modelctl.state_matches(state, changed, output))

    def test_invalid_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            path.write_text(json.dumps({"schema": 99}), encoding="utf-8")
            self.assertEqual(modelctl.load_state(path), {})


if __name__ == "__main__":
    unittest.main()

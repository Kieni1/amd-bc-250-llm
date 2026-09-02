from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
            digest = modelctl.sha256(output)
            stat = output.stat()
            state = {
                **MODEL,
                "schema": 2,
                "sha256": digest,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            self.assertTrue(modelctl.state_matches(state, MODEL, output))

    def test_changed_provenance_or_checksum_does_not_reuse_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            digest = modelctl.sha256(output)
            stat = output.stat()
            state = {
                **MODEL,
                "schema": 2,
                "sha256": digest,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            for changed in (
                {**MODEL, "repository": "example/other"},
                {**MODEL, "revision": "new"},
                {**MODEL, "gguf": "other.gguf"},
                {**MODEL, "sha256": "0" * 64},
            ):
                with self.subTest(changed=changed):
                    self.assertFalse(modelctl.state_matches(state, changed, output))

    def test_modified_gguf_is_not_reused_even_when_sidecar_provenance_matches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            digest = modelctl.sha256(output)
            stat = output.stat()
            state = {
                **MODEL,
                "schema": 2,
                "sha256": digest,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            output.write_bytes(b"WEIGHTS")  # same size; writing changes ctime
            os.utime(
                output, ns=(stat.st_atime_ns, stat.st_mtime_ns)
            )  # preserve recorded mtime
            self.assertFalse(modelctl.state_matches(state, MODEL, output))

    def test_cleanup_retains_local_source_when_ollama_registration_removal_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.gguf"
            output.write_bytes(b"weights")
            model = {
                "id": "m",
                "name": "prod-test",
                "provider": "ollama",
                "from": str(output),
                "gguf": output.name,
            }
            args = SimpleNamespace(yes=True, keep_gguf=False)
            with (
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(
                    modelctl,
                    "run_as_ollama",
                    return_value=SimpleNamespace(returncode=1),
                ),
                patch.object(modelctl, "registered_models", return_value={"prod-test"}),
            ):
                self.assertEqual(
                    modelctl.cleanup_models(
                        {"ollama_host": "127.0.0.1:11434"}, [model], args
                    ),
                    2,
                )
            self.assertTrue(output.exists())

    def test_cleanup_can_remove_ollama_registration_but_keep_local_gguf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "model.gguf"
            output.write_bytes(b"weights")
            sidecar = modelctl.state_path(output)
            sidecar.write_text("{}", encoding="utf-8")
            runtime = base / "runtime"
            runtime.mkdir()
            runtime_file = runtime / "prod-test.Modelfile"
            runtime_file.write_text("FROM /tmp/model.gguf\n", encoding="utf-8")
            model = {
                "id": "m", "name": "prod-test", "provider": "ollama",
                "from": str(output), "gguf": output.name,
                "modelfile": runtime_file.name,
            }
            args = SimpleNamespace(yes=True, keep_gguf=True)
            with (
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=0)) as run_rm,
            ):
                self.assertEqual(modelctl.cleanup_models(
                    {"ollama_host": "127.0.0.1:11434", "modelfile_destination": str(runtime)},
                    [model], args), 0)
                run_rm.assert_called_once_with(
                    ["/usr/bin/ollama", "rm", "prod-test"],
                    {"HOME": "/var/lib/ollama", "OLLAMA_HOST": "127.0.0.1:11434"},
                )
            self.assertTrue(output.exists())
            self.assertTrue(sidecar.exists())
            self.assertFalse(runtime_file.exists())

    def test_remote_ocr_keep_gguf_explains_ollama_managed_source(self) -> None:
        model = {
            "id": "m",
            "name": "exp-vision",
            "provider": "ollama-hf",
            "from": "hf.co/example/vision:Q8_0",
            "gguf": "vision.gguf",
        }
        args = SimpleNamespace(yes=True, keep_gguf=True)
        capture = StringIO()
        with (
            patch.object(modelctl.os, "geteuid", return_value=0),
            patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
            patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
            patch.object(
                modelctl,
                "run_as_ollama",
                return_value=SimpleNamespace(returncode=0),
            ),
            redirect_stdout(capture),
        ):
            self.assertEqual(
                modelctl.cleanup_models(
                    {"ollama_host": "127.0.0.1:11434"}, [model], args
                ),
                0,
            )
        text = capture.getvalue()
        self.assertIn("no manager-owned GGUF/state to retain", text)
        self.assertIn("multimodal source/projector blobs are Ollama-managed", text)

    def test_normal_cleanup_still_removes_local_gguf_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.gguf"
            output.write_bytes(b"weights")
            sidecar = modelctl.state_path(output)
            sidecar.write_text("{}", encoding="utf-8")
            model = {"id": "m", "name": "prod-test", "provider": "ollama", "from": str(output), "gguf": output.name}
            args = SimpleNamespace(yes=True, keep_gguf=False)
            with (
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=0)),
            ):
                self.assertEqual(modelctl.cleanup_models({"ollama_host": "127.0.0.1:11434"}, [model], args), 0)
            self.assertFalse(output.exists())
            self.assertFalse(sidecar.exists())

    def test_invalid_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            path.write_text(json.dumps({"schema": 99}), encoding="utf-8")
            self.assertEqual(modelctl.load_state(path), {})


if __name__ == "__main__":
    unittest.main()

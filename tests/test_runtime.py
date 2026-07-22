from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))

import modelctl


class AuthenticationTests(unittest.TestCase):
    def test_rejected_token_falls_back_without_persisting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"HF_TOKEN": "rejected", "BC250_HF_ANONYMOUS": "1"}
        ), patch.object(
            modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=1)
        ):
            self.assertEqual(modelctl.hf_token("hf", Path(temporary), None), "")
        self.assertNotIn("bashrc", (ROOT / "models/modelctl.py").read_text())

    def test_hf_download_environment_keeps_progress_and_token(self) -> None:
        environment = modelctl.hf_environment("secret", Path("/cache/hf"))
        self.assertEqual(environment["HF_TOKEN"], "secret")
        self.assertEqual(environment["HF_HUB_DISABLE_PROGRESS_BARS"], "0")
        self.assertEqual(environment["PYTHONUNBUFFERED"], "1")

    def test_hf_download_can_run_in_a_progress_terminal(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(
            modelctl, "command_path", side_effect=lambda name: f"/usr/bin/{name}"
        ), patch.object(modelctl.subprocess, "run", return_value=completed) as run:
            result = modelctl.run_as_ollama(
                ["/usr/bin/hf", "download", "owner/repo", "model.gguf"],
                {"HF_TOKEN": "secret"},
                terminal=True,
            )

        self.assertIs(result, completed)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["/usr/bin/script", "--quiet", "--return", "--flush"])
        self.assertIn("/usr/bin/runuser", command[5])
        self.assertIn("owner/repo", command[5])


class RuntimeContractTests(unittest.TestCase):
    def test_host_precedence_preserves_both_supported_environment_names(self) -> None:
        source = (ROOT / "models/modelctl.py").read_text(encoding="utf-8")
        host_expression = (
            'args.host or os.environ.get("OLLAMA_HOST") or '
            'os.environ.get("OLLAMA_URL")'
        )
        self.assertIn(host_expression, source.replace("\\\n        ", ""))

    def test_install_does_not_probe_ollama_before_download(self) -> None:
        source = (ROOT / "models/modelctl.py").read_text(encoding="utf-8")
        self.assertNotIn("/api/tags", source)
        self.assertNotIn("curl", source)


if __name__ == "__main__":
    unittest.main()

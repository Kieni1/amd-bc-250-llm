from __future__ import annotations

import os
import io
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


class OcrInstallTests(unittest.TestCase):
    def test_remote_ocr_install_uses_ollama_without_hf_download_tools(self) -> None:
        defaults, models = modelctl.load_models(
            "experiments", directories=[ROOT / "models/modelfiles"]
        )
        model = next(item for item in models if item["name"] == "exp-glm-ocr-ggml-q8-0")
        args = SimpleNamespace(
            revision=None, sha256=None, destination=None, min_free_bytes=None,
            token_file=None, refresh=False, host=None,
        )
        completed = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"MODELFILE_DIR": temporary}, clear=False
        ), patch.object(modelctl.os, "geteuid", return_value=0), patch.object(
            modelctl, "ollama_identity", return_value=(1000, 1000)
        ), patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"), patch.object(
            modelctl, "command_path", side_effect=lambda name: f"/usr/bin/{name}"
        ) as command_path, patch.object(
            modelctl, "run_as_ollama", return_value=completed
        ) as run:
            self.assertEqual(modelctl.install_models(defaults, [model], args), 0)
            rendered = Path(temporary, model["modelfile"]).read_text(encoding="utf-8")

        requested = [call.args[0] for call in command_path.call_args_list]
        self.assertNotIn("hf", requested)
        self.assertNotIn("script", requested)
        self.assertIn("FROM hf.co/ggml-org/GLM-OCR-GGUF:Q8_0", rendered)
        self.assertEqual(run.call_args.args[0][:2], ["/usr/bin/ollama", "create"])

    def test_hf_backing_registration_is_removed_after_friendly_alias(self) -> None:
        defaults, models = modelctl.load_models(
            "experiments", directories=[ROOT / "models/modelfiles"]
        )
        model = next(item for item in models if item["name"] == "exp-glm-ocr-ggml-q8-0")
        completed = SimpleNamespace(returncode=0)
        with patch.object(
            modelctl, "registered_models",
            side_effect=[{model["from"], model["name"]}, {model["name"]}],
        ), patch.object(modelctl, "run_as_ollama", return_value=completed) as run:
            modelctl.remove_hf_backing_registration("/usr/bin/ollama", defaults["ollama_host"], model)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/ollama", "rm", model["from"]])

    def test_hf_backing_with_friendly_alias_is_not_reported_as_unmanaged(self) -> None:
        _, models = modelctl.load_models(
            "experiments", directories=[ROOT / "models/modelfiles"]
        )
        model = next(item for item in models if item["name"] == "exp-glm-ocr-ggml-q8-0")
        main_host = modelctl.CATEGORY_DEFAULTS[model["category"]]["ollama_host"]
        registrations = {model["name"], model["from"]}
        output = io.StringIO()
        with patch.object(modelctl, "discover_models", return_value=[model]), patch.object(
            modelctl, "registered_models", side_effect=lambda host: registrations if host == main_host else set()
        ), patch("sys.stdout", output):
            modelctl.print_all_models([ROOT / "models/modelfiles"] )
        self.assertNotIn("Unmanaged Ollama models", output.getvalue())

    def test_invalid_ocr_alias_fails_before_manager_or_ollama(self) -> None:
        script = ROOT / "models/ocr/bc250-ocr.sh"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            marker = temporary_path / "called"
            manager = temporary_path / "manager"
            ollama = temporary_path / "ollama"
            body = f'#!/bin/sh\ntouch "{marker}"\nexit 0\n'
            manager.write_text(body, encoding="utf-8")
            ollama.write_text(body, encoding="utf-8")
            manager.chmod(0o755)
            ollama.chmod(0o755)
            environment = os.environ.copy()
            environment["MODEL_MANAGER"] = str(manager)
            environment["PATH"] = f"{temporary}:{environment.get('PATH', '')}"
            for action in ("install", "show"):
                with self.subTest(action=action):
                    marker.unlink(missing_ok=True)
                    result = subprocess.run(
                        [str(script), action, "nope"],
                        env=environment, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, check=False,
                    )
                    self.assertEqual(result.returncode, 2, result.stdout)
                    self.assertIn("OCR model must be", result.stdout)
                    self.assertFalse(marker.exists(), result.stdout)


class RuntimeContractTests(unittest.TestCase):
    def test_host_precedence_preserves_both_supported_environment_names(self) -> None:
        source = (ROOT / "models/modelctl.py").read_text(encoding="utf-8")
        host_expression = (
            'return override or os.environ.get("OLLAMA_HOST") or '
            'os.environ.get("OLLAMA_URL")'
        )
        self.assertIn(host_expression, source.replace("\\\n        ", ""))
        self.assertIn("host = ollama_host(defaults, args.host)", source)

    def test_install_does_not_probe_ollama_before_download(self) -> None:
        source = (ROOT / "models/modelctl.py").read_text(encoding="utf-8")
        self.assertNotIn("/api/tags", source)
        self.assertNotIn("curl", source)

    def test_missing_progress_terminal_names_the_fedora_package(self) -> None:
        with patch.object(modelctl.shutil, "which", return_value=None):
            with self.assertRaisesRegex(modelctl.ModelError, "util-linux-script"):
                modelctl.command_path("script")


if __name__ == "__main__":
    unittest.main()

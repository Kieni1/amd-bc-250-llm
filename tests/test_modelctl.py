from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import errno
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "models/modelctl.py"
SPEC = importlib.util.spec_from_file_location("bc250_modelctl_tests", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
modelctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(modelctl)


class SelectionTests(unittest.TestCase):
    def test_all_and_empty_select_every_entry(self) -> None:
        self.assertEqual(modelctl.parse_selection("all", 4), [0, 1, 2, 3])
        self.assertEqual(modelctl.parse_selection("", 3), [0, 1, 2])

    def test_ranges_are_normalized_and_deduplicated(self) -> None:
        self.assertEqual(modelctl.parse_selection("0,2-4,3,1", 5), [0, 2, 3, 4, 1])
        self.assertEqual(modelctl.parse_selection("3-1", 4), [1, 2, 3])

    def test_out_of_range_values_are_not_selected(self) -> None:
        self.assertEqual(modelctl.parse_selection("8,2-9", 4), [2, 3])


class CatalogTests(unittest.TestCase):
    def test_all_repository_catalogs_validate(self) -> None:
        for category in modelctl.CATEGORIES:
            with self.subTest(category=category):
                source, modelfiles = modelctl.default_paths(category)
                defaults, models = modelctl.load_catalog(
                    source,
                    category,
                    modelfiles,
                    strict_metadata=True,
                )
                self.assertTrue(models)
                self.assertEqual(defaults["category"], category)

    def test_experiment_paths_include_the_entry_id(self) -> None:
        defaults, models = modelctl.load_catalog(
            ROOT / "models/sources/experiments.toml",
            "experiments",
            ROOT / "models/modelfiles/experiments",
        )
        first = models[0]
        self.assertEqual(
            modelctl.model_output_path(defaults, first),
            Path(defaults["destination"]) / first["id"] / first["gguf"],
        )

    def test_default_enablement_matches_appliance_roles(self) -> None:
        expected = {
            "production": 0,
            "experiments": 0,
            "mtp": 0,
            "task": 1,
            "coding": 2,
        }
        for category, count in expected.items():
            source, modelfiles = modelctl.default_paths(category)
            _defaults, models = modelctl.load_catalog(
                source,
                category,
                modelfiles,
            )
            self.assertEqual(sum(model["enabled"] for model in models), count)

    def test_every_packaged_modelfile_is_referenced_by_its_full_name(self) -> None:
        for category in modelctl.CATEGORIES:
            source, modelfiles = modelctl.default_paths(category)
            _defaults, models = modelctl.load_catalog(
                source,
                category,
                modelfiles,
            )
            referenced = {
                model["modelfile"] for model in models if model["provider"] == "ollama"
            }
            packaged = {
                path.name for path in (ROOT / "models/modelfiles" / category).glob("*.Modelfile")
            }
            self.assertEqual(referenced, packaged)
            for model in models:
                if model["provider"] == "ollama":
                    self.assertEqual(model["modelfile"], f"{model['name']}.Modelfile")

    def test_mtp_catalog_is_download_only_and_rejects_ollama_entries(self) -> None:
        _mtp_defaults, mtp_models = modelctl.load_catalog(
            ROOT / "models/mtp/models.toml",
            "mtp",
            ROOT / "models/modelfiles/mtp",
        )
        _experiment_defaults, experiment_models = modelctl.load_catalog(
            ROOT / "models/sources/experiments.toml",
            "experiments",
            ROOT / "models/modelfiles/experiments",
        )
        self.assertTrue(all(model["provider"] == "download-only" for model in mtp_models))
        self.assertTrue(all(model["provider"] == "ollama" for model in experiment_models))
        ollama = dict(experiment_models[0])
        mtp = dict(mtp_models[0])
        ollama["enabled"] = True
        mtp["enabled"] = True
        enabled = [ollama, mtp]
        self.assertEqual(
            modelctl.resolve_model(enabled, mtp["id"], "download-only")["id"],
            mtp["id"],
        )
        with self.assertRaisesRegex(modelctl.ModelError, "download-only"):
            modelctl.resolve_model(enabled, ollama["id"], "download-only")

    def test_operator_revision_override_does_not_require_modelfile_edits(self) -> None:
        original = (ROOT / "models/sources/production.toml").read_text(encoding="utf-8")
        changed = original.replace('revision = "latest"', 'revision = "main"', 1)
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "production.toml"
            catalog.write_text(changed, encoding="utf-8")
            _defaults, models = modelctl.load_catalog(
                catalog,
                "production",
                ROOT / "models/modelfiles/production",
            )
            self.assertEqual(models[0]["revision"], "main")
            with self.assertRaises(modelctl.ModelError):
                modelctl.load_catalog(
                    catalog,
                    "production",
                    ROOT / "models/modelfiles/production",
                    strict_metadata=True,
                )


class InstallWorkflowTests(unittest.TestCase):
    def test_cross_filesystem_download_uses_atomic_copy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "download/model.gguf"
            output = root / "destination/model.gguf"
            staged.parent.mkdir()
            output.parent.mkdir()
            staged.write_bytes(b"payload")
            real_replace = os.replace
            calls = 0

            def replace_with_exdev(source: Path, destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError(errno.EXDEV, "cross-device link")
                real_replace(source, destination)

            with mock.patch.object(modelctl.os, "replace", side_effect=replace_with_exdev):
                modelctl.move_download(staged, output)

            self.assertEqual(output.read_bytes(), b"payload")
            self.assertFalse(staged.exists())
            self.assertEqual(list(output.parent.glob("*.partial")), [])

    def test_download_create_and_runtime_overrides_are_applied_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            modelfiles = root / "templates"
            modelfiles.mkdir()
            template = modelfiles / "model.Modelfile"
            template.write_text(
                "# Ollama model: original-name\n"
                "# Source: example/original @ latest\n"
                "# GGUF: model.gguf\n"
                f"FROM {root / 'default/model.gguf'}\n"
                "PARAMETER num_gpu 99\n",
                encoding="utf-8",
            )
            payload = b"synthetic GGUF payload"
            model = {
                "enabled": True,
                "provider": "ollama",
                "id": "model-id",
                "name": "original-name",
                "repository": "example/original",
                "revision": "latest",
                "gguf": "model.gguf",
                "modelfile": "model.Modelfile",
            }
            defaults = {
                "category": "coding",
                "destination": str(root / "default"),
                "download_namespace": "coding",
                "layout": "flat",
                "ollama_host": "127.0.0.1:11436",
            }
            destination = root / "override"
            args = argparse.Namespace(
                revision="main",
                sha256=hashlib.sha256(payload).hexdigest(),
                destination=str(destination),
                min_free_bytes=None,
                host=None,
            )
            create_calls: list[tuple[list[str], str]] = []
            api_request = mock.Mock(return_value={})

            def fake_run_as_ollama(command: list[str], _environment: dict[str, str]):
                if "download" in command:
                    local_dir = Path(command[command.index("--local-dir") + 1])
                    local_dir.mkdir(parents=True, exist_ok=True)
                    (local_dir / model["gguf"]).write_bytes(payload)
                elif "create" in command:
                    runtime = Path(command[command.index("-f") + 1])
                    create_calls.append((command, runtime.read_text(encoding="utf-8")))
                return subprocess.CompletedProcess(command, 0)

            with (
                redirect_stdout(io.StringIO()),
                mock.patch.object(modelctl.os, "geteuid", return_value=0),
                mock.patch.object(modelctl, "_ollama_identity", return_value=(os.getuid(), os.getgid())),
                mock.patch.object(modelctl, "_command_path", side_effect=lambda name: f"/fake/{name}"),
                mock.patch.object(modelctl, "_prompt_hf_token", return_value=""),
                mock.patch.object(modelctl, "_run_as_ollama", side_effect=fake_run_as_ollama),
                mock.patch.object(modelctl, "_api_request", api_request),
                mock.patch.object(modelctl.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
                mock.patch.dict(
                    os.environ,
                    {
                        "HF_HOME": str(root / "hf"),
                        "DOWNLOAD_DIR": str(root / "downloads"),
                        "OLLAMA_URL": "http://ollama.example:11434",
                    },
                    clear=True,
                ),
            ):
                result = modelctl.install_models(defaults, [model], modelfiles, args)

            self.assertEqual(result, 0)
            api_request.assert_any_call("http://ollama.example:11434", "/api/tags")
            self.assertEqual((destination / "model.gguf").read_bytes(), payload)
            self.assertEqual(len(create_calls), 1)
            command, rendered = create_calls[0]
            self.assertEqual(command[2], "original-name")
            self.assertIn("# Ollama model: original-name", rendered)
            self.assertIn("# Source: example/original @ main", rendered)
            self.assertIn(f"FROM {destination / 'model.gguf'}", rendered)


class IsolatedInstanceTests(unittest.TestCase):
    def test_task_and_agent_instances_use_dedicated_ports_and_stores(self) -> None:
        setup = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        self.assertIn('port="${TASK_PORT:-11435}"', setup)
        self.assertIn('service="ollama-task.service"', setup)
        self.assertIn('instance_root="/var/llm/ollama-task"', setup)
        self.assertIn('port="${CODING_AGENT_PORT:-11436}"', setup)
        self.assertIn('service="ollama-agent.service"', setup)
        self.assertIn('instance_root="/var/llm/ollama-agent"', setup)

    def test_coding_client_defaults_to_the_agent_instance(self) -> None:
        client = (ROOT / "models/coding-agent/coding-agent.sh").read_text(encoding="utf-8")
        self.assertIn("agentic-ornith1-9b-deepreinforce-q5-k-m", client)
        self.assertIn("127.0.0.1:11436", client)
        self.assertIn("OLLAMA_HOST", client)
        self.assertIn("OLLAMA_URL", client)


if __name__ == "__main__":
    unittest.main()

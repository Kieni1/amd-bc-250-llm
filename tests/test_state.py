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
    def test_registration_is_current_only_when_all_three_inputs_match(self) -> None:
        current = {"prod-test"}
        self.assertTrue(modelctl.registration_current(
            "prod-test", current, refresh=False, source_changed=False, template_changed=False
        ))
        for kwargs in (
            {"refresh": True, "source_changed": False, "template_changed": False},
            {"refresh": False, "source_changed": True, "template_changed": False},
            {"refresh": False, "source_changed": False, "template_changed": True},
        ):
            self.assertFalse(modelctl.registration_current("prod-test", current, **kwargs))
        self.assertFalse(modelctl.registration_current(
            "prod-test", set(), refresh=False, source_changed=False, template_changed=False
        ))

    def test_failed_hf_download_is_rejected_even_if_file_is_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            destination = base / "models"
            download_root = base / "downloads"
            model = {
                "id": "download-test",
                "name": "download-test",
                "provider": "download-only",
                "repository": "example/model",
                "revision": "latest",
                "gguf": "model.gguf",
                "sha256": "",
            }
            defaults = {
                "destination": str(destination),
                "layout": "flat",
                "download_namespace": "test",
                "min_free_bytes": 0,
                "ollama_host": "127.0.0.1:11434",
            }
            args = SimpleNamespace(
                revision=None, sha256=None, destination=None, min_free_bytes=0,
                token_file=None, refresh=False, host=None,
            )

            def failed_download(command, environment, *, terminal=False):
                staged = download_root / model["id"] / model["gguf"]
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(b"partial-but-present")
                return SimpleNamespace(returncode=1)

            with (
                patch.dict(
                    os.environ,
                    {
                        "DOWNLOAD_DIR": str(download_root),
                        "HF_HOME": str(base / "hf"),
                        "BC250_HF_ANONYMOUS": "1",
                    },
                    clear=False,
                ),
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl, "command_path", side_effect=lambda name: f"/usr/bin/{name}"),
                patch.object(modelctl.os, "chown"),
                patch.object(modelctl, "run_as_ollama", side_effect=failed_download),
            ):
                self.assertEqual(modelctl.install_models(defaults, [model], args), 2)

            self.assertFalse((destination / model["gguf"]).exists())
            self.assertFalse(modelctl.state_path(destination / model["gguf"]).exists())

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

    def test_cleanup_preview_distinguishes_remove_and_keep_gguf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.gguf"
            source.write_bytes(b"weights")
            model = {
                "id": "m", "name": "prod-test", "provider": "ollama",
                "from": str(source), "gguf": source.name, "modelfile": "prod-test.Modelfile",
            }
            defaults = {
                "destination": str(root),
                "ollama_host": "127.0.0.1:11434",
                "modelfile_destination": str(root / "runtime"),
            }
            for keep, expected in ((False, "remove"), (True, "retain")):
                capture = StringIO()
                args = SimpleNamespace(keep_gguf=keep, host=None, destination=None)
                with redirect_stdout(capture):
                    modelctl.show_cleanup_plan([(defaults, [model])], args)
                text = capture.getvalue()
                self.assertIn(f"Manager-owned source: {expected} {source}", text)
                self.assertIn(f"State sidecar: {expected} {modelctl.state_path(source)}", text)
                self.assertIn("Packaged/source Modelfile definition: retain", text)

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


    def test_cleanup_accepts_install_host_and_destination_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            default_root = base / "default"
            custom_root = base / "custom"
            default_root.mkdir()
            custom_root.mkdir()
            default_output = default_root / "model.gguf"
            custom_output = custom_root / "model.gguf"
            default_output.write_bytes(b"default-marker")
            custom_output.write_bytes(b"weights")
            custom_sidecar = modelctl.state_path(custom_output)
            custom_sidecar.write_text("{}", encoding="utf-8")
            model = {
                "id": "m",
                "name": "prod-test",
                "provider": "ollama",
                "from": str(default_output),
                "gguf": "model.gguf",
            }
            args = SimpleNamespace(
                yes=True, keep_gguf=False, host="127.0.0.1:19999",
                destination=str(custom_root),
            )
            with (
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(
                    modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=0)
                ) as run_rm,
            ):
                self.assertEqual(
                    modelctl.cleanup_models(
                        {
                            "destination": str(default_root),
                            "ollama_host": "127.0.0.1:11434",
                        },
                        [model],
                        args,
                    ),
                    0,
                )
            run_rm.assert_called_once_with(
                ["/usr/bin/ollama", "rm", "prod-test"],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": "127.0.0.1:19999"},
            )
            self.assertFalse(custom_output.exists())
            self.assertFalse(custom_sidecar.exists())
            self.assertTrue(default_output.exists())

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

    def test_schema3_state_records_model_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.gguf"
            output.write_bytes(b"weights")
            model = {
                "id": "exp-test",
                "name": "exp-test-long-name",
                "category": "experiments",
                "repository": "example/model",
                "revision": "main",
                "gguf": "model.gguf",
            }
            sidecar = modelctl.state_path(output)
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(sidecar, model, modelctl.sha256(output), 1)
            state = json.loads(sidecar.read_text())
            self.assertEqual(state["schema"], 3)
            self.assertEqual(state["model_name"], "exp-test-long-name")
            self.assertEqual(state["model_id"], "exp-test")
            self.assertEqual(state["category"], "experiments")


    def test_write_state_preserves_dedupe_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.gguf"
            output.write_bytes(b"weights")
            sidecar = modelctl.state_path(output)
            record = {
                "main/sha256-" + "a" * 64: {
                    "source": {"size": 7},
                    "blob": {"size": 7},
                }
            }
            sidecar.write_text(
                json.dumps({"schema": 3, "dedupe": record}),
                encoding="utf-8",
            )
            model = {
                "id": "exp-test",
                "name": "exp-test",
                "category": "experiments",
                "repository": "example/model",
                "revision": "main",
                "gguf": "model.gguf",
            }
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(sidecar, model, modelctl.sha256(output), 1)
            state = json.loads(sidecar.read_text())
            self.assertEqual(state["dedupe"], record)

    def test_current_schema3_fast_path_does_not_force_state_rewrite(self) -> None:
        source = (ROOT / "models/modelctl.py").read_text()
        self.assertIn('state.get("schema") != 3', source)
        self.assertNotIn('state.get("schema") != 2\n', source)

    def test_cleanup_retired_removes_only_catalogued_package_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_root = base / "gguf" / "experiments"
            runtime_root = base / "modelfiles" / "experiments"
            source = source_root / "retired.gguf"
            runtime = runtime_root / "retired.Modelfile"
            source.parent.mkdir(parents=True); runtime.parent.mkdir(parents=True)
            source.write_bytes(b"weights"); modelctl.state_path(source).write_text("{}")
            runtime.write_text("FROM retired.gguf\n")
            catalog = base / "retired-models.json"
            catalog.write_text(json.dumps({"schema": 1, "models": [{
                "name": "exp-retired",
                "category": "experiments",
                "ollama_host": "127.0.0.1:11434",
                "source": str(source),
                "runtime_modelfile": str(runtime),
            }]}))
            defaults = dict(modelctl.CATEGORY_DEFAULTS["experiments"])
            defaults["destination"] = str(source_root)
            defaults["modelfile_destination"] = str(runtime_root)
            with (
                patch.object(modelctl, "local_source_root", return_value=None),
                patch.object(modelctl, "RETIRED_CATALOG", catalog),
                patch.dict(modelctl.CATEGORY_DEFAULTS, {"experiments": defaults}),
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(
                    modelctl,
                    "registered_models",
                    side_effect=lambda host: {"exp-retired"} if host == "127.0.0.1:11434" else set(),
                ),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=0)),
            ):
                self.assertEqual(modelctl.cleanup_retired(yes=True), 0)
            self.assertFalse(source.exists())
            self.assertFalse(modelctl.state_path(source).exists())
            self.assertFalse(runtime.exists())


    def test_cleanup_retired_refuses_misplaced_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_root = base / "gguf" / "experiments"
            runtime_root = base / "modelfiles" / "experiments"
            source = source_root / "retired.gguf"
            runtime = runtime_root / "retired.Modelfile"
            source.parent.mkdir(parents=True); runtime.parent.mkdir(parents=True)
            source.write_bytes(b"weights"); modelctl.state_path(source).write_text("{}")
            runtime.write_text("FROM retired.gguf\n")
            catalog = base / "retired-models.json"
            catalog.write_text(json.dumps({"schema": 1, "models": [{
                "name": "exp-retired", "category": "experiments",
                "ollama_host": "127.0.0.1:11434", "source": str(source),
                "runtime_modelfile": str(runtime),
            }]}))
            defaults = dict(modelctl.CATEGORY_DEFAULTS["experiments"])
            defaults["destination"] = str(source_root)
            defaults["modelfile_destination"] = str(runtime_root)
            with (
                patch.object(modelctl, "local_source_root", return_value=None),
                patch.object(modelctl, "RETIRED_CATALOG", catalog),
                patch.dict(modelctl.CATEGORY_DEFAULTS, {"experiments": defaults}),
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(
                    modelctl, "registered_models",
                    side_effect=lambda host: {"exp-retired"} if host == "127.0.0.1:11435" else set(),
                ),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
            ):
                self.assertEqual(modelctl.cleanup_retired(yes=True), 2)
            self.assertTrue(source.exists())
            self.assertTrue(runtime.exists())



if __name__ == "__main__":
    unittest.main()

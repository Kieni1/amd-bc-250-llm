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
    def test_model_inspection_combines_source_modelfile_and_registration_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.gguf"
            source.write_bytes(b"weights")
            template = root / "prod-test.Modelfile"
            template.write_text(
                "# BC250 category: production\n"
                "# Ollama model: prod-test\n"
                "# Source: example/model @ latest\n"
                "# GGUF: model.gguf\n"
                f"FROM {source}\n",
                encoding="utf-8",
            )
            model = {
                "id": "prod-test", "name": "prod-test", "category": "production",
                "provider": "ollama", "repository": "example/model",
                "revision": "latest", "gguf": "model.gguf", "sha256": "",
                "template": template, "modelfile": template.name, "origin": "packaged",
                "from": str(source),
            }
            sidecar = modelctl.state_path(source)
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(sidecar, model, modelctl.sha256(source), 1)
            defaults = {
                "destination": str(root),
                "modelfile_destination": str(root / "runtime"),
                "ollama_host": "127.0.0.1:11434",
            }
            runtime = Path(defaults["modelfile_destination"]) / template.name
            runtime.parent.mkdir()
            runtime.write_text(
                modelctl.rendered_modelfile_content(template, model, source),
                encoding="utf-8",
            )
            current = modelctl.inspect_model_state(
                defaults, model, registrations={"prod-test"}
            )
            self.assertEqual(current.overall_status, "CURRENT")
            self.assertEqual(current.source_status, "current")
            self.assertEqual(current.modelfile_status, "current")
            self.assertEqual(current.registration_status, "current")

            runtime.write_text("FROM /wrong/model.gguf\n", encoding="utf-8")
            drift = modelctl.inspect_model_state(
                defaults, model, registrations={"prod-test"}
            )
            self.assertEqual(drift.overall_status, "DRIFT")
            self.assertEqual(drift.modelfile_status, "drift")

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
                command="apply", revision=None, sha256=None, destination=None, min_free_bytes=0,
                token_file=None, host=None, hf_session={"resolved": False, "token": ""},
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
                self.assertEqual(modelctl.apply_models(defaults, [model], args), 2)

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

    def test_removal_preview_distinguishes_remove_and_unregister(self) -> None:
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
            for command, expected in (("remove", "remove"), ("unregister", "retain")):
                capture = StringIO()
                args = SimpleNamespace(command=command, host=None, destination=None)
                with redirect_stdout(capture):
                    modelctl.show_removal_plan([(defaults, [model])], args)
                text = capture.getvalue()
                self.assertIn(f"Manager-owned source: {expected} {source}", text)
                self.assertIn(f"State sidecar: {expected} {modelctl.state_path(source)}", text)
                self.assertIn("Catalog definition: retain", text)

    def test_remove_retains_local_source_when_registration_removal_fails(
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
            args = SimpleNamespace(command="remove", yes=True, host=None, destination=None)
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
                    modelctl.remove_models(
                        {"ollama_host": "127.0.0.1:11434"}, [model], args
                    ),
                    2,
                )
            self.assertTrue(output.exists())

    def test_unregister_removes_registration_but_keeps_local_gguf(self) -> None:
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
            args = SimpleNamespace(command="unregister", yes=True, host=None, destination=None)
            with (
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=0)) as run_rm,
            ):
                self.assertEqual(modelctl.remove_models(
                    {"ollama_host": "127.0.0.1:11434", "modelfile_destination": str(runtime)},
                    [model], args), 0)
                run_rm.assert_called_once_with(
                    ["/usr/bin/ollama", "rm", "prod-test"],
                    {"HOME": "/var/lib/ollama", "OLLAMA_HOST": "127.0.0.1:11434"},
                )
            self.assertTrue(output.exists())
            self.assertTrue(sidecar.exists())
            self.assertFalse(runtime_file.exists())


    def test_remove_accepts_host_and_destination_overrides(self) -> None:
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
                command="remove", yes=True, host="127.0.0.1:19999",
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
                    modelctl.remove_models(
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

    def test_unregister_remote_ocr_explains_ollama_managed_source(self) -> None:
        model = {
            "id": "m",
            "name": "exp-vision",
            "provider": "ollama-hf",
            "from": "hf.co/example/vision:Q8_0",
            "gguf": "vision.gguf",
        }
        args = SimpleNamespace(command="unregister", yes=True, host=None, destination=None)
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
                modelctl.remove_models(
                    {"ollama_host": "127.0.0.1:11434"}, [model], args
                ),
                0,
            )
        text = capture.getvalue()
        self.assertIn("no manager-owned GGUF/state to retain", text)
        self.assertIn("multimodal source/projector blobs are Ollama-managed", text)

    def test_remove_deletes_local_gguf_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.gguf"
            output.write_bytes(b"weights")
            sidecar = modelctl.state_path(output)
            sidecar.write_text("{}", encoding="utf-8")
            model = {"id": "m", "name": "prod-test", "provider": "ollama", "from": str(output), "gguf": output.name}
            args = SimpleNamespace(command="remove", yes=True, host=None, destination=None)
            with (
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
                patch.object(modelctl, "run_as_ollama", return_value=SimpleNamespace(returncode=0)),
            ):
                self.assertEqual(modelctl.remove_models({"ollama_host": "127.0.0.1:11434"}, [model], args), 0)
            self.assertFalse(output.exists())
            self.assertFalse(sidecar.exists())

    def test_apply_reuses_verified_source_and_repairs_modelfile_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "model.gguf"
            source.write_bytes(b"weights")
            template = base / "prod-test.Modelfile"
            template.write_text(
                "# BC250 category: production\n"
                "# Ollama model: prod-test\n"
                "# Source: example/model @ latest\n"
                "# GGUF: model.gguf\n"
                f"FROM {source}\n"
                "PARAMETER num_gpu 99\n"
                "PARAMETER num_keep 256\n",
                encoding="utf-8",
            )
            model = {
                "id": "prod-test",
                "name": "prod-test",
                "category": "production",
                "provider": "ollama",
                "repository": "example/model",
                "revision": "latest",
                "gguf": "model.gguf",
                "sha256": "",
                "from": str(source),
                "template": template,
                "modelfile": template.name,
                "origin": "packaged",
            }
            sidecar = modelctl.state_path(source)
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(sidecar, model, modelctl.sha256(source), 1)
            runtime_root = base / "runtime"
            runtime_root.mkdir()
            runtime = runtime_root / template.name
            runtime.write_text("FROM /stale/model.gguf\n", encoding="utf-8")
            defaults = {
                "category": "production",
                "destination": str(base),
                "download_namespace": "production",
                "modelfile_destination": str(runtime_root),
                "ollama_host": "127.0.0.1:11434",
                "min_free_bytes": 0,
            }
            args = SimpleNamespace(
                command="apply",
                revision=None,
                sha256=None,
                destination=None,
                min_free_bytes=None,
                token_file=None,
                host=None,
                hf_session={"resolved": False, "token": ""},
            )
            with (
                patch.dict(os.environ, {}, clear=False),
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl, "command_path", side_effect=lambda name: f"/usr/bin/{name}"),
                patch.object(modelctl.os, "chown"),
                patch.object(modelctl.os, "chmod"),
                patch.object(modelctl, "registered_models", return_value={"prod-test"}),
                patch.object(
                    modelctl,
                    "run_as_ollama",
                    return_value=SimpleNamespace(returncode=0),
                ) as run,
            ):
                os.environ.pop("MODELFILE_DIR", None)
                os.environ.pop("DEST", None)
                self.assertEqual(modelctl.apply_models(defaults, [model], args), 0)

            self.assertEqual(
                runtime.read_text(encoding="utf-8"),
                modelctl.rendered_modelfile_content(template, model, source),
            )
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][1:3], ["create", "prod-test"])

    def test_refresh_forces_download_even_when_verified_source_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            destination = base / "models"
            destination.mkdir()
            output = destination / "model.gguf"
            output.write_bytes(b"old-weights")
            model = {
                "id": "download-test",
                "name": "download-test",
                "category": "mtp",
                "provider": "download-only",
                "repository": "example/model",
                "revision": "latest",
                "gguf": "model.gguf",
                "sha256": "",
            }
            sidecar = modelctl.state_path(output)
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(sidecar, model, modelctl.sha256(output), 1)
            defaults = {
                "category": "mtp",
                "destination": str(destination),
                "layout": "flat",
                "download_namespace": "test",
                "min_free_bytes": 0,
            }
            args = SimpleNamespace(
                command="refresh",
                revision=None,
                sha256=None,
                destination=None,
                min_free_bytes=0,
                token_file=None,
                host=None,
                hf_session={"resolved": True, "token": ""},
            )
            download_root = base / "downloads"
            calls = []

            def fake_run(command, environment, *, terminal=False):
                calls.append(command)
                staged = download_root / model["id"] / model["gguf"]
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(b"new-weights")
                return SimpleNamespace(returncode=0)

            with (
                patch.dict(
                    os.environ,
                    {"DOWNLOAD_DIR": str(download_root), "HF_HOME": str(base / "hf")},
                    clear=False,
                ),
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(1, 1)),
                patch.object(modelctl, "command_path", side_effect=lambda name: f"/usr/bin/{name}"),
                patch.object(modelctl.os, "chown"),
                patch.object(modelctl, "run_as_ollama", side_effect=fake_run),
            ):
                self.assertEqual(modelctl.apply_models(defaults, [model], args), 0)

            self.assertTrue(any(command[1:3] == ["download", "example/model"] for command in calls))
            self.assertEqual(output.read_bytes(), b"new-weights")

    def test_online_status_reports_update_without_mutating_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "model.gguf"
            output.write_bytes(b"weights")
            model = {
                "id": "prod-test",
                "name": "prod-test",
                "category": "production",
                "provider": "ollama",
                "repository": "example/model",
                "revision": "latest",
                "gguf": "model.gguf",
                "sha256": "",
                "from": str(output),
                "template": root / "prod-test.Modelfile",
                "modelfile": "prod-test.Modelfile",
                "origin": "packaged",
            }
            model["template"].write_text(
                "# BC250 category: production\n"
                "# Ollama model: prod-test\n"
                "# Source: example/model @ latest\n"
                "# GGUF: model.gguf\n"
                f"FROM {output}\n",
                encoding="utf-8",
            )
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(
                    modelctl.state_path(output), model, modelctl.sha256(output), 1
                )
            defaults = {
                "category": "production",
                "destination": str(root),
                "modelfile_destination": str(root / "runtime"),
                "ollama_host": "127.0.0.1:11434",
            }
            runtime = Path(defaults["modelfile_destination"]) / model["modelfile"]
            runtime.parent.mkdir()
            runtime.write_text(
                modelctl.rendered_modelfile_content(model["template"], model, output),
                encoding="utf-8",
            )
            before = output.read_bytes()
            with patch.object(modelctl, "remote_file_sha256", return_value="f" * 64):
                inspection = modelctl.inspect_model_state(
                    defaults,
                    model,
                    registrations={"prod-test"},
                    online=True,
                )
            self.assertEqual(inspection.remote_status, "update available")
            self.assertEqual(inspection.overall_status, "CURRENT")
            self.assertEqual(output.read_bytes(), before)

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

    def test_purge_retired_removes_only_catalogued_package_model(self) -> None:
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
                self.assertEqual(modelctl.purge_retired(yes=True), 0)
            self.assertFalse(source.exists())
            self.assertFalse(modelctl.state_path(source).exists())
            self.assertFalse(runtime.exists())


    def test_purge_retired_refuses_misplaced_registration(self) -> None:
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
                self.assertEqual(modelctl.purge_retired(yes=True), 2)
            self.assertTrue(source.exists())
            self.assertTrue(runtime.exists())



if __name__ == "__main__":
    unittest.main()

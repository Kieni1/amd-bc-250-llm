from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
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


    def test_modelfile_drift_distinguishes_proven_package_update_from_local_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.gguf"
            source.write_bytes(b"weights")
            old_template = root / "old.Modelfile"
            old_template.write_text(
                "# BC250 category: production\n"
                "# Ollama model: prod-test\n"
                "FROM __BC250_SOURCE__\n"
                "PARAMETER num_gpu 99\n"
                "PARAMETER num_keep 256\n"
                "PARAMETER temperature 0.7\n",
                encoding="utf-8",
            )
            new_template = root / "prod-test.Modelfile"
            new_template.write_text(
                old_template.read_text(encoding="utf-8").replace(
                    "PARAMETER temperature 0.7", "PARAMETER temperature 1.0"
                ),
                encoding="utf-8",
            )
            model = {
                "id": "prod-test", "name": "prod-test", "category": "production",
                "provider": "ollama", "repository": "example/model",
                "revision": "latest", "gguf": source.name, "sha256": "",
                "template": new_template, "modelfile": new_template.name,
                "origin": "packaged", "from": str(source),
            }
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(
                    modelctl.state_path(source), model, modelctl.sha256(source), 1
                )
            runtime_root = root / "runtime"
            runtime_root.mkdir()
            runtime = runtime_root / new_template.name
            runtime.write_text(
                modelctl.rendered_modelfile_content(old_template, model, source),
                encoding="utf-8",
            )
            provenance = root / "preupgrade.json"
            provenance.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "runtime_modelfiles": {
                            str(runtime): {
                                "model_id": "prod-test",
                                "category": "production",
                                "sha256": modelctl.sha256(runtime),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            defaults = {
                "destination": str(root),
                "modelfile_destination": str(runtime_root),
                "ollama_host": "127.0.0.1:11434",
            }
            with patch.dict(
                os.environ, {"BC250_PREUPGRADE_MODELFILE_STATE": str(provenance)}
            ):
                pending = modelctl.inspect_model_state(
                    defaults, model, registrations={"prod-test"}
                )
                self.assertEqual(pending.overall_status, "PACKAGE UPDATE PENDING")
                self.assertEqual(pending.modelfile_drift_kind, "package-update")
                self.assertEqual(
                    modelctl.compact_inspection_details(pending),
                    ["PACKAGE UPDATE PENDING"],
                )
                self.assertEqual(
                    modelctl.recommended_status_action(pending),
                    "sudo bc250 model apply production prod-test",
                )

                runtime.write_text("FROM /operator/modified.gguf\n", encoding="utf-8")
                local = modelctl.inspect_model_state(
                    defaults, model, registrations={"prod-test"}
                )
                self.assertEqual(local.overall_status, "DRIFT")
                self.assertEqual(local.modelfile_drift_kind, "local-or-unknown")
                self.assertIn(
                    "local/unknown Modelfile drift",
                    modelctl.compact_inspection_details(local),
                )

    def test_apply_migrates_legacy_pinned_state_without_refreshing_tracking_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.gguf"
            source.write_bytes(b"legacy-pinned-weights")
            digest = modelctl.sha256(source)
            stat_result = source.stat()
            old_revision = "6" * 40
            sidecar = modelctl.state_path(source)
            sidecar.write_text(
                json.dumps(
                    {
                        "schema": 3,
                        "repository": "example/model",
                        "revision": old_revision,
                        "gguf": source.name,
                        "sha256": digest,
                        "size": stat_result.st_size,
                        "mtime_ns": stat_result.st_mtime_ns,
                        "ctime_ns": stat_result.st_ctime_ns,
                    }
                ),
                encoding="utf-8",
            )
            template = root / "prod-test.Modelfile"
            template.write_text(
                "# BC250 category: production\n"
                "# Ollama model: prod-test\n"
                "FROM __BC250_SOURCE__\n"
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
                "gguf": source.name,
                "sha256": "",
                "from": str(source),
                "template": template,
                "modelfile": template.name,
                "origin": "packaged",
                "source_metadata": {"policy": "tracking"},
            }
            runtime_root = root / "runtime"
            runtime_root.mkdir()
            runtime = runtime_root / template.name
            runtime.write_text(
                modelctl.rendered_modelfile_content(template, model, source),
                encoding="utf-8",
            )
            defaults = {
                "category": "production",
                "destination": str(root),
                "download_namespace": "test",
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
                patch.dict(
                    os.environ,
                    {
                        "HF_HOME": str(root / "hf"),
                        "DOWNLOAD_DIR": str(root / "downloads"),
                    },
                    clear=False,
                ),
                patch.object(modelctl.os, "geteuid", return_value=0),
                patch.object(modelctl, "ollama_identity", return_value=(0, 0)),
                patch.object(modelctl, "command_path", side_effect=lambda name: f"/usr/bin/{name}"),
                patch.object(modelctl, "registered_models", return_value={"prod-test"}),
                patch.object(modelctl, "run_as_ollama") as run_as_ollama,
                patch.object(modelctl.os, "chown"),
                patch.object(modelctl.os, "chmod"),
            ):
                self.assertEqual(modelctl.apply_models(defaults, [model], args), 0)
            run_as_ollama.assert_not_called()
            self.assertEqual(source.read_bytes(), b"legacy-pinned-weights")
            migrated = json.loads(sidecar.read_text())
            self.assertEqual(migrated["schema"], 4)
            self.assertEqual(migrated["source_policy"], "tracking")
            self.assertEqual(migrated["configured_ref"], "latest")
            self.assertEqual(migrated["resolved_revision"], old_revision)
            self.assertEqual(migrated["acquired_sha256"], digest)

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

    def test_tracking_state_reuses_valid_artifact_across_configured_ref_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            digest = modelctl.sha256(output)
            stat = output.stat()
            acquired_revision = "1" * 40
            state = {
                **MODEL,
                "revision": acquired_revision,
                "schema": 3,
                "sha256": digest,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            tracking_model = {
                **MODEL,
                "source_metadata": {"policy": "tracking"},
            }
            status, detail, checksum = modelctl.inspect_local_source(
                state, tracking_model, output
            )
            self.assertEqual(status, "current")
            self.assertEqual(checksum, digest)
            self.assertIn("refresh required to advance", detail)

    def test_tracking_reuses_revision_but_rejects_source_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            digest = modelctl.sha256(output)
            stat = output.stat()
            state = {
                **MODEL,
                "revision": "2" * 40,
                "schema": 3,
                "sha256": digest,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            tracking = {**MODEL, "source_metadata": {"policy": "tracking"}}
            self.assertTrue(modelctl.state_matches(state, tracking, output))
            for changed in (
                {**tracking, "repository": "example/other"},
                {**tracking, "gguf": "other.gguf"},
            ):
                with self.subTest(changed=changed):
                    self.assertFalse(modelctl.state_matches(state, changed, output))

    def test_pinned_source_rejects_revision_or_checksum_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / MODEL["gguf"]
            output.write_bytes(b"weights")
            digest = modelctl.sha256(output)
            stat = output.stat()
            pinned_revision = "3" * 40
            state = {
                **MODEL,
                "revision": pinned_revision,
                "schema": 3,
                "sha256": digest,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            pinned = {
                **MODEL,
                "revision": pinned_revision,
                "sha256": digest,
                "source_metadata": {"policy": "pinned"},
            }
            self.assertTrue(modelctl.state_matches(state, pinned, output))
            self.assertFalse(
                modelctl.state_matches(
                    {**state, "revision": "4" * 40}, pinned, output
                )
            )
            self.assertFalse(
                modelctl.state_matches(
                    state, {**pinned, "sha256": "0" * 64}, output
                )
            )

    def test_invalid_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            path.write_text(json.dumps({"schema": 99}), encoding="utf-8")
            self.assertEqual(modelctl.load_state(path), {})

    def test_schema4_state_records_model_identity_and_source_policy(self) -> None:
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
            self.assertEqual(state["schema"], 4)
            self.assertEqual(state["model_name"], "exp-test-long-name")
            self.assertEqual(state["model_id"], "exp-test")
            self.assertEqual(state["category"], "experiments")
            self.assertEqual(state["source_policy"], "tracking")
            self.assertEqual(state["configured_ref"], "main")
            self.assertEqual(state["acquired_sha256"], state["sha256"])


    def test_schema4_migration_preserves_tracking_acquisition_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.gguf"
            output.write_bytes(b"weights")
            sidecar = modelctl.state_path(output)
            old_revision = "5" * 40
            sidecar.write_text(
                json.dumps(
                    {
                        "schema": 3,
                        "repository": "example/model",
                        "revision": old_revision,
                        "gguf": "model.gguf",
                        "sha256": modelctl.sha256(output),
                    }
                ),
                encoding="utf-8",
            )
            model = {
                "id": "exp-test",
                "name": "exp-test",
                "category": "experiments",
                "repository": "example/model",
                "revision": "latest",
                "gguf": "model.gguf",
                "sha256": "",
                "source_metadata": {"policy": "tracking"},
            }
            with patch.object(modelctl.os, "chown"), patch.object(modelctl.os, "chmod"):
                modelctl.write_state(
                    sidecar, model, modelctl.sha256(output), 1, preserve_acquisition=True
                )
            state = json.loads(sidecar.read_text())
            self.assertEqual(state["schema"], 4)
            self.assertEqual(state["configured_ref"], "latest")
            self.assertEqual(state["resolved_revision"], old_revision)
            self.assertEqual(state["revision"], old_revision)

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

    def test_current_schema4_fast_path_does_not_force_state_rewrite(self) -> None:
        source = (ROOT / "models/modelctl.py").read_text()
        self.assertIn('state.get("schema") != 4', source)
        self.assertNotIn('state.get("schema") != 2\n', source)

    def test_purge_retired_removes_only_catalogued_package_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_root = base / "gguf" / "experiments"
            runtime_root = base / "modelfiles" / "experiments"
            source = source_root / "retired.gguf"
            runtime = runtime_root / "retired.Modelfile"
            source.parent.mkdir(parents=True)
            runtime.parent.mkdir(parents=True)
            source.write_bytes(b"weights")
            modelctl.state_path(source).write_text("{}")
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
            source.parent.mkdir(parents=True)
            runtime.parent.mkdir(parents=True)
            source.write_bytes(b"weights")
            modelctl.state_path(source).write_text("{}")
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

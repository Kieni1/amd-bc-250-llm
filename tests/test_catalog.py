from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
MODELFILES = ROOT / "models/modelfiles"
sys.path.insert(0, str(ROOT / "models"))

import modelctl


def load(category: str) -> tuple[dict, list[dict]]:
    return modelctl.load_models(category, directories=[MODELFILES])


class ModelfileDiscoveryTests(unittest.TestCase):
    def test_every_packaged_modelfile_is_discovered_and_strictly_valid(self) -> None:
        models = modelctl.discover_models([MODELFILES])
        packaged = {path.stem for path in MODELFILES.glob("*.Modelfile")}
        self.assertEqual({model["name"] for model in models}, packaged)

    def test_current_model_set_and_dedicated_instances_are_preserved(self) -> None:
        expected_hosts = {
            "production": "127.0.0.1:11434",
            "experiments": "127.0.0.1:11434",
            "task": "127.0.0.1:11435",
            "agentic": "127.0.0.1:11436",
            "embedding": "127.0.0.1:11437",
        }
        for category, host in expected_hosts.items():
            with self.subTest(category=category):
                defaults, models = load(category)
                self.assertTrue(models, f"{category} catalog must not be empty")
                self.assertEqual(defaults["ollama_host"], host)
        required = {
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-gpt-oss20b-ggml-org-mxfp4",
            "prod-lfm25-8b-a1b-liquidai-q6-k",
            "prod-qwen35-9b-unsloth-q6-k",
        }
        self.assertTrue(required <= {model["name"] for model in load("production")[1]})

    def test_all_modelfiles_keep_required_bc250_gpu_and_context_settings(self) -> None:
        for path in MODELFILES.glob("*.Modelfile"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_gpu 99$", text, re.MULTILINE)), 1
                )
                if not path.name.startswith("embed-"):
                    self.assertEqual(
                        len(
                            re.findall(r"^PARAMETER num_keep 256$", text, re.MULTILINE)
                        ),
                        1,
                    )

    def test_experimental_ocr_models_use_ollama_managed_hf_sources(self) -> None:
        expected = {
            "exp-glm-ocr-ggml-q8-0",
            "exp-ovisocr2-abiray-q8-0",
        }
        models = {
            model["name"]: model for model in modelctl.discover_models([MODELFILES])
        }
        self.assertTrue(expected <= models.keys())
        self.assertTrue(
            all(models[name]["provider"] == "ollama-hf" for name in expected)
        )
        glm = (MODELFILES / "exp-glm-ocr-ggml-q8-0.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 16384", glm)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "exp-remote-mismatch.Modelfile"
            path.write_text(
                glm.replace("exp-glm-ocr-ggml-q8-0", "exp-remote-mismatch").replace(
                    "hf.co/ggml-org/GLM-OCR-GGUF", "hf.co/other/repository"
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                modelctl.ModelError, "must match Source metadata"
            ):
                modelctl.load_modelfile(path)

    def test_ornith_checksum_is_pinned_to_replacement_commit(self) -> None:
        text = (MODELFILES / "agentic-ornith15-9b-ornith-q5-k-m.Modelfile").read_text()
        self.assertIn("@ 87fcf5d7dbecb02941c0917a0e93619af2075b61", text)
        self.assertIn(
            "# SHA256: e4d9634a3b6546a5c00a8680568fe1125f6c98c704ee51ae52ba07650fb4247d",
            text,
        )

    def test_jina_embedding_uses_pooling_metadata_revision(self) -> None:
        text = (
            MODELFILES / "embed-jina-v5-small-retrieval-q4-k-m.Modelfile"
        ).read_text()
        self.assertIn("@ e9137ac0a9d41c851de69bea36babc029b7f5fc9", text)
        self.assertIn(
            "# SHA256: 9440cf89f3e8a7a31a42e11b87e106dd5b344af4e0e3b6b21a96136cc8686e21",
            text,
        )
        self.assertIn("pooling metadata", text)

    def test_new_compact_candidates_have_reviewed_sampling_and_roles(self) -> None:
        q38 = (MODELFILES / "exp-qwen38-4b-distill-empero-q6-k.Modelfile").read_text()
        self.assertIn("PARAMETER temperature 0.6", q38)
        self.assertIn("PARAMETER top_p 0.95", q38)
        self.assertIn("PARAMETER top_k 20", q38)
        lfm = (MODELFILES / "task-lfm25-2.6b-liquidai-q6-k.Modelfile").read_text()
        self.assertNotRegex(lfm, r"(?m)^SYSTEM\s")
        self.assertIn("PARAMETER num_ctx 4096", lfm)
        coder = (MODELFILES / "agentic-qwen25-coder7b-unsloth-q5-k-m.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 32768", coder)
        self.assertIn("PARAMETER temperature 0.7", coder)
        self.assertIn("PARAMETER top_p 0.8", coder)

    def test_coding_helper_defaults_to_measured_qwen25_coder(self) -> None:
        helper = (ROOT / "models/coding-agent/coding-agent.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "CODING_AGENT_MODEL:-agentic-qwen25-coder7b-unsloth-q5-k-m", helper
        )

    def test_recommended_tooling_models_are_discoverable(self) -> None:
        expected = {
            "embedding": "embed-jina-v5-small-retrieval-q4-k-m",
            "task": "task-gemma3-1b-unsloth-ud-q4-k-xl",
            "agentic": "agentic-qwen25-coder7b-unsloth-q5-k-m",
        }
        for category, name in expected.items():
            with self.subTest(category=category):
                _defaults, models = load(category)
                self.assertIn(name, {model["name"] for model in models})

    def test_example_is_ignored_and_operator_template_overrides_package(self) -> None:
        name = "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl.Modelfile"
        with tempfile.TemporaryDirectory() as temporary:
            operator = Path(temporary)
            shutil.copy2(MODELFILES / name, operator / name)
            models = modelctl.discover_models([MODELFILES, operator])
            selected = next(model for model in models if model["modelfile"] == name)
            self.assertEqual(selected["template"], operator / name)
            self.assertNotIn("MODEL-TEMPLATE", {model["name"] for model in models})

    def test_incomplete_modelfile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prod-invalid.Modelfile"
            path.write_text("PARAMETER num_gpu 99\nPARAMETER num_keep 256\n")
            with self.assertRaisesRegex(
                modelctl.ModelError, "missing category metadata"
            ):
                modelctl.load_modelfile(path)

    def test_duplicate_source_metadata_is_rejected(self) -> None:
        source = MODELFILES / "task-gemma3-1b-unsloth-ud-q4-k-xl.Modelfile"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / source.name
            text = source.read_text(encoding="utf-8")
            path.write_text(
                text.replace("# GGUF:", "# Source: owner/other @ main\n# GGUF:")
            )
            with self.assertRaisesRegex(modelctl.ModelError, "exactly one.*Source"):
                modelctl.load_modelfile(path)

    def test_production_qwen35_prompt_and_fablevibes_sampling_match_policy(
        self,
    ) -> None:
        qwen = (MODELFILES / "prod-qwen35-9b-unsloth-q6-k.Modelfile").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("experimental general assistant", qwen)
        self.assertIn("German-, French-, and English-speaking users", qwen)
        self.assertIn("PARAMETER temperature 0.7", qwen)
        self.assertIn("PARAMETER top_p 0.8", qwen)
        lfm = (MODELFILES / "prod-lfm25-8b-a1b-liquidai-q6-k.Modelfile").read_text(encoding="utf-8")
        self.assertIn("dedicated professional German↔French translator", lfm)
        self.assertIn("provides German text without another explicit task", lfm)
        self.assertNotIn("Do not assume that a German or French input should be translated", lfm)
        fable = (
            MODELFILES / "exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m.Modelfile"
        ).read_text(encoding="utf-8")
        self.assertIn("PARAMETER temperature 1.0", fable)
        self.assertIn("PARAMETER top_p 0.95", fable)
        self.assertIn("PARAMETER top_k 20", fable)

    def test_task_model_accepts_open_webui_integrated_task_prompts(self) -> None:
        source = MODELFILES / "task-gemma3-1b-unsloth-ud-q4-k-xl.Modelfile"
        text = source.read_text(encoding="utf-8")
        self.assertIn("PARAMETER num_predict 128", text)
        self.assertNotRegex(
            text, r"(?m)^SYSTEM\s", msg="task prompts must come from Open WebUI"
        )

    def test_ollama_toml_catalogs_are_not_part_of_the_source_tree(self) -> None:
        source_dir = ROOT / "models/sources"
        self.assertFalse(source_dir.exists() and any(source_dir.glob("*.toml")))

    def test_mtp_keeps_its_download_only_runtime_catalog(self) -> None:
        defaults, models = modelctl.load_mtp_catalog(ROOT / "models/mtp/models.toml")
        self.assertEqual(defaults["category"], "mtp")
        self.assertEqual(len(models), 2)
        self.assertTrue(all(model["provider"] == "download-only" for model in models))

    def test_granite42_context_is_explicitly_bounded_for_bc250(self) -> None:
        for name in (
            "exp-granite42-3b-ibm-q6-k.Modelfile",
            "exp-granite42-8b-ibm-q5-k-m.Modelfile",
        ):
            source = (ROOT / "models/modelfiles" / name).read_text(encoding="utf-8")
            self.assertIn("PARAMETER num_ctx 32768", source)
            self.assertIn("128K context", source)


class CategoryInterfaceTests(unittest.TestCase):
    def test_public_categories_are_canonical_and_include_all(self) -> None:
        self.assertEqual(
            modelctl.CATEGORIES,
            (
                "production",
                "experiments",
                "task",
                "agentic",
                "embedding",
                "mtp",
                "all",
            ),
        )
        for legacy in ("experimental", "tasker", "coding", "embedded", "embed"):
            self.assertNotIn(legacy, modelctl.CATEGORIES)

    def test_list_requires_sudo_to_avoid_protected_source_unknown_status(self) -> None:
        with (
            patch.object(modelctl.os, "geteuid", return_value=1000),
            self.assertRaisesRegex(modelctl.ModelError, "sudo bc250-model list"),
        ):
            modelctl.main(["list"])

    def test_cleanup_all_without_selection_selects_every_catalog_entry(self) -> None:
        catalogs = [
            (
                {"category": "production"},
                [{"category": "production", "id": "p", "name": "prod-p"}],
            ),
            (
                {"category": "mtp"},
                [
                    {
                        "category": "mtp",
                        "id": "m",
                        "name": "mtp-m",
                        "enabled": False,
                    }
                ],
            ),
        ]
        with (
            patch.object(modelctl.os, "geteuid", return_value=0),
            patch.object(modelctl, "load_all_catalogs", return_value=catalogs),
            patch.object(modelctl, "print_catalogs"),
            patch.object(modelctl, "run_all_catalog_operation", return_value=0) as run,
        ):
            self.assertEqual(
                modelctl.main(["cleanup", "all", "--keep-gguf", "--yes"]), 0
            )
        self.assertEqual(
            {(model["category"], model["id"]) for model in run.call_args.args[1]},
            {("production", "p"), ("mtp", "m")},
        )

    def test_all_cleanup_dispatches_each_selected_category(self) -> None:
        catalogs = [
            (
                {"category": "production"},
                [{"category": "production", "id": "p", "name": "prod-p"}],
            ),
            (
                {"category": "mtp"},
                [{"category": "mtp", "id": "m", "name": "mtp-m"}],
            ),
        ]
        selected = [catalogs[0][1][0], catalogs[1][1][0]]
        args = modelctl.argparse.Namespace(command="cleanup", yes=True)
        with patch.object(modelctl, "cleanup_models", return_value=0) as cleanup:
            self.assertEqual(
                modelctl.run_all_catalog_operation(catalogs, selected, args), 0
            )
        self.assertEqual(cleanup.call_count, 2)
        self.assertTrue(all(call.args[2].yes for call in cleanup.call_args_list))


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _defaults, cls.models = load("production")

    def test_selection_accepts_stable_ids_indices_and_ranges(self) -> None:
        first = self.models[0]
        self.assertEqual(modelctl.select_models(self.models, first["id"]), [first])
        self.assertEqual(
            modelctl.select_models(self.models, "0,2-3"),
            [self.models[0], *self.models[2:4]],
        )

    def test_all_selects_every_entry(self) -> None:
        self.assertEqual(modelctl.select_models(self.models, "all"), self.models)

    def test_catalog_indexes_are_global_and_selectable(self) -> None:
        all_models = modelctl.discover_models([MODELFILES])
        self.assertEqual(
            [model["index"] for model in all_models], list(range(len(all_models)))
        )
        _defaults, experiments = load("experiments")
        first_index = experiments[0]["index"]
        self.assertEqual(
            modelctl.select_models(experiments, str(first_index)), [experiments[0]]
        )

    def test_empty_and_invalid_selections_fail(self) -> None:
        for selection in ("", "999", "original-name"):
            with (
                self.subTest(selection=selection),
                self.assertRaises(modelctl.ModelError),
            ):
                modelctl.select_models(self.models, selection)


class StatusTests(unittest.TestCase):
    def test_combined_status_handles_protected_sources_and_unmanaged_models(
        self,
    ) -> None:
        class ProtectedPath:
            def stat(self):
                raise PermissionError

        registrations = {
            "127.0.0.1:11434": {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
                "unmanaged-test-model",
            },
            "127.0.0.1:11435": {"task-gemma3-1b-unsloth-ud-q4-k-xl"},
            "127.0.0.1:11436": {"prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl"},
            "127.0.0.1:11437": set(),
        }
        output = StringIO()
        with (
            patch.object(
                modelctl,
                "registered_models",
                side_effect=lambda host: registrations[host],
            ),
            patch.object(modelctl, "model_path", return_value=ProtectedPath()),
            redirect_stdout(output),
        ):
            modelctl.print_all_models([MODELFILES])

        text = output.getvalue()
        gemma = next(
            model
            for model in modelctl.discover_models([MODELFILES])
            if model["name"] == "exp-gemma4-12b-google-qat-q4-0"
        )
        self.assertIn(f"  {gemma['index']:2d}) exp-gemma4-12b-google-qat-q4-0", text)
        self.assertIn("downloaded, set up", text)
        self.assertIn("source Ollama-managed (main+projector), not set up", text)
        self.assertIn("unmanaged-test-model", text)
        self.assertIn("Modelfile missing", text)
        self.assertIn("Misplaced Ollama models", text)
        self.assertIn("prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl", text)
        self.assertIn("expected 127.0.0.1:11434", text)

    def test_ollama_hf_status_is_explicitly_managed(self) -> None:
        model = {
            "id": "m",
            "name": "exp-vision",
            "provider": "ollama-hf",
            "enabled": True,
        }
        output = StringIO()
        with redirect_stdout(output):
            modelctl.print_models({}, [model], registered=set())
        text = output.getvalue()
        self.assertIn("source Ollama-managed (main+projector), not set up", text)
        self.assertNotIn("download unknown", text)

    def test_retained_gguf_reports_downloaded_after_registration_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "model.gguf"
            output_path.write_bytes(b"weights")
            modelctl.state_path(output_path).write_text("{}", encoding="utf-8")
            model = {
                "id": "m",
                "name": "prod-test",
                "provider": "ollama",
                "from": str(output_path),
                "gguf": output_path.name,
                "enabled": True,
            }
            output = StringIO()
            with (
                patch.object(modelctl, "model_path", return_value=output_path),
                redirect_stdout(output),
            ):
                modelctl.print_models(
                    {"destination": temporary}, [model], registered=set()
                )
            text = output.getvalue()
            self.assertIn("downloaded, not set up", text)
            self.assertNotIn("download unknown", text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
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
        self.assertEqual(len(models), 26)

    def test_current_model_set_and_dedicated_instances_are_preserved(self) -> None:
        expected = {
            "production": (5, "127.0.0.1:11434"),
            "experiments": (16, "127.0.0.1:11434"),
            "task": (1, "127.0.0.1:11435"),
            "agentic": (2, "127.0.0.1:11436"),
            "embedding": (2, "127.0.0.1:11434"),
        }
        for category, (count, host) in expected.items():
            with self.subTest(category=category):
                defaults, models = load(category)
                self.assertEqual(len(models), count)
                self.assertEqual(defaults["ollama_host"], host)

    def test_all_modelfiles_keep_required_bc250_gpu_and_context_settings(self) -> None:
        for path in MODELFILES.glob("*.Modelfile"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_gpu 99$", text, re.MULTILINE)), 1
                )
                if not path.name.startswith("embed-"):
                    self.assertEqual(
                        len(re.findall(r"^PARAMETER num_keep 256$", text, re.MULTILINE)), 1
                    )

    def test_experimental_ocr_models_use_ollama_managed_hf_sources(self) -> None:
        expected = {
            "exp-glm-ocr-ggml-q8-0",
            "exp-dots-ocr-ggml-q8-0",
            "exp-ovisocr2-abiray-q8-0",
            "exp-chandra-ocr2-prithivmlmods-q4-k-m",
        }
        models = {model["name"]: model for model in modelctl.discover_models([MODELFILES])}
        self.assertTrue(expected <= models.keys())
        self.assertTrue(all(models[name]["provider"] == "ollama-hf" for name in expected))
        glm = (MODELFILES / "exp-glm-ocr-ggml-q8-0.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 16384", glm)
        chandra = (MODELFILES / "exp-chandra-ocr2-prithivmlmods-q4-k-m.Modelfile").read_text()
        self.assertIn("# GGUF: chandra-ocr-2.Q4_K_M.gguf", chandra)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "exp-remote-mismatch.Modelfile"
            path.write_text(
                glm.replace("exp-glm-ocr-ggml-q8-0", "exp-remote-mismatch")
                   .replace("hf.co/ggml-org/GLM-OCR-GGUF", "hf.co/other/repository"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(modelctl.ModelError, "must match Source metadata"):
                modelctl.load_modelfile(path)

    def test_ornith_checksum_is_pinned_to_replacement_commit(self) -> None:
        text = (MODELFILES / "agentic-ornith15-9b-ornith-q5-k-m.Modelfile").read_text()
        self.assertIn("@ 87fcf5d7dbecb02941c0917a0e93619af2075b61", text)
        self.assertIn("# SHA256: e4d9634a3b6546a5c00a8680568fe1125f6c98c704ee51ae52ba07650fb4247d", text)

    def test_jina_embedding_uses_pooling_metadata_revision(self) -> None:
        text = (MODELFILES / "embed-jina-v5-small-retrieval-q4-k-m.Modelfile").read_text()
        self.assertIn("@ e9137ac0a9d41c851de69bea36babc029b7f5fc9", text)
        self.assertIn("# SHA256: 9440cf89f3e8a7a31a42e11b87e106dd5b344af4e0e3b6b21a96136cc8686e21", text)
        self.assertIn("pooling metadata", text)

    def test_recommended_tooling_models_are_discoverable(self) -> None:
        expected = {
            "embedding": "embed-jina-v5-small-retrieval-q4-k-m",
            "task": "task-gemma3-1b-unsloth-ud-q4-k-xl",
            "agentic": "agentic-ornith15-9b-ornith-q5-k-m",
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
            self.assertNotIn(
                "MODEL-TEMPLATE", {model["name"] for model in models}
            )

    def test_incomplete_modelfile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prod-invalid.Modelfile"
            path.write_text("PARAMETER num_gpu 99\nPARAMETER num_keep 256\n")
            with self.assertRaisesRegex(modelctl.ModelError, "missing category metadata"):
                modelctl.load_modelfile(path)

    def test_duplicate_source_metadata_is_rejected(self) -> None:
        source = MODELFILES / "task-gemma3-1b-unsloth-ud-q4-k-xl.Modelfile"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / source.name
            text = source.read_text(encoding="utf-8")
            path.write_text(text.replace("# GGUF:", "# Source: owner/other @ main\n# GGUF:"))
            with self.assertRaisesRegex(modelctl.ModelError, "exactly one.*Source"):
                modelctl.load_modelfile(path)

    def test_production_qwen35_prompt_and_fablevibes_sampling_match_policy(self) -> None:
        qwen = (MODELFILES / "prod-qwen35-9b-unsloth-q6-k.Modelfile").read_text(encoding="utf-8")
        self.assertNotIn("experimental general assistant", qwen)
        self.assertIn("German-, French-, and English-speaking users", qwen)
        self.assertIn("PARAMETER temperature 0.7", qwen)
        self.assertIn("PARAMETER top_p 0.8", qwen)
        fable = (MODELFILES / "exp-qwen36-14b-a3b-tvall43-fablevibes-q4-k-m.Modelfile").read_text(encoding="utf-8")
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
        self.assertEqual([model["index"] for model in all_models], list(range(len(all_models))))
        _defaults, experiments = load("experiments")
        first_index = experiments[0]["index"]
        self.assertEqual(modelctl.select_models(experiments, str(first_index)), [experiments[0]])

    def test_empty_and_invalid_selections_fail(self) -> None:
        for selection in ("", "999", "original-name"):
            with self.subTest(selection=selection), self.assertRaises(modelctl.ModelError):
                modelctl.select_models(self.models, selection)


class StatusTests(unittest.TestCase):
    def test_combined_status_handles_protected_sources_and_unmanaged_models(self) -> None:
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
        }
        output = StringIO()
        with patch.object(
            modelctl, "registered_models", side_effect=lambda host: registrations[host]
        ), patch.object(modelctl, "model_path", return_value=ProtectedPath()), \
             redirect_stdout(output):
            modelctl.print_all_models([MODELFILES])

        text = output.getvalue()
        gemma = next(
            model for model in modelctl.discover_models([MODELFILES])
            if model["name"] == "exp-gemma4-12b-google-qat-q4-0"
        )
        self.assertIn(f"  {gemma['index']:2d}) exp-gemma4-12b-google-qat-q4-0", text)
        self.assertIn("downloaded, set up", text)
        self.assertIn("download unknown, not set up", text)
        self.assertIn("unmanaged-test-model", text)
        self.assertIn("Modelfile missing", text)
        self.assertIn("Misplaced Ollama models", text)
        self.assertIn("prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl", text)
        self.assertIn("expected 127.0.0.1:11434", text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest


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
        self.assertEqual(len(models), 19)

    def test_current_model_set_and_dedicated_instances_are_preserved(self) -> None:
        expected = {
            "production": (6, "127.0.0.1:11434"),
            "experiments": (10, "127.0.0.1:11434"),
            "task": (1, "127.0.0.1:11435"),
            "agentic": (2, "127.0.0.1:11436"),
        }
        for category, (count, host) in expected.items():
            with self.subTest(category=category):
                defaults, models = load(category)
                self.assertEqual(len(models), count)
                self.assertEqual(defaults["ollama_host"], host)

    def test_all_chat_modelfiles_keep_bc250_gpu_and_context_settings(self) -> None:
        for path in MODELFILES.glob("*.Modelfile"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_gpu 99$", text, re.MULTILINE)), 1
                )
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_keep 256$", text, re.MULTILINE)), 1
                )

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

    def test_empty_and_invalid_selections_fail(self) -> None:
        for selection in ("", "999", "original-name"):
            with self.subTest(selection=selection), self.assertRaises(modelctl.ModelError):
                modelctl.select_models(self.models, selection)


if __name__ == "__main__":
    unittest.main()

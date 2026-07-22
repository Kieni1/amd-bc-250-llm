from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))

import modelctl


def catalog_path(category: str) -> Path:
    if category == "mtp":
        return ROOT / "models/mtp/models.toml"
    return ROOT / f"models/sources/{category}.toml"


def load(category: str) -> tuple[dict, list[dict]]:
    return modelctl.load_catalog(
        catalog_path(category), category, ROOT / "models/modelfiles"
    )


class CatalogTests(unittest.TestCase):
    def test_every_catalog_and_modelfile_is_strictly_valid(self) -> None:
        referenced: set[str] = set()
        for category in modelctl.CATEGORIES:
            _defaults, models = load(category)
            current = {
                model["modelfile"]
                for model in models
                if model["provider"] == "ollama"
            }
            self.assertFalse(referenced & current)
            referenced.update(current)
        packaged = {
            path.name for path in (ROOT / "models/modelfiles").glob("*.Modelfile")
        }
        self.assertEqual(packaged, referenced)

    def test_all_chat_modelfiles_keep_bc250_gpu_and_context_settings(self) -> None:
        for path in (ROOT / "models/modelfiles").glob("*.Modelfile"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_gpu 99$", text, re.MULTILINE)), 1
                )
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_keep 256$", text, re.MULTILINE)), 1
                )

    def test_production_and_experiments_remain_disabled_by_default(self) -> None:
        for category in ("production", "experiments"):
            _defaults, models = load(category)
            self.assertTrue(models)
            self.assertFalse(any(model["enabled"] for model in models))

    def test_task_and_agent_catalogs_keep_their_dedicated_instances(self) -> None:
        task, _models = load("task")
        coding, _models = load("coding")
        self.assertEqual(task["ollama_host"], "127.0.0.1:11435")
        self.assertEqual(coding["ollama_host"], "127.0.0.1:11436")


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _defaults, cls.models = load("production")

    def test_selection_accepts_stable_ids_names_indices_and_ranges(self) -> None:
        first = self.models[0]
        self.assertEqual(modelctl.select_models(self.models, first["id"]), [first])
        self.assertEqual(modelctl.select_models(self.models, first["name"]), [first])
        self.assertEqual(
            modelctl.select_models(self.models, "0,2-3"),
            [self.models[0], *self.models[2:4]],
        )

    def test_all_and_empty_select_every_entry(self) -> None:
        self.assertEqual(modelctl.select_models(self.models, "all"), self.models)
        self.assertEqual(modelctl.select_models(self.models, ""), self.models)

    def test_invalid_selection_fails_instead_of_changing_scope(self) -> None:
        with self.assertRaises(modelctl.ModelError):
            modelctl.select_models(self.models, "999")
        with self.assertRaises(modelctl.ModelError):
            modelctl.select_models(self.models, "original-name")


if __name__ == "__main__":
    unittest.main()

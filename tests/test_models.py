from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def load_modelctl():
    path = ROOT / "models/modelctl.py"
    spec = importlib.util.spec_from_file_location("bc250_modelctl_models_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ModelCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.modelctl = load_modelctl()

    def test_active_categories_have_valid_models(self) -> None:
        seen: set[str] = set()
        for category in self.modelctl.CATEGORY_DEFAULTS:
            _defaults, models = self.modelctl.load_models(category, directories=[ROOT / "models/modelfiles"])
            self.assertTrue(models, category)
            for model in models:
                name = str(model["name"])
                self.assertNotIn(name, seen)
                seen.add(name)
                digest = str(model.get("sha256") or "")
                if digest:
                    self.assertRegex(digest, r"^[0-9a-f]{64}$")
                self.assertTrue((ROOT / "models/modelfiles" / str(model["modelfile"])).is_file())

    def test_model_list_is_read_only_and_available(self) -> None:
        result = subprocess.run(
            ["python3", "models/modelctl.py", "list"], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Production models", result.stdout)
        self.assertIn("exp-", result.stdout)

    def test_profile_and_retired_metadata_are_well_formed(self) -> None:
        profiles = json.loads((ROOT / "models/model-profiles.json").read_text(encoding="utf-8"))
        retired = json.loads((ROOT / "models/retired-models.json").read_text(encoding="utf-8"))
        self.assertIsInstance(profiles, dict)
        self.assertIsInstance(retired, (dict, list))

    def test_mtp_catalog_is_parseable(self) -> None:
        with (ROOT / "models/mtp/models.toml").open("rb") as stream:
            data = tomllib.load(stream)
        self.assertIsInstance(data, dict)
        self.assertTrue(data)

    def test_modelfiles_have_from_directive(self) -> None:
        for path in sorted((ROOT / "models/modelfiles").glob("*.Modelfile")):
            if path.name.startswith("MODEL-TEMPLATE"):
                continue
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^FROM\s+\S+")


if __name__ == "__main__":
    unittest.main()

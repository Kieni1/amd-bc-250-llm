from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_help(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv), cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    )


class CoreContractTests(unittest.TestCase):
    def test_release_identity_is_consistent(self) -> None:
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertEqual(contract["package"]["version"], version)
        self.assertRegex(spec, rf"(?m)^Version:\s+{re.escape(version)}$")
        self.assertRegex(spec, rf"(?m)^Release:\s+{re.escape(contract['package']['rpm_release'])}%")

    def test_runtime_contract_has_required_pins(self) -> None:
        values: dict[str, str] = {}
        for raw in (ROOT / "config/runtime.env").read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        for key in (
            "BC250_OLLAMA_VERSION", "BC250_OLLAMA_PAYLOAD_SHA256",
            "BC250_OPEN_WEBUI_VERSION", "BC250_OPEN_WEBUI_IMAGE_DIGEST",
            "BC250_TIKA_VERSION", "BC250_TIKA_IMAGE_DIGEST",
            "BC250_GOVERNOR_VERSION", "BC250_GOVERNOR_COMMIT",
        ):
            self.assertTrue(values.get(key), key)

    def test_core_cli_help_is_non_mutating(self) -> None:
        commands = [
            ("bash", "packaging/bc250", "--help"),
            ("bash", "cmd/system/install.sh", "--help"),
            ("python3", "models/modelctl.py", "--help"),
            ("bash", "cmd/monitoring/status.sh", "--help"),
            ("python3", "cmd/monitoring/health.py", "--help"),
            ("bash", "cmd/monitoring/verify-server.sh", "--help"),
            ("python3", "cmd/monitoring/version.py", "--help"),
            ("python3", "cmd/system/storage.py", "--help"),
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                result = run_help(*argv)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("Usage" if argv[1].endswith(".sh") or argv[1] == "packaging/bc250" else "usage:", result.stdout)

    def test_dispatcher_exposes_only_current_core_names(self) -> None:
        text = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        routes = set(re.findall(r'^  "([a-z0-9-]+)\|', text, flags=re.MULTILINE))
        required = {"install", "status", "health", "verify", "version", "model", "storage", "reset"}
        self.assertTrue(required <= routes)
        self.assertNotIn("gfx" + "1013", text.lower())

    def test_install_manifest_core_sources_exist(self) -> None:
        manifest = ROOT / "packaging/install-manifest.tsv"
        required_destinations = {
            "{bindir}/bc250", "{libexec}/install.sh", "{libexec}/status.sh",
            "{libexec}/health.py", "{libexec}/verify.sh", "{libexec}/version.py",
            "{libexec}/modelctl", "{share}/VERSION", "{share}/runtime.env",
        }
        destinations: set[str] = set()
        for raw in manifest.read_text(encoding="utf-8").splitlines():
            if not raw or raw.startswith("#"):
                continue
            kind, _mode, source, destination = raw.split("\t")
            destinations.add(destination)
            if (
                kind in {"file", "config"}
                and "*" not in source
                and source != "-"
                and not source.startswith(("governor-src/", "live-manager-src/"))
            ):
                self.assertTrue((ROOT / source).is_file(), source)
        self.assertTrue(required_destinations <= destinations)
        self.assertNotIn("gfx" + "1013", manifest.read_text(encoding="utf-8").lower())

    def test_active_model_catalog_loads_and_is_unique(self) -> None:
        modelctl = load_module("bc250_modelctl_core_tests", ROOT / "models/modelctl.py")
        names: list[str] = []
        for category in modelctl.CATEGORY_DEFAULTS:
            _defaults, models = modelctl.load_models(category, directories=[ROOT / "models/modelfiles"])
            self.assertTrue(models, category)
            names.extend(str(model["name"]) for model in models)
        self.assertEqual(len(names), len(set(names)))

    def test_primary_json_and_toml_configs_parse(self) -> None:
        for relative in (
            "config/openwebui/desired-state.json", "config/openwebui/functions.json",
            "config/openwebui/models.json", "models/model-catalog.json", "models/model-profiles.json", "models/retired-models.json",
        ):
            json.loads((ROOT / relative).read_text(encoding="utf-8"))
        with (ROOT / "models/mtp/models.toml").open("rb") as stream:
            tomllib.load(stream)


if __name__ == "__main__":
    unittest.main()

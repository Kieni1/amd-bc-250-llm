"""Cross-file agreement checks that execute the real definitions (T5.6, T5.7)."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_contract():
    spec = importlib.util.spec_from_file_location("bc250_contract_t56", ROOT / "cmd/model_contract.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def maintenance_timers() -> list[str]:
    script = ROOT / "cmd/maintenance/maintenance.sh"
    definitions = "\n".join(
        line for line in script.read_text(encoding="utf-8").splitlines()
        if re.match(r"^(BACKUP|OPTIONAL|ALL)_TIMERS=", line)
    )
    result = subprocess.run(["bash", "-c", definitions + '\nprintf "%s\\n" "${ALL_TIMERS[@]}"'],
                            capture_output=True, text=True, check=True)
    return result.stdout.split()


def installer_verify_timers() -> list[str]:
    source = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
    body = source[source.index("verify_local_maintenance_setup() {"):]
    match = re.search(r"for unit in ((?:[^;]|\\\n)+?); do", body)
    assert match, "installer timer verification loop not found"
    return match.group(1).replace("\\\n", " ").split()


class UnitListAgreement(unittest.TestCase):
    """T5.7: one maintenance timer set across maintenance, installer, spec and preset."""

    def test_maintenance_timer_lists_agree_everywhere(self) -> None:
        timers = maintenance_timers()
        self.assertEqual(len(timers), len(set(timers)))
        self.assertIn("owui-backup-documents.timer", timers)
        self.assertEqual(sorted(installer_verify_timers()), sorted(timers))

        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        units = re.search(r"^%global bc250_units (.+)$", spec, re.MULTILINE).group(1).split()
        self.assertEqual(sorted(u for u in units if u.endswith(".timer")), sorted(timers))

        preset = (ROOT / "packaging/90-bc250-llm-server.preset").read_text(encoding="utf-8")
        preset_units = {line.split()[1]: line.split()[0] for line in preset.splitlines() if line.strip()}
        self.assertEqual(sorted(set(units)), sorted(preset_units))
        for timer in timers:
            self.assertEqual(preset_units[timer], "disable", f"{timer} must stay opt-in")

        installed_units = set()
        for line in (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) == 4 and fields[0] == "file" and fields[3].startswith("{unitdir}/"):
                installed_units |= {path.name for path in ROOT.glob(fields[2])}
        for timer in timers:
            self.assertIn(timer, installed_units, f"{timer} is not installed by the manifest")
            service = timer.removesuffix(".timer") + ".service"
            unit_text = next(ROOT.glob(f"**/{timer}")).read_text(encoding="utf-8")
            activated = re.search(r"^Unit=(\S+)", unit_text, re.MULTILINE)
            target = activated.group(1) if activated else service
            template = re.fullmatch(r"(.+@)(.+)(\.service)", target)
            if template:
                target = template.group(1) + template.group(3)
                self.assertTrue((ROOT / "cmd/maintenance" / f"{template.group(2)}.sh").is_file(), timer)
            self.assertIn(target, installed_units, timer)


@unittest.skipUnless(shutil.which("jq"), "jq is required to execute the installer expressions")
class InstallerBaselineMatchesContract(unittest.TestCase):
    """T5.6: the installer's jq derivation equals required_baseline_model_ids()."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = _load_contract()
        source = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        block = source[source.index('required_csv="$({'):]
        cls.roles_jq, cls.desired_jq = re.findall(r"jq -r '([^']+)'", block)[:2]

    def installer_set(self, roles: Path, desired: Path) -> frozenset[str]:
        lines = []
        for expression, document in ((self.roles_jq, roles), (self.desired_jq, desired)):
            out = subprocess.run(["jq", "-r", expression, str(document)],
                                 capture_output=True, text=True, check=True).stdout
            lines += [line for line in out.splitlines() if line]
        return frozenset(lines)

    def test_packaged_documents(self) -> None:
        roles = ROOT / "config/openwebui/models.json"
        desired = ROOT / "config/openwebui/desired-state.json"
        expected = self.contract.required_baseline_model_ids(roles_path=roles, desired_path=desired)
        self.assertTrue(expected)
        self.assertEqual(self.installer_set(roles, desired), expected)

    def test_edge_cases(self) -> None:
        roles_doc = {"models": [
            {"id": "a", "is_active": True, "base_model_id": "main-model:latest"},
            {"id": "b", "is_active": False, "base_model_id": "inactive-model"},
            {"id": "c", "is_active": True, "base_model_id": "main-model"},
            {"id": "d", "is_active": True},
            {"id": "e", "is_active": "true", "base_model_id": "string-true"},
        ]}
        desired_doc = {"task": {"TASK_MODEL": "task-model:latest"},
                       "embedding": {"RAG_EMBEDDING_MODEL": "embed-model"}}
        with tempfile.TemporaryDirectory() as temporary:
            roles = Path(temporary) / "models.json"
            desired = Path(temporary) / "desired.json"
            roles.write_text(json.dumps(roles_doc), encoding="utf-8")
            desired.write_text(json.dumps(desired_doc), encoding="utf-8")
            expected = self.contract.required_baseline_model_ids(roles_path=roles, desired_path=desired)
            self.assertEqual(expected, {"main-model", "task-model", "embed-model"})
            self.assertEqual(self.installer_set(roles, desired), expected)


if __name__ == "__main__":
    unittest.main()

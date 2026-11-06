"""Regression contracts for 0.20.0-5 OPEN WIP MW/RT repairs."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module_at(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


modelctl = module_at("bc250_mw_modelctl", "models/modelctl.py")
contract = modelctl._SHARED_MODEL_CONTRACT


class ModelWorkflows(unittest.TestCase):
    def test_mw4_experiment_selected_by_active_role_is_required(self):
        model = {
            "id": "exp-required-role", "name": "exp-required-role",
            "category": "experiments", "provider": "ollama", "gguf": "role.gguf",
        }
        with (
            patch.object(modelctl, "inspect_local_source", return_value=("missing", "missing", "")),
            patch.object(modelctl, "runtime_modelfile_path", return_value=Path("/tmp/role.Modelfile")),
            patch.object(modelctl, "inspect_runtime_modelfile", return_value=("missing", "missing")),
            patch.object(modelctl, "required_baseline_model_ids", return_value=frozenset({model["id"]})),
        ):
            result = modelctl.inspect_model_state(
                {"destination": "/unused", "modelfile_destination": "/unused"},
                model, registrations=set(), destination="/tmp",
            )
        self.assertEqual(result.overall_status, "MISSING")

    # The installer/contract equivalence is executed with jq in
    # tests/test_unit_lists_02005.py::InstallerBaselineMatchesContract.

    def test_mw3_forbidden_policy_must_not_be_ordinary_visible(self):
        profiles = {
            "exp-private": {"owui_testing_exposure": "forbidden"},
            "exp-testing": {"owui_testing_exposure": "testing"},
        }
        with self.assertRaisesRegex(contract.ModelContractError, "forbidden profile"):
            contract.validate_testing_visibility_policies(
                {"exp-private:latest": {"ordinary_user_visible": True}}, profiles
            )
        with self.assertRaisesRegex(contract.ModelContractError, "explicit"):
            contract.validate_testing_visibility_policies(
                {"exp-testing": {"ordinary_user_visible": False}}, profiles
            )
        contract.validate_testing_visibility_policies(
            {"exp-testing": {"ordinary_user_visible": False, "description": "Admin-only comparison"}}, profiles
        )
        contract.validate_testing_visibility_policies(
            {"exp-testing": {"ordinary_user_visible": True}}, profiles
        )

    def test_mw1_reports_only_model_owned_orphans_and_does_not_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = modelctl.CATEGORY_DEFAULTS
            modelctl.CATEGORY_DEFAULTS = {"experiments": {"destination": str(root)}}
            try:
                active = root / "new.gguf"
                orphan = root / "old.gguf"
                orphan.write_bytes(b"old")
                other = root / "other.gguf"
                other.write_bytes(b"other")
                for path, identity in [(orphan, "exp-same"), (other, "exp-other")]:
                    modelctl.state_path(path).write_text(json.dumps({
                        "schema": 4, "model_id": identity,
                        "model_name": identity, "gguf": path.name,
                    }))
                self.assertEqual(
                    modelctl.orphaned_manager_sources(
                        {"provider": "ollama", "id": "exp-same", "name": "exp-same"}, active
                    ), [orphan]
                )
                self.assertTrue(orphan.exists())
                self.assertTrue(modelctl.state_path(orphan).exists())
            finally:
                modelctl.CATEGORY_DEFAULTS = original

    def test_mw5_agent_exit_notice_before_normal_transition(self):
        from types import SimpleNamespace
        with (
            patch.object(modelctl.shutil, "which", side_effect=lambda name: "/usr/bin/" + name),
            patch.object(modelctl.subprocess, "run", side_effect=[
                SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)
            ]) as runner,
            patch.dict(os.environ, {"BC250_DISPATCHER": "/usr/bin/bc250"}),
        ):
            import contextlib
            import io
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                modelctl.set_appliance_mode("normal")
            self.assertIn("Agent mode active", stderr.getvalue())
            self.assertEqual(runner.call_args_list[0].args[0][:2], ["systemctl", "is-active"])
            self.assertEqual(runner.call_args_list[1].args[0][-2:], ["agent", "leave"])

    def test_mw7_openwebui_apply_hint_is_documented(self):
        source = (ROOT / "models/modelctl.py").read_text()
        self.assertIn("NEXT: run `sudo bc250 advanced openwebui apply`", source)

    def test_mw6_required_model_removal_warns_before_confirmation(self):
        model = {"provider": "ollama", "id": "required", "name": "required", "gguf": "required.gguf", "from": "/tmp/models/required.gguf"}
        defaults = {"destination": "/tmp/models", "modelfile_destination": "/tmp/modelfiles", "ollama_host": "127.0.0.1:11434"}
        import contextlib
        import io
        with (
            patch.object(modelctl, "required_baseline_model_ids", return_value=frozenset({"required"})),
            contextlib.redirect_stdout(io.StringIO()) as captured,
        ):
            modelctl.show_removal_plan([(defaults, [model])], type("Args", (), {"command": "unregister", "host": None, "destination": None})())
        self.assertIn("WARNING: required by an active role", captured.getvalue())

    def test_mw8_generic_env_no_longer_redirects_model_sources(self):
        with patch.dict(os.environ, {"MODELFILE_SOURCE_DIR": "/evil", "DEST": "/evil", "MODELFILE_DIR": "/evil"}):
            self.assertNotIn("/evil", [str(path) for path in modelctl.model_directories()])
            self.assertEqual(modelctl.model_path({"destination": "/good"}, {"provider": "ollama", "gguf": "x.gguf", "from": "/good/x.gguf"}), Path("/good/x.gguf"))
        source = (ROOT / "models/modelctl.py").read_text()
        self.assertNotIn('os.environ.get("DEST")', source)
        self.assertNotIn('os.environ["SOURCE_FILE"]', source)


class RuntimeTopology(unittest.TestCase):
    def test_rt1_warmup_never_pulls_main_lane(self):
        unit = (ROOT / "config/systemd/maintenance/owui-warmup.service").read_text()
        self.assertIn("After=network-online.target ollama.service", unit)
        self.assertNotIn("Wants=network-online.target ollama.service", unit)
        with tempfile.TemporaryDirectory() as directory:
            ctl = Path(directory) / "systemctl"
            ctl.write_text("#!/usr/bin/env bash\n[[ \"$3\" == ollama-agent.service ]]\n")
            ctl.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "cmd/maintenance/warmup.sh")],
                env=os.environ | {"PATH": directory + ":" + os.environ["PATH"]},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SKIP: warmup suppressed in Agent mode", result.stdout)

    def test_rt2_rt3_balanced_is_reset_without_activating_inactive_lane(self):
        source = (ROOT / "cmd/system/ollama-profile.sh").read_text()
        self.assertIn("balanced|reset) reset_profile", source)
        self.assertIn("systemctl try-restart ollama.service", source)
        self.assertNotIn("systemctl restart ollama.service", source)
        self.assertFalse((ROOT / "config/ollama-profiles/max-context.conf").exists())

    def test_rt4_safe_power_defers_agent_and_protects_mtp(self):
        source = (ROOT / "cmd/maintenance/safe-power.sh").read_text()
        self.assertIn("3000 8090 11434", source)
        self.assertIn('SAFE_POWER_PORTS="$SAFE_POWER_PORTS 8090"', source)
        self.assertIn("systemctl is-active --quiet ollama-agent.service", source)
        with tempfile.TemporaryDirectory() as directory:
            for name, content in {
                "systemctl": '#!/usr/bin/env bash\n[[ "$1 $2 $3" == "is-active --quiet ollama-agent.service" ]]\n',
                "logger": '#!/usr/bin/env bash\nexit 0\n',
                "ss": '#!/usr/bin/env bash\nexit 66\n',
            }.items():
                target = Path(directory) / name
                target.write_text(content)
                target.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "cmd/maintenance/safe-power.sh")],
                env=os.environ | {"PATH": directory + ":" + os.environ["PATH"]},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("exclusive Agent mode is active", result.stdout)

    def test_mc1_unsafe_prune_cannot_issue_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "curl"
            calls = Path(directory) / "calls"
            fake.write_text(textwrap.dedent('''\
                #!/usr/bin/env bash
                printf '%s\\n' "$*" >> "$CALLS"
                if [[ "$*" == *" -X DELETE "* ]]; then exit 77; fi
                printf '%s\\n' '[{"id":"managed-rag-file","created_at":1700000000,"meta":{"size":123}}]'
            '''))
            fake.chmod(0o755)
            env = os.environ | {
                "PATH": directory + ":" + os.environ["PATH"], "CALLS": str(calls),
                "OWUI_API_KEY": "fake", "DRY_RUN": "0",
                "MAX_AGE_DAYS": "1", "MAX_TOTAL_GB": "0",
                "OWUI_API_KEY_FILE": str(Path(directory) / "missing"),
            }
            result = subprocess.run(["bash", str(ROOT / "cmd/maintenance/prune-uploads.sh")],
                                    env=env, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Knowledge-linked", result.stdout)
            self.assertNotIn("-X DELETE", calls.read_text())


if __name__ == "__main__":
    unittest.main()

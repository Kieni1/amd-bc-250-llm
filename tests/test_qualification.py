from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "cmd/qualification"
if str(QUALIFICATION) not in sys.path:
    sys.path.insert(0, str(QUALIFICATION))

import resilience_common as common
import resilience_manager as manager_module


def command_result(argv: list[str], rc: int = 0, stdout: str = "", stderr: str = "") -> common.CommandResult:
    return common.CommandResult(tuple(argv), rc, stdout, stderr)


class QualificationTests(unittest.TestCase):
    def test_tika_gate_marker_is_extraction_safe_and_reports_observed_text(self) -> None:
        source = (QUALIFICATION / "package_gate_capture.py").read_text(encoding="utf-8")
        self.assertIn('marker = "BC250TIKA410PACKAGEGATE7D6D6F"', source)
        self.assertNotIn("BC250_TIKA_410_PACKAGE_GATE_7D6D6F", source)
        self.assertIn("observed=extraction.stdout.strip()", source)

    def test_managed_swap_refresh_only_touches_package_swap_and_restores_priority(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> common.CommandResult:
            calls.append(argv)
            if argv[0] == "swapon" and "--show=NAME,PRIO" in argv:
                return command_result(
                    argv,
                    stdout=(
                        "/dev/zram0 100\n"
                        "/var/lib/operator/custom.swap 50\n"
                        f"{common.MANAGED_SWAP} 10\n"
                    ),
                )
            return command_result(argv)

        result = common.refresh_managed_swap(runner=runner)
        self.assertEqual(result.status, "PASS")
        self.assertTrue(result.restored)
        self.assertEqual(result.priority, 10)
        self.assertIn(["swapoff", str(common.MANAGED_SWAP)], calls)
        self.assertIn(["swapon", "--priority", "10", str(common.MANAGED_SWAP)], calls)
        self.assertNotIn(["swapoff", "-a"], calls)
        self.assertFalse(any(call[:2] == ["swapoff", "/dev/zram0"] for call in calls))
        self.assertFalse(any("/var/lib/operator/custom.swap" in call for call in calls if call[0] == "swapoff"))

    def test_managed_swap_restoration_failure_stays_visible(self) -> None:
        def runner(argv: list[str]) -> common.CommandResult:
            if argv[0] == "swapon" and "--show=NAME,PRIO" in argv:
                return command_result(argv, stdout=f"{common.MANAGED_SWAP} 17\n")
            if argv[0] == "swapoff":
                return command_result(argv)
            return command_result(argv, rc=1, stderr="restore failed")

        with self.assertRaises(common.QualificationError) as caught:
            common.refresh_managed_swap(runner=runner)
        self.assertEqual(caught.exception.result, "HARNESS")
        self.assertIn("restoration failed", str(caught.exception))

    def test_managed_swap_refresh_ignores_non_package_swaps_when_managed_inactive(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> common.CommandResult:
            calls.append(argv)
            return command_result(argv, stdout="/dev/zram0 100\n/var/lib/operator/custom.swap 20\n")

        result = common.refresh_managed_swap(runner=runner)
        self.assertEqual(result.status, "PASS")
        self.assertFalse(any(call[0] == "swapoff" for call in calls))

    def test_normal_topology_accepts_inactive_agent(self) -> None:
        original = common.service_active_state
        states = {
            "ollama.service": "active",
            "ollama-task.service": "active",
            "ollama-embedding.service": "active",
            "ollama-agent.service": "inactive",
        }
        common.service_active_state = states.__getitem__
        try:
            healthy, observed = common.normal_topology_status()
        finally:
            common.service_active_state = original
        self.assertTrue(healthy)
        self.assertEqual(observed["ollama-agent.service"], "inactive")

    def test_closed_package_gate_manifest_rejects_unlisted_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = root / "gate.json"
            gate.write_text(
                json.dumps({"schema": common.PACKAGE_GATE_SCHEMA, "result": "PASS"}) + "\n",
                encoding="utf-8",
            )
            evidence = root / "evidence.txt"
            evidence.write_text("ok\n", encoding="utf-8")
            lines = []
            for path in (gate, evidence):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                lines.append(f"{digest}  {path.name}")
            (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
            validation = common.validate_package_gate(root)
            self.assertEqual(validation.gate["result"], "PASS")
            (root / "unexpected.txt").write_text("gap\n", encoding="utf-8")
            with self.assertRaises(common.QualificationError) as caught:
                common.validate_package_gate(root)
            self.assertEqual(caught.exception.result, "INCOMPLETE")

    def test_manager_missing_common_module_is_clean_rc2_without_traceback(self) -> None:
        source = QUALIFICATION / "resilience_manager.py"
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "resilience_manager.py"
            target.write_bytes(source.read_bytes())
            completed = subprocess.run(
                [sys.executable, str(target), "--help"],
                cwd=temporary,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("common module unavailable", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_plan_requires_exact_bounded_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            payload = {
                "schema": common.RESILIENCE_PLAN_SCHEMA,
                "lanes": {str(n): ["/bin/true"] for n in range(20, 27)},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = manager_module.load_plan(path)
            self.assertEqual(set(loaded["lanes"]), {str(n) for n in range(20, 27)})
            payload["lanes"]["27"] = ["/bin/true"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(common.QualificationError):
                manager_module.load_plan(path)

    def test_missing_lane_executable_is_controlled_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            (campaign / "evidence").mkdir()
            plan = {
                "schema": common.RESILIENCE_PLAN_SCHEMA,
                "lanes": {str(n): ["/definitely/missing/bc250-lane"] for n in range(20, 27)},
            }
            (campaign / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            manager = manager_module.CampaignManager(campaign)
            manager.state = {
                "result": "INCOMPLETE",
                "lanes": {str(n): {"result": "PENDING", "attempts": 0} for n in range(20, 27)},
                "barriers": {},
            }
            manager.persist()
            manager.event = lambda *args, **kwargs: None  # type: ignore[method-assign]
            rc = manager.run_lane("20")
            result = json.loads((campaign / "evidence/lane-20/result.json").read_text(encoding="utf-8"))
        self.assertEqual(rc, 2)
        self.assertEqual(result["result"], "HARNESS")
        self.assertEqual(result["returncode"], 2)

    def test_post_reboot_retry_runs_lane26_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            manager = manager_module.CampaignManager(campaign)
            manager.state = {
                "phase": "lane26-post-reboot",
                "result": "INCOMPLETE",
                "start_boot_id": "boot1",
                "post_reboot_boot_id": "boot2",
                "lanes": {
                    **{str(n): {"result": "PASS", "attempts": 1} for n in range(20, 26)},
                    "26": {"result": "INCOMPLETE", "attempts": 1},
                },
                "barriers": {f"after-{n}": {"result": "PASS"} for n in range(20, 26)},
            }
            called: list[str] = []
            original_boot_id = manager_module.read_boot_id
            manager_module.read_boot_id = lambda: "boot2"
            manager.run_lane = lambda lane: called.append(lane) or 0  # type: ignore[method-assign]
            manager.persist = lambda: None  # type: ignore[method-assign]
            manager.event = lambda *args, **kwargs: None  # type: ignore[method-assign]
            try:
                rc = manager.run_post_reboot()
            finally:
                manager_module.read_boot_id = original_boot_id
        self.assertEqual(rc, 0)
        self.assertEqual(called, ["26"])
        self.assertEqual(manager.state["phase"], "complete")

    def test_defect_is_non_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = manager_module.CampaignManager(Path(temporary))
            manager.state = {
                "phase": "lane26-post-reboot",
                "result": "DEFECT",
                "start_boot_id": "boot1",
                "post_reboot_boot_id": "boot2",
                "lanes": {
                    **{str(n): {"result": "PASS"} for n in range(20, 26)},
                    "26": {"result": "DEFECT"},
                },
                "barriers": {},
            }
            rc = manager.run_post_reboot()
        self.assertEqual(rc, 3)

    def test_missing_resume_artifact_becomes_controlled_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            manager = manager_module.CampaignManager(campaign)
            manager.state = {
                "schema": common.RESILIENCE_STATE_SCHEMA,
                "result": "INCOMPLETE",
                "lanes": {},
                "barriers": {},
                "evidence_gaps": [],
            }
            manager.persist()
            rc = manager.validate_resume_identity()
            state = json.loads(manager.state_path.read_text(encoding="utf-8"))
        self.assertEqual(rc, 4)
        self.assertEqual(state["result"], "INCOMPLETE")
        self.assertTrue(state["evidence_gaps"])


    def test_16_package_gate_schema_and_configuration_identity_are_bound(self) -> None:
        self.assertEqual(common.PACKAGE_GATE_SCHEMA, "bc250.package-gate.v2")
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            config.write_text("value = 1\n", encoding="utf-8")
            first = common.qualification_config_identity((config,))
            config.write_text("value = 2\n", encoding="utf-8")
            second = common.qualification_config_identity((config,))
        self.assertNotEqual(first, second)

    def test_gfx_identity_uses_machine_readable_stable_subset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            libexec = Path(temporary)
            helper = libexec / "gfx1013.sh"
            helper.write_text("#!/bin/sh\n", encoding="utf-8")
            original = common.run_command
            payload = {
                "schema": "bc250.gfx1013-status.v1",
                "state": "ENABLED",
                "profile": "v0.2.1-alpha",
                "upstream": {"version": "0.2.0-alpha", "commit": "d3e6dc"},
                "source_identity_ok": True,
                "package": {"prepared_nevra": "bc250-llm-server-0.13.1-1.6.fc44.x86_64"},
                "kernel": {"prepared": "7.2.9-200.fc44.x86_64"},
                "enabled_recorded": True,
                "ollama_private_radv_override": True,
                "private_radv_present": True,
                "private_icd_present": True,
                "vulkan": {"vendor_id": "0x1002", "device_id": "0x13fe", "driver_name": "radv"},
                "boot": {"saved_entry": "transient-not-bound"},
            }
            common.run_command = lambda *args, **kwargs: command_result(
                [str(helper), "status", "--json"],
                stdout=json.dumps(payload),
            )
            try:
                identity = common.gfx1013_identity(libexec)
            finally:
                common.run_command = original
        self.assertEqual(identity["state"], "ENABLED")
        self.assertEqual(identity["vulkan"]["device_id"], "0x13fe")
        self.assertNotIn("boot", identity)

    def test_package_gate_and_resume_bind_kernel_config_and_gfx_identity(self) -> None:
        gate_source = (QUALIFICATION / "package_gate_capture.py").read_text(encoding="utf-8")
        manager_source = (QUALIFICATION / "resilience_manager.py").read_text(encoding="utf-8")
        self.assertIn('"schema_version": 2', gate_source)
        self.assertIn('"qualification_identity": qualification', gate_source)
        self.assertIn("kernel/configuration/GFX1013 identity", manager_source)

    def test_package_gate_cli_has_no_result_override(self) -> None:
        source = (QUALIFICATION / "package_gate_capture.py").read_text(encoding="utf-8")
        self.assertNotIn('add_argument("--result"', source)
        self.assertIn("result derived from package-owned live checks", source)

    def test_release_wires_tika_410_and_qualification_commands(self) -> None:
        runtime = (ROOT / "config/runtime.env").read_text(encoding="utf-8")
        tika = (ROOT / "config/containers/tika.container").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("BC250_TIKA_VERSION=4.1.0-full", runtime)
        self.assertIn("sha256:d7607239d4e9c2dc1fd396f41a370576a334aef28f767e5bc5511247a1e1adf7", tika)
        self.assertIn('"package-gate|$LIBEXEC/qualification/package_gate_capture.py"', dispatcher)
        self.assertIn('"resilience|$LIBEXEC/qualification/resilience_manager.py"', dispatcher)
        self.assertIn("cmd/qualification/resilience_common.py", manifest)

    def test_reporting_separates_quality_headroom_and_restart_authorities(self) -> None:
        revalidate = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        install = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        status = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn("COMPLETED — QUALITY MIXED", revalidate)
        self.assertIn("qualification: PASS; diagnostic headroom: TIGHT", revalidate)
        self.assertIn("BC-250 configuration reboot", install)
        self.assertIn("OS/package restart check", install)
        self.assertIn("OS/package restart check", status)


if __name__ == "__main__":
    unittest.main()

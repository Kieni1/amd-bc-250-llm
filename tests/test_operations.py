from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent


class StatusTests(unittest.TestCase):
    def test_status_help_is_available_without_host_changes(self) -> None:
        result = subprocess.run(
            [str(ROOT / "cmd/monitoring/status.sh"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("read-only", result.stdout)

    def test_status_is_packaged_as_a_read_only_summary(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        for mutation in (
            "systemctl enable",
            "systemctl disable",
            "systemctl start",
            "systemctl stop",
            "sysctl --write",
            "rm -",
            "dnf ",
            "rpm -e",
        ):
            self.assertNotIn(mutation, source)
        for expected in (
            "bc250-cu-status",
            "vm.swappiness",
            "zramctl",
            "ollama-task.service",
            "ollama-agent.service",
            "PWM controls",
            "memory PSI",
            "Ollama main",
            "Ollama task",
            "Ollama agent",
            "Podman storage",
        ):
            self.assertIn(expected, source)


class VerifyTests(unittest.TestCase):
    def test_verify_reports_kernel_module_and_governor_compatibility(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        for expected in (
            'kernel="$(uname -r)"',
            '"/usr/lib/modules/$kernel/build"',
            "modinfo -n amdgpu",
            "modinfo -F vermagic amdgpu",
            "rebuild/reapply the 40-CU module",
            "cyan-skillfish-governor-smu --version",
            "toml_table_value gpu-usage fix-freq",
            "toml_table_value gpu-usage method",
        ):
            self.assertIn(expected, source)
        runtime_sources = source + (ROOT / "install").read_text(encoding="utf-8")
        runtime_sources += (ROOT / "cmd/system/40cu-module.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotRegex(
            runtime_sources,
            r"\b[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\.fc44(?:\.[A-Za-z0-9_]+)?\b",
        )

    def test_verify_detects_optional_compute_stack_and_vulkan_failures(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        for expected in (
            "QUEUE_COMPUTE_BIT",
            "QUEUE_GRAPHICS_BIT",
            "/opt/bc250-gfx1013",
            "bc250.gfx1013_v33=1",
            "*/updates/amdgpu.ko*",
            "ollama --version",
            "ErrorDeviceLost",
            "Not enough memory for command submission",
            "ring comp_",
            "journalctl -k -b",
            "for port in 11434 11435 11436",
            "expected container-bridge listener",
        ):
            self.assertIn(expected, source)


class CuStatusTests(unittest.TestCase):
    def test_cu_status_reports_stale_preparation_after_kernel_change(self) -> None:
        source = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        self.assertIn("/var/lib/bc250-llm-server/40cu/prepared", source)
        self.assertIn("stale: prepared for", source)
        self.assertIn("sudo bc250-40cu prepare", source)


class SwapProfileTests(unittest.TestCase):
    def test_swappiness_override_is_optional_and_reversible(self) -> None:
        source = (ROOT / "cmd/system/swap-profile.sh").read_text(encoding="utf-8")
        self.assertIn('SWAPPINESS="${SWAPPINESS:-}"', source)
        self.assertIn("90-bc250-llm-server-swap.conf", source)
        self.assertIn("swappiness.previous", source)
        self.assertIn("SWAPPINESS must be an integer from 0 through 200", source)
        self.assertIn('sysctl --write "vm.swappiness=$previous_swappiness"', source)
        self.assertIn("vm.swappiness was left at the current system value", source)


if __name__ == "__main__":
    unittest.main()

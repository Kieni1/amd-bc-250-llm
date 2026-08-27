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
            "MIN_FREE_GB",
            "CPU power states",
            "cpufreq",
            "Missing C-states",
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
            "--get-active-zones",
            "--list-rich-rules",
            "CPU topology",
            "cpufreq driver",
            "16 threads are active",
        ):
            self.assertIn(expected, source)


class RuntimeConvenienceTests(unittest.TestCase):
    def test_temperature_watch_is_default_and_once_is_available(self) -> None:
        source = (ROOT / "cmd/monitoring/check-temp.sh").read_text(encoding="utf-8")
        self.assertIn('""|-w|--watch)', source)
        self.assertIn('--once) show_temps', source)
        result = subprocess.run(
            [str(ROOT / "cmd/monitoring/check-temp.sh"), "--help"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("continuous watch is the default", result.stdout)

    def test_mtp_disables_shared_prompt_cache_when_supported(self) -> None:
        source = (ROOT / "models/mtp/run-mtp-llamacpp.sh").read_text(encoding="utf-8")
        self.assertIn("grep -Fq -- '--cache-ram'", source)
        self.assertIn("cache_flags+=(--cache-ram 0)", source)
        self.assertIn("grep -Fq -- '--no-cache-idle-slots'", source)
        self.assertIn("cache_flags+=(--no-cache-idle-slots)", source)

    def test_cpu_sysfs_scan_ignores_an_unexpanded_glob(self) -> None:
        for relative in ("cmd/monitoring/status.sh", "cmd/monitoring/verify-server.sh"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('[[ -d "$cpu" ]] || continue', source)

    def test_benchmark_uses_role_appropriate_runtime_metrics(self) -> None:
        benchmark_path = ROOT / "cmd/benchmark/compare-models.sh"
        benchmark = benchmark_path.read_text(encoding="utf-8")
        sensors = (ROOT / "cmd/benchmark/log_sensors.sh").read_text(encoding="utf-8")
        self.assertIn('BENCH_PROFILE="${BENCH_PROFILE:-moderate}"', benchmark)
        self.assertIn("NUM_PREDICT_PREFILL", benchmark)
        self.assertIn("prompt_eval_count stopped growing", benchmark)
        self.assertIn("allocated_context", benchmark)
        self.assertIn("resident_size_bytes", benchmark)
        self.assertIn("embedding_process_duration_s", benchmark)
        self.assertIn("mem_available_mib", benchmark)
        self.assertIn("INCLUDE_EMBEDDINGS", benchmark)
        self.assertIn('"$OLLAMA/api/embed"', benchmark)
        self.assertIn("truncate: false", benchmark)
        self.assertIn("keep_alive: $keep_alive", benchmark)
        self.assertEqual(benchmark.count('record_success "$model" "$label" "cold_chat" 1 "$row"'), 1)
        self.assertIn("grep -viE 'embed|ocr'", benchmark)
        self.assertIn("0.32.15", benchmark)
        self.assertIn("uncalibrated", sensors)
        result = subprocess.run(
            [str(benchmark_path), "--help"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("moderate is the package standard", result.stdout)


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

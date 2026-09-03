from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

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

    def test_verify_treats_static_agent_unit_as_not_boot_enabled(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn("UnitFileState", source)
        self.assertIn("enabled-runtime", source)
        self.assertNotIn("is-enabled --quiet ollama-agent.service", source)

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


class DiagnoseTests(unittest.TestCase):
    def test_static_no_load_run_does_not_warn_about_expected_absence_of_resident_model(self) -> None:
        source = (ROOT / "cmd/monitoring/llm-run-diagnose.sh").read_text(encoding="utf-8")
        self.assertIn("no model resident (--no-load requested; residency test skipped)", source)
        self.assertNotIn('wn "no model resident (start it, or run without --no-load)"', source)

    def test_mesa_reference_delta_is_informational_not_a_package_failure(self) -> None:
        source = (ROOT / "cmd/monitoring/llm-run-diagnose.sh").read_text(encoding="utf-8")
        self.assertIn("package does not pin Mesa", source)
        self.assertNotIn('wn "${mv:-Mesa ?}  (ref Mesa 26.1.4)"', source)


class RuntimeConvenienceTests(unittest.TestCase):
    def test_temperature_watch_is_default_and_once_is_available(self) -> None:
        source = (ROOT / "cmd/monitoring/check-temp.sh").read_text(encoding="utf-8")
        self.assertIn('""|-w|--watch)', source)
        self.assertIn("--once) show_temps", source)
        result = subprocess.run(
            [str(ROOT / "cmd/monitoring/check-temp.sh"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
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

    def test_benchmark_dispatches_structured_suites_and_records_resource_peaks(
        self,
    ) -> None:
        wrapper = (ROOT / "cmd/benchmark/compare-models.sh").read_text(encoding="utf-8")
        generation = (ROOT / "cmd/benchmark/generation-benchmark.py").read_text(
            encoding="utf-8"
        )
        categories = (ROOT / "cmd/benchmark/category-benchmark.py").read_text(
            encoding="utf-8"
        )
        common = (ROOT / "cmd/benchmark/benchmark_common.py").read_text(
            encoding="utf-8"
        )
        for expected in (
            "embeddings|embedding|ocr|task|agent|coding",
            "generation-benchmark.py",
            "Ollama 0.33.2",
        ):
            self.assertIn(expected, wrapper)
        for expected in (
            "BENCH_MODE",
            "NEUTRAL_SYSTEM",
            'payload["system"] = NEUTRAL_SYSTEM',
            "THINK_MODE",
            "resolve_think_policy",
            "done_reason=stop",
            "RUN_THERMAL",
            "temp_max_c",
            "mem_available_min_mib",
            "swap_used_max_mib",
            "vram_used_max_bytes",
            "gtt_used_max_bytes",
            "client.digest(model)",
        ):
            self.assertIn(expected, generation)
        self.assertNotIn('"think": false', generation.lower())
        for expected in (
            "recall_at_1",
            "cross_mrr",
            "OCR_PROMPTS",
            "word_precision",
            "word_f1",
            "char_similarity",
            "field_order_score",
            "task_prompt",
            "benchmark_agent",
            "validate_agent_output",
            '"keep_alive": 0',
        ):
            self.assertIn(expected, categories)
        for expected in (
            "mem_info_vram_used",
            "mem_info_gtt_used",
            "seconds_ge_85c",
            "gpu_clock_min_mhz",
            "discover_amdgpu_device",
            "amdgpu_edge_temperature",
        ):
            self.assertIn(expected, common)
        result = subprocess.run(
            [str(ROOT / "cmd/benchmark/compare-models.sh"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("BENCH_MODE=neutral", result.stdout)
        self.assertIn("Ollama 0.33.2", result.stdout)
        self.assertIn("bc250-benchmark agent", result.stdout)


class CuStatusTests(unittest.TestCase):
    def test_cu_status_reports_stale_preparation_after_kernel_change(self) -> None:
        source = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        self.assertIn("/var/lib/bc250-llm-server/40cu/prepared", source)
        self.assertIn("stale: prepared for", source)
        self.assertIn("sudo bc250-40cu prepare", source)

    def test_cu_status_keeps_full_routing_table_without_fixed_count_success(self) -> None:
        status = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        diagnose = (ROOT / "cmd/monitoring/llm-run-diagnose.sh").read_text(encoding="utf-8")
        self.assertIn("Live routing dashboard", status)
        self.assertIn('value == "S+"', status)
        self.assertIn('value == "D!"', status)
        self.assertIn("no off/problem cells", verify)
        self.assertNotIn("40/40 routed", verify)
        self.assertNotIn("partial CU routing table", verify)
        self.assertNotIn("40/40 active and routed", diagnose)

    def test_cu_routing_cell_parser_classifies_dashboard_states(self) -> None:
        source = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        start = source.index("routing_cells() {")
        end = source.index("\nread_param() {", start)
        function = source[start:end]
        sample = "| SE0.SH0 | W0 | S+ | D+ | D! | -- |\n"
        result = subprocess.run(
            ["bash", "-c", function + "\nrouting_cells",],
            input=sample, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip(), "1 1 1 1")


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

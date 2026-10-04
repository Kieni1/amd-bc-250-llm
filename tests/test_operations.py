from __future__ import annotations

import os
import subprocess
import tempfile
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
            "cu-status.sh",
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
            "CPU idle",
        ):
            self.assertIn(expected, source)


    def test_status_surfaces_topology_aware_overall_state(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn('Overall: HEALTHY', source)
        self.assertIn('Runtime mode: exclusive agent', source)
        self.assertIn('Overall: DEGRADED', source)
        self.assertIn('Recovery: sudo bc250 agent-mode normal', source)
        self.assertIn('Overall: UNAVAILABLE', source)
        self.assertIn('Reason: optional needs-restarting helper unavailable', source)

    def test_status_reports_protected_storage_instead_of_zero_size(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        start = source.index("directory_usage() {")
        end = source.index("\nollama_version_line() {", start)
        function = source[start:end]
        command = (
            function
            + "\ndu() { echo 'du: cannot read directory: Permission denied'; return 1; }; "
            + "directory_usage 'Open WebUI' /protected"
        )
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("protected (use sudo)", result.stdout)
        self.assertNotRegex(result.stdout, r"Open WebUI\s+0\s")

    def test_status_queries_ollama_version_from_an_active_lane(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        start = source.index("ollama_version_line() {")
        end = source.index("\nopenwebui_readiness() {", start)
        function = source[start:end]
        command = function + """
systemctl() {
  [[ $1 == is-active && $3 == ollama-agent.service ]]
}
curl() {
  [[ ${@: -1} == http://127.0.0.1:11436/api/version ]] || return 9
  printf '{"version":"0.34.0"}\n'
}
jq() { printf '0.34.0\n'; }
ollama_version_line
"""
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Ollama server version: 0.34.0")
        self.assertNotIn("Warning", result.stdout)

    def test_status_reports_openwebui_application_readiness(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn("openwebui_readiness()", source)
        self.assertIn("active-not-ready", source)
        self.assertIn("Open WebUI application readiness", source)
        self.assertIn("resident:", source)
        self.assertIn("Reboot recommendation: not checked", source)

    def test_support_bundle_is_redacted_read_only_evidence(self) -> None:
        path = ROOT / "cmd/monitoring/support-bundle.sh"
        result = subprocess.run(
            [str(path), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        source = path.read_text(encoding="utf-8")
        for expected in (
            "manifest.json",
            "SHA256SUMS.txt",
            "bc250 status",
            "bc250 verify --summary",
            "bc250 maintenance status",
            "pstore-presence.txt",
            "memory.events",
            "BC250_SUPPORT_CAPTURE_TIMEOUT",
            "interpretation=TIMEOUT",
            "sha256sum -c SHA256SUMS.txt",
            "Support bundle created and self-verified",
        ):
            self.assertIn(expected, source)
        for forbidden in (
            "/var/lib/open-webui/webui.db",
            "journalctl -u open-webui.service",
            "cat /var/lib/bc250-llm-server/secrets/openwebui-admin.key",
        ):
            self.assertNotIn(forbidden, source)

    def test_status_uses_agent_mode_as_single_runtime_topology_classifier(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        start = source.index("runtime_mode() {")
        end = source.index("\nollama_status() {", start)
        function = source[start:end]
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "bc250"
            helper.write_text(
                "#!/usr/bin/env bash\nprintf 'ollama.service failed\nmode=%s\n' \"${TEST_MODE}\"\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)
            for expected in ("normal", "degraded", "stopped", "agent"):
                env = os.environ | {
                    "PATH": f"{tmp}:{os.environ.get('PATH', '')}",
                    "TEST_MODE": expected,
                }
                result = subprocess.run(
                    ["bash", "-c", function + "\nruntime_mode"],
                    text=True,
                    capture_output=True,
                    env=env,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
        self.assertIn("degraded (partial normal topology)", source)
        self.assertIn("stopped (normal and agent lanes inactive)", source)



class VerifyTests(unittest.TestCase):
    def test_verify_reports_kernel_module_and_governor_compatibility(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        for expected in (
            'kernel="$(uname -r)"',
            "cyan-skillfish-governor-smu --version",
            "toml_table_value gpu-usage fix-freq",
            "toml_table_value gpu-usage method",
            "IOMMU is outside the qualified LLM baseline",
            "/etc/tmpfiles.d /usr/lib/tmpfiles.d /etc/modprobe.d",
        ):
            self.assertIn(expected, source)
        self.assertNotIn("6.15.0", source)
        self.assertNotIn("6.17.8", source)
        self.assertNotIn("bc250_cc_write_mode", source)
        self.assertNotIn("legacy patched AMDGPU module detected", source)
        runtime_sources = source + (ROOT / "install").read_text(encoding="utf-8")
        self.assertNotRegex(
            runtime_sources,
            r"\b[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\.fc44(?:\.[A-Za-z0-9_]+)?\b",
        )

    def test_verify_reports_dependent_lane_checks_as_skipped(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('skipped "task model registration unavailable because ollama-task.service is inactive"', source)
        self.assertIn('skipped "RAG embedding registration unavailable because ollama-embedding.service is inactive"', source)
        self.assertIn('skipped "authenticated Open WebUI desired-state check (no API token supplied)"', source)
        self.assertIn("Verification: %d ok / %d warn / %d fail / %d skipped", source)
        self.assertIn("optional/authenticated check was skipped", source)

    def test_verify_treats_static_agent_unit_as_normal_inactive_optional_lane(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn("UnitFileState", source)
        self.assertIn("enabled-runtime", source)
        self.assertNotIn("is-enabled --quiet ollama-agent.service", source)
        self.assertIn("optional Agent lane is inactive in normal mode", source)
        self.assertNotIn("ollama-agent.service is not enabled at boot", source)



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
    def test_temperature_helper_is_removed_in_favor_of_sensors(self) -> None:
        self.assertFalse((ROOT / "cmd/monitoring/check-temp.sh").exists())
        hardware = (ROOT / "docs/HARDWARE.md").read_text(encoding="utf-8")
        self.assertIn("watch -n 1 sensors", hardware)
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertNotIn("check-temp", manifest)


    def test_mtp_runner_help_does_not_require_llamacpp(self) -> None:
        result = subprocess.run(
            [str(ROOT / "models/mtp/run-mtp-llamacpp.sh"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("qwen3.5-9b-mtp", result.stdout)
        self.assertIn("qwen3.8-27b-hauhaucs-mtp", result.stdout)
        self.assertIn("qwen3.8-27b-ymq-xs-ti-mtp", result.stdout)
        self.assertNotIn("qwen3.6-27b-mtp", result.stdout)
        self.assertNotIn("qwen3.6-35b-a3b-mtp", result.stdout)
        self.assertNotIn("qwen36-27b", result.stdout)
        self.assertNotIn("qwen38-27b", result.stdout)
        self.assertNotIn("set LLAMACPP", result.stdout)

    def test_mtp_runner_missing_source_points_to_exact_fetch_before_runtime(self) -> None:
        result = subprocess.run(
            [str(ROOT / "models/mtp/run-mtp-llamacpp.sh"), "qwen3.8-27b-ymq-xs-ti-mtp"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "sudo bc250 fetch-mtp qwen3.8-27b-ymq-xs-ti-mtp", result.stdout
        )
        self.assertNotIn("set LLAMACPP", result.stdout)

    def test_mtp_disables_shared_prompt_cache_when_supported(self) -> None:
        source = (ROOT / "models/mtp/run-mtp-llamacpp.sh").read_text(encoding="utf-8")
        self.assertIn("grep -Fq -- '--cache-ram'", source)
        self.assertIn("cache_flags+=(--cache-ram 0)", source)
        self.assertIn("grep -Fq -- '--no-cache-idle-slots'", source)
        self.assertIn("cache_flags+=(--no-cache-idle-slots)", source)

    def test_mtp_runner_drains_ollama_and_restores_direct_operator_residency(self) -> None:
        source = (ROOT / "models/mtp/run-mtp-llamacpp.sh").read_text(encoding="utf-8")
        for expected in (
            'RESIDENCY_POLICY="${BC250_MTP_RESIDENCY_POLICY:-restore}"',
            'OLLAMA_PORTS=(11434 11435 11436 11437)',
            "snapshot_ollama_residency()",
            "drain_ollama_residency()",
            "stop_ollama_model()",
            "restore_ollama_residency()",
            "bc250 MTP residency restore probe",
            "ollama stop",
            "configured default residency policy applies",
        ):
            self.assertIn(expected, source)
        self.assertIn('if [[ "$RESIDENCY_POLICY" == drain-only ]]; then', source)
        self.assertIn('trap restore_on_exit EXIT', source)

    def test_mtp_compare_explicitly_keeps_ollama_cold_for_qualification(self) -> None:
        source = (ROOT / "models/experiments/compare-mtp.sh").read_text(encoding="utf-8")
        self.assertIn("ollama_residency_policy=drain-only", source)
        self.assertIn("BC250_MTP_RESIDENCY_POLICY=drain-only", source)

    def test_mtp_compare_records_and_verifies_effective_draft_depth(self) -> None:
        source = (ROOT / "models/experiments/compare-mtp.sh").read_text(encoding="utf-8")
        for expected in (
            "catalog_draft_n_max",
            "requested_draft_n_max",
            "effective_draft_n_max",
            "draft_n_source",
            'grep -Fq -- "--spec-draft-n-max $EFFECTIVE_DRAFT_N_MAX"',
            "runtime-config.txt",
            "baseline server flags unexpectedly enabled MTP",
        ):
            self.assertIn(expected, source)

    def test_cpu_sysfs_scan_ignores_an_unexpanded_glob(self) -> None:
        for relative in ("cmd/monitoring/status.sh", "cmd/monitoring/verify-server.sh"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('[[ -d "$cpu" ]] || continue', source)

    def test_benchmark_dispatches_canonical_suites_and_workflows(self) -> None:
        wrapper = (ROOT / "cmd/benchmark/benchmark.sh").read_text(encoding="utf-8")
        generation = (ROOT / "cmd/benchmark/generation-benchmark.py").read_text(
            encoding="utf-8"
        )
        categories = (ROOT / "cmd/benchmark/category-benchmark.py").read_text(
            encoding="utf-8"
        )
        runtime_workflow = (ROOT / "cmd/benchmark/runtime-benchmark.py").read_text(encoding="utf-8")
        openwebui_workflow = (ROOT / "cmd/benchmark/openwebui-benchmark.py").read_text(encoding="utf-8")
        workflow = runtime_workflow + "\n" + openwebui_workflow
        common = (ROOT / "cmd/benchmark/benchmark_common.py").read_text(
            encoding="utf-8"
        )
        for expected in (
            "bc250 benchmark generation",
            "bc250 benchmark rag-cycle",
            "bc250 benchmark concurrency",
            "bc250 benchmark owui-system-context",
        ):
            self.assertIn(expected, wrapper)
        for legacy in ("embeddings|embedding", "agent|coding", "compare-models.sh"):
            self.assertNotIn(legacy, wrapper)
        for expected in (
            "prepare_result_dir",
            'choices=("compare", "edge", "thermal")',
            "swap_peak_delta_mib",
            "client.digest(model)",
        ):
            self.assertIn(expected, generation)
        for expected in (
            "result_record",
            "write_result_summary",
            'category="ocr"',
            'category="rag-cycle"',
            'category="rag-quality"',
        ):
            self.assertIn(expected, categories)
        for expected in (
            "cmd_concurrency",
            "cmd_num_batch",
            "cmd_owui_rag",
            "cmd_owui_embedding_batch",
            "cmd_owui_chunk_min",
            "cmd_owui_system_context",
        ):
            self.assertIn(expected, workflow)
        for expected in (
            "BenchmarkPaths",
            "prepare_result_dir",
            "results.jsonl",
            "summary.json",
            "fixtures",
        ):
            self.assertIn(expected, common)
        result = subprocess.run(
            [str(ROOT / "cmd/benchmark/benchmark.sh"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("bc250 benchmark generation", result.stdout)
        self.assertIn("bc250 benchmark agent", result.stdout)
        missing = subprocess.run(
            [str(ROOT / "cmd/benchmark/benchmark.sh")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(missing.returncode, 2, missing.stdout)
        legacy = subprocess.run(
            [str(ROOT / "cmd/benchmark/benchmark.sh"), "rag"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(legacy.returncode, 2, legacy.stdout)


class CuStatusTests(unittest.TestCase):
    def test_cu_status_has_no_legacy_kernel_module_state(self) -> None:
        source = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        self.assertNotIn("40cu/prepared", source)
        self.assertNotIn("bc250_cc_write_mode", source)
        self.assertNotIn("Persistent patched-module activation", source)

    def test_cu_status_keeps_full_routing_table_without_fixed_count_success(self) -> None:
        status = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        diagnose = (ROOT / "cmd/monitoring/llm-run-diagnose.sh").read_text(encoding="utf-8")
        self.assertIn("Live routing dashboard", status)
        self.assertIn("Kernel diagnostic active_cu_number", status)
        self.assertIn("not live-routing authority", status)
        main_status = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn("Kernel diagnostic active_cu_number", main_status)
        self.assertIn('value == "S+"', status)
        self.assertIn('value == "D!"', status)
        self.assertIn("Routing profile match", verify)
        self.assertIn("configured saved profile", verify)
        self.assertIn("BC250_WGP_MASKS", status)
        self.assertIn("Configured live profile", status)
        self.assertIn("Live routing profile", status)
        self.assertIn('[[ "$live_masks" == "$saved_masks" ]]', status)
        self.assertNotIn("modified 40-CU module", verify)
        self.assertNotIn("40/40 routed", verify)
        self.assertNotIn("partial CU routing table", verify)
        self.assertNotIn("40/40 active and routed", diagnose)

    def test_cu_routing_cell_parser_classifies_dashboard_states(self) -> None:
        source = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        start = source.index("routing_cells() {")
        end = source.index("\nread_param() {", start)
        functions = source[start:end]
        sample = (
            "| SE0.SH0 | D+ | D+ | D+ | -- | -- | 0x07 | 0x0 | 6/10 |\n"
            "| SE0.SH1 | D+ | D+ | D+ | S+ | -- | 0x0f | 0x0 | 8/10 |\n"
            "| SE1.SH0 | D+ | D+ | D+ | -- | -- | 0x07 | 0x0 | 6/10 |\n"
            "| SE1.SH1 | D+ | D+ | D+ | S+ | -- | 0x0f | 0x0 | 8/10 |\n"
        )
        for command, expected in (
            ("routing_cells", "2 12 0 6"),
            ("routing_mask_csv", "0x07,0x0f,0x07,0x0f"),
            ('normalize_mask_csv "0x07,0x0f,0x07,0x0f"', "0x07,0x0f,0x07,0x0f 28"),
        ):
            with self.subTest(command=command):
                result = subprocess.run(
                    ["bash", "-c", functions + "\n" + command],
                    input=sample, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout.strip(), expected)


class SwapProfileTests(unittest.TestCase):
    def test_swap_directory_mode_matches_package_contract(self) -> None:
        source = (ROOT / "cmd/system/swap-profile.sh").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "packaging/bc250-llm-server.tmpfiles").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn('install -d -m0750 "$SWAP_DIR"', source)
        self.assertNotIn('install -d -m0755 "$SWAP_DIR"', source)
        self.assertIn("d /var/lib/bc250-llm-server/swap 0750 root root -", tmpfiles)
        self.assertIn("%attr(0750,root,root) /var/lib/bc250-llm-server/swap", spec)

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

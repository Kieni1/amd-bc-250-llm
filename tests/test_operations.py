from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
CURRENT_VERSION = CONTRACT["package"]["version"]
CURRENT_RELEASE = CONTRACT["package"]["rpm_release"]
CURRENT_NEVRA = f"{CONTRACT['package']['name']}-{CURRENT_VERSION}-{CURRENT_RELEASE}.fc44.x86_64"


class StatusTests(unittest.TestCase):
    def test_verify_rejects_symlink_openwebui_token_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "token"
            target.write_text("secret\n", encoding="utf-8")
            target.chmod(0o600)
            link = Path(tmp) / "token-link"
            link.symlink_to(target)
            result = subprocess.run(
                [str(ROOT / "cmd/monitoring/verify-server.sh"), "--owui-token-file", str(link)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("must not be a symlink", result.stderr)

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


    def test_status_human_platform_includes_installed_package_identity(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn('section "Platform"', source)
        self.assertIn("Package:", source)
        self.assertIn("bc250-llm-server 2>/dev/null", source)

    def test_ollama_profile_apply_is_nounset_safe(self) -> None:
        source = (ROOT / "cmd/system/ollama-profile.sh").read_text(encoding="utf-8")
        start = source.index("apply_profile() {")
        end = source.index("\n}", start) + 2
        function = source[start:end]
        command = (
            "set -u\n"
            "PROFILE_DIR=/definitely/missing\n"
            "require_root(){ :; }\n"
            + function
            + "\napply_profile balanced"
        )
        result = subprocess.run(
            ["bash", "-c", command],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing profile /definitely/missing/balanced.conf", result.stderr)
        self.assertNotIn("unbound variable", result.stderr)

    def test_status_surfaces_topology_aware_overall_state(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn('Overall: HEALTHY', source)
        self.assertIn('Overall: SETUP INCOMPLETE — package runtime convergence pending', source)
        self.assertIn('Overall: HEALTHY WITH WARNINGS — package runtime identity mismatch', source)
        self.assertIn('Overall: HEALTHY WITH WARNINGS — package runtime identity unavailable', source)
        self.assertNotIn('package runtime identity mismatch/unavailable', source)
        self.assertIn('Runtime mode: exclusive agent', source)
        self.assertIn('Overall: DEGRADED', source)
        self.assertIn('Recovery: sudo bc250 advanced agent normal', source)
        self.assertIn('Overall: UNAVAILABLE', source)
        self.assertIn('Reboot required: UNKNOWN (restart check unavailable)', source)

    def test_status_overall_state_distinguishes_pending_mismatch_and_unavailable(self) -> None:
        source = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        start = source.index("topology_summary() {")
        end = source.index("\n}\n\nollama_status() {", start) + 2
        function = source[start:end]
        cases = (
            (("normal", "unavailable", "convergence_pending"), "Overall: SETUP INCOMPLETE — package runtime convergence pending\nRuntime mode: normal"),
            (("normal", "mismatch", "published"), "Overall: HEALTHY WITH WARNINGS — package runtime identity mismatch\nRuntime mode: normal"),
            (("normal", "unavailable", "published"), "Overall: HEALTHY WITH WARNINGS — package runtime identity unavailable\nRuntime mode: normal"),
            (("normal", "match", "published"), "Overall: HEALTHY\nRuntime mode: normal"),
        )
        for arguments, expected in cases:
            command = function + "\ntopology_summary " + " ".join(arguments)
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)

    def test_status_json_uses_publication_hold_as_setup_convergence_signal(self) -> None:
        module_path = ROOT / "cmd/monitoring/status-json.py"
        spec = importlib.util.spec_from_file_location("bc250_status_setup_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            dropin = Path(temporary) / "90-enable.conf"
            with mock.patch.dict(module.os.environ, {"BC250_OWUI_ENABLE_DROPIN": str(dropin)}, clear=False):
                held = module.setup_state()
                dropin.write_text("[Install]\nWantedBy=multi-user.target\n", encoding="utf-8")
                published = module.setup_state()
        self.assertEqual(held["state"], "convergence_pending")
        self.assertEqual(held["open_webui_publication"], "held")
        self.assertIn("convergence", held["reason"])
        self.assertEqual(published["state"], "published")
        self.assertEqual(published["open_webui_publication"], "published")
        self.assertIsNone(published["reason"])

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
        self.assertIn("listener=", source)
        self.assertIn("backend=", source)
        self.assertIn("web-interface=", source)
        self.assertNotIn("front-door=", source)
        self.assertIn("listener-only", source)
        self.assertIn("Open WebUI application readiness", source)
        self.assertIn("resident:", source)
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn("Open WebUI web interface usable through nginx", verify)
        self.assertNotIn("Open WebUI front door usable through nginx", verify)
        self.assertIn("main Ollama BC-250 Vulkan contract", verify)
        for required in ("OLLAMA_VULKAN=1", "OLLAMA_IGPU_ENABLE=1", "GGML_VK_VISIBLE_DEVICES=0"):
            self.assertIn(required, verify)
        self.assertIn("resident:", source)
        self.assertIn("Reboot required: UNKNOWN (restart check unavailable)", source)


    def test_machine_readable_status_and_health_are_packaged_interfaces(self) -> None:
        status = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        status_json = (ROOT / "cmd/monitoring/status-json.py").read_text(encoding="utf-8")
        health = ROOT / "cmd/monitoring/health.py"
        self.assertIn("Usage: bc250 status [--json]", status)
        self.assertIn('"schema": "bc250.status.v4"', status_json)
        self.assertIn('"setup": setup_state()', status_json)
        self.assertNotIn("gfx" + "1013", status_json.lower())
        result = subprocess.run(
            [str(health), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("read-only appliance health diagnostics", result.stdout)
        health_source = health.read_text(encoding="utf-8")
        self.assertIn('"schema": "bc250.health.v1"', health_source)
        self.assertIn('["rpm", "-V", PACKAGE]', health_source)
        self.assertIn("diagnostic headroom TIGHT", health_source)
        self.assertIn("runtime_identity", status_json)
        self.assertIn("Overall appliance health:", health_source)
        self.assertNotIn("gfx" + "1013", health_source.lower())

    def test_health_contract_has_no_obsolete_doctor_alias(self) -> None:
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        completion = (ROOT / "packaging/completions/bc250.bash").read_text(encoding="utf-8")
        health = ROOT / "cmd/monitoring/health.py"
        health_source = health.read_text(encoding="utf-8")
        self.assertIn('"health|$LIBEXEC/health.py"', dispatcher)
        self.assertNotIn('"doctor|', dispatcher)
        self.assertIn("status|health", completion)
        self.assertNotIn(" doctor ", f" {completion} ")
        self.assertIn('"schema": "bc250.health.v1"', health_source)
        self.assertIn('prog="bc250 health"', health_source)
        self.assertIn('"NO_COLOR" not in os.environ', health_source)

        spec = importlib.util.spec_from_file_location("bc250_health_color_test", health)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class TtyStream:
            @staticmethod
            def isatty() -> bool:
                return True

        class PlainStream:
            @staticmethod
            def isatty() -> bool:
                return False

        with mock.patch.object(module.sys, "stdout", TtyStream()), mock.patch.dict(
            module.os.environ, {"TERM": "xterm"}, clear=False
        ):
            module.os.environ.pop("NO_COLOR", None)
            self.assertIn("\x1b[1;32mPASS\x1b[0m", module.color_verdict("PASS"))
            self.assertIn("\x1b[1;31mFAIL\x1b[0m", module.color_verdict("FAIL"))
            self.assertIn("\x1b[1;33mWARN\x1b[0m", module.color_verdict("WARN"))

        with mock.patch.object(module.sys, "stdout", PlainStream()), mock.patch.dict(
            module.os.environ, {"TERM": "xterm"}, clear=False
        ):
            module.os.environ.pop("NO_COLOR", None)
            self.assertEqual(module.color_verdict("PASS"), "PASS")

        with mock.patch.object(module.sys, "stdout", TtyStream()), mock.patch.dict(
            module.os.environ, {"TERM": "xterm", "NO_COLOR": "1"}, clear=False
        ):
            self.assertEqual(module.color_verdict("FAIL"), "FAIL")

    def test_status_json_normalizes_the_known_tika_version_prefix(self) -> None:
        source = (ROOT / "cmd/monitoring/status-json.py").read_text(encoding="utf-8")
        self.assertIn('value.startswith("Apache Tika ")', source)
        self.assertIn('value.removeprefix("Apache Tika ").strip()', source)

    def test_non_root_runtime_identity_is_not_inspected_without_health_mismatch(self) -> None:
        module_path = ROOT / "cmd/monitoring/status-json.py"
        spec = importlib.util.spec_from_file_location("bc250_status_json_test", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            share = Path(temporary)
            (share / "runtime.env").write_text(
                (
                    "BC250_OPEN_WEBUI_VERSION=0.12.3\n"
                    f"BC250_OPEN_WEBUI_IMAGE_DIGEST=sha256:{'1' * 64}\n"
                    "BC250_TIKA_VERSION=4.1.0-full\n"
                    f"BC250_TIKA_IMAGE_DIGEST=sha256:{'2' * 64}\n"
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(module.os, "geteuid", return_value=1000),
                mock.patch.object(module, "container_image_identity") as inspect_image,
                mock.patch.object(module, "tika_live_version") as tika_version,
                mock.patch.object(module, "open_webui_live_version") as owui_version,
            ):
                payload = module.runtime_identity(share)
        self.assertEqual(payload["inspection"], "not_inspected")
        self.assertIsNone(payload["match"])
        self.assertIn("requires sudo", payload["reason"])
        for service in ("open_webui", "tika"):
            self.assertEqual(payload[service]["inspection"], "not_inspected")
            self.assertIsNone(payload[service]["match"])
            self.assertIsNone(payload[service]["observed"]["digest"])
        inspect_image.assert_not_called()
        tika_version.assert_not_called()
        owui_version.assert_not_called()

        status = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        version = (ROOT / "cmd/monitoring/version.py").read_text(encoding="utf-8")
        health = (ROOT / "cmd/monitoring/health.py").read_text(encoding="utf-8")
        self.assertIn('runtime_inspection" == not_inspected', status)
        self.assertIn('runtime_identity_state=not_inspected', status)
        self.assertIn("Package runtime identity: requires sudo for inspection", status)
        self.assertIn('row.get("inspection") == "not_inspected"', version)
        self.assertIn('"INFO"', health)
        self.assertNotIn("secure-boot", health.lower())

    def test_public_runtime_identity_and_package_identity_are_unambiguous(self) -> None:
        status_json = (ROOT / "cmd/monitoring/status-json.py").read_text(encoding="utf-8")
        version = (ROOT / "cmd/monitoring/version.py").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        for source in (status_json, version):
            self.assertIn('"epoch": epoch', source)
            self.assertIn('f"{name}-{version}-{release}.{arch}"', source)
            self.assertNotIn('f"{name}-{epoch}:{version}-{release}.{arch}"', source)
        self.assertIn("runtime_identity", status_json)
        self.assertIn("configured_runtime", version)
        self.assertIn("runtime_identity", version)
        self.assertIn('section "Package runtime identity"', verify)
        self.assertIn("release acceptance additionally requires bc250 advanced qualification", verify)

    def test_runtime_state_identifies_only_active_zram_swap_membership(self) -> None:
        helper = ROOT / "cmd/monitoring/runtime-state.sh"
        command = f"""
source {helper!s}
swapon() {{
  if [[ $* == *'--output NAME'* ]]; then
    printf '/dev/zram0\n/var/lib/bc250-llm-server/swap/bc250-llm.swap\n'
  fi
}}
bc250_active_zram_swap_names
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/dev/zram0")

    def test_runtime_state_does_not_treat_initialized_zram_as_active_swap(self) -> None:
        helper = ROOT / "cmd/monitoring/runtime-state.sh"
        command = f"""
source {helper!s}
swapon() {{
  if [[ $* == *'--output NAME'* ]]; then
    printf '/var/lib/bc250-llm-server/swap/bc250-llm.swap\n'
  fi
}}
bc250_active_zram_swap_names
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_runtime_state_distinguishes_unavailable_swap_inspection(self) -> None:
        helper = ROOT / "cmd/monitoring/runtime-state.sh"
        command = f"""
source {helper!s}
swapon() {{ return 7; }}
bc250_active_swap_names >/dev/null
rc=$?
[[ "$rc" == 7 ]] || exit 21
bc250_active_zram_swap_names >/dev/null
rc=$?
[[ "$rc" == 7 ]] || exit 23
exit 0
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verify_reports_unavailable_swap_state_as_unknown(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn("active swap state could not be determined", source)
        self.assertIn("zram swap activity is unverified", source)
        self.assertIn("disk-backed swap safety margin is unverified", source)

    def test_runtime_state_parses_actual_failed_systemd_units_not_exit_code(self) -> None:
        helper = ROOT / "cmd/monitoring/runtime-state.sh"
        command = f"""
source {helper!s}
systemctl() {{
  printf 'broken.service loaded failed failed Broken unit\n'
  return 0
}}
bc250_failed_systemd_units
"""
        result = subprocess.run(
            ["bash", "-c", command], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "broken.service")

    def test_verify_uses_runtime_state_for_active_zram_and_failed_units(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn("bc250_active_swap_names", source)
        self.assertIn("no zram device is active as swap", source)
        self.assertIn("bc250_failed_systemd_units", source)
        self.assertIn("systemd has failed units", source)

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
        self.assertIn("mktemp -d /run/bc250/support-bundle.XXXXXX", source)
        self.assertIn("-bc250-support-bundle.tar.gz", source)
        self.assertNotIn("/run/bc250 support-bundle", source)
        self.assertNotIn("-bc250 support-bundle.tar.gz", source)

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



    def test_version_executes_all_output_modes_with_installed_rpm_identity(self) -> None:
        version = ROOT / "cmd/monitoring/version.py"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            bindir = base / "bin"
            share = base / "share"
            libexec = base / "libexec"
            bindir.mkdir()
            share.mkdir()
            libexec.mkdir()
            (share / "VERSION").write_text(CURRENT_VERSION + "\n", encoding="utf-8")
            (share / "runtime.env").write_text(
                "BC250_OLLAMA_VERSION=0.40.8\n"
                "BC250_OPEN_WEBUI_VERSION=0.12.3\n"
                "BC250_OPEN_WEBUI_IMAGE_DIGEST=sha256:" + "1" * 64 + "\n"
                "BC250_TIKA_VERSION=4.1.0-full\n"
                "BC250_TIKA_IMAGE_DIGEST=sha256:" + "2" * 64 + "\n"
                "BC250_GOVERNOR_VERSION=0.4.14\n",
                encoding="utf-8",
            )
            rpm = bindir / "rpm"
            rpm.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'bc250-llm-server|0|{CURRENT_VERSION}|{CURRENT_RELEASE}.fc44|x86_64\\n'\n",
                encoding="utf-8",
            )
            rpm.chmod(0o755)
            status = libexec / "status-json.py"
            status.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "json.dump({'runtime_identity': {"
                "'open_webui': {'expected': {'version': '0.12.3', 'digest': 'sha256:' + '1'*64}, 'observed': {'version': '0.12.3', 'digest': 'sha256:' + '1'*64}, 'match': True}, "
                "'tika': {'expected': {'version': '4.1.0-full', 'digest': 'sha256:' + '2'*64}, 'observed': {'version': '4.1.0-full', 'digest': 'sha256:' + '2'*64}, 'match': True}"
                "}}, __import__('sys').stdout)\n",
                encoding="utf-8",
            )
            status.chmod(0o755)
            env = {
                **os.environ,
                "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                "BC250_SHARE": str(share),
                "BC250_LIBEXEC": str(libexec),
            }
            normal = subprocess.run([str(version)], env=env, text=True, capture_output=True, check=False)
            machine = subprocess.run([str(version), "--json"], env=env, text=True, capture_output=True, check=False)
            short = subprocess.run([str(version), "--short"], env=env, text=True, capture_output=True, check=False)

        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertIn(f"Package:      {CURRENT_NEVRA}", normal.stdout)
        self.assertIn("Open WebUI:", normal.stdout)
        self.assertIn("MATCH", normal.stdout)
        self.assertEqual(machine.returncode, 0, machine.stderr)
        payload = __import__("json").loads(machine.stdout)
        self.assertEqual(payload["schema"], "bc250.version.v3")
        self.assertEqual(payload["package"]["nevra"], CURRENT_NEVRA)
        self.assertTrue(payload["runtime_identity"]["open_webui"]["match"])
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertEqual(short.stdout.strip(), CURRENT_NEVRA)

    def test_version_executes_without_installed_rpm_identity(self) -> None:
        version = ROOT / "cmd/monitoring/version.py"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            bindir = base / "bin"
            share = base / "share"
            libexec = base / "libexec"
            bindir.mkdir()
            share.mkdir()
            libexec.mkdir()
            (share / "VERSION").write_text(CURRENT_VERSION + "\n", encoding="utf-8")
            (share / "runtime.env").write_text("BC250_OLLAMA_VERSION=0.40.8\n", encoding="utf-8")
            rpm = bindir / "rpm"
            rpm.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            rpm.chmod(0o755)
            status = libexec / "status-json.py"
            status.write_text("#!/usr/bin/env python3\nprint('{}')\n", encoding="utf-8")
            status.chmod(0o755)
            env = {
                **os.environ,
                "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                "BC250_SHARE": str(share),
                "BC250_LIBEXEC": str(libexec),
            }
            normal = subprocess.run([str(version)], env=env, text=True, capture_output=True, check=False)
            machine = subprocess.run([str(version), "--json"], env=env, text=True, capture_output=True, check=False)
            short = subprocess.run([str(version), "--short"], env=env, text=True, capture_output=True, check=False)

        self.assertEqual(normal.returncode, 2, normal.stderr)
        self.assertIn("Package:      unavailable", normal.stdout)
        self.assertIn("Open WebUI:", normal.stdout)
        self.assertEqual(machine.returncode, 0, machine.stderr)
        payload = __import__("json").loads(machine.stdout)
        self.assertIsNone(payload["package"]["nevra"])
        self.assertEqual(payload["runtime_identity"], {})
        self.assertEqual(short.returncode, 2, short.stderr)
        self.assertEqual(short.stdout.strip(), CURRENT_VERSION)


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
        self.assertNotIn("legacy patched " + "AMDGPU module detected", source)
        runtime_sources = source + (ROOT / "install").read_text(encoding="utf-8")
        self.assertNotRegex(
            runtime_sources,
            r"\b[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\.fc44(?:\.[A-Za-z0-9_]+)?\b",
        )

    def test_verify_reports_dependent_lane_checks_as_skipped(self) -> None:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('skipped "task model registration unavailable because ollama-task.service is inactive"', source)
        self.assertIn('skipped "document embedding registration unavailable because ollama-embedding.service is inactive"', source)
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
        source = (ROOT / "cmd/benchmark/parity-diagnose.sh").read_text(encoding="utf-8")
        self.assertIn("no model resident (--no-load requested; residency test skipped)", source)
        self.assertNotIn('wn "no model resident (start it, or run without --no-load)"', source)

    def test_mesa_reference_delta_is_informational_not_a_package_failure(self) -> None:
        source = (ROOT / "cmd/benchmark/parity-diagnose.sh").read_text(encoding="utf-8")
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
            "sudo bc250 advanced mtp prepare qwen3.8-27b-ymq-xs-ti-mtp", result.stdout
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
        source = (ROOT / "models/mtp/compare-mtp.sh").read_text(encoding="utf-8")
        self.assertIn("ollama_residency_policy=drain-only", source)
        self.assertIn("BC250_MTP_RESIDENCY_POLICY=drain-only", source)

    def test_mtp_compare_records_and_verifies_effective_draft_depth(self) -> None:
        source = (ROOT / "models/mtp/compare-mtp.sh").read_text(encoding="utf-8")
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
            "bc250 advanced benchmark generation",
            "bc250 advanced benchmark rag-cycle",
            "bc250 advanced benchmark concurrency",
            "bc250 advanced benchmark owui-system-context",
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
        self.assertIn("bc250 advanced benchmark generation", result.stdout)
        self.assertIn("bc250 advanced benchmark agent", result.stdout)
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
        diagnose = (ROOT / "cmd/benchmark/parity-diagnose.sh").read_text(encoding="utf-8")
        self.assertIn("Live routing dashboard", status)
        self.assertIn("Live SPI-routed CUs", status)
        self.assertNotIn("Kernel diagnostic active_cu_number", status)
        self.assertNotIn("RADV-reported CU count", status)
        main_status = (ROOT / "cmd/monitoring/status.sh").read_text(encoding="utf-8")
        self.assertIn("Live SPI-routed CUs", main_status)
        self.assertNotIn("Kernel diagnostic active_cu_number", main_status)
        self.assertIn('value == "S+"', status)
        self.assertIn('value == "D!"', status)
        self.assertIn("Routing profile match", verify)
        self.assertIn("configured saved profile", verify)
        self.assertIn("BC250_WGP_MASKS", status)
        self.assertIn("Saved boot profile", status)
        self.assertIn("Live routing profile", status)
        self.assertIn('[[ "$live_masks" == "$saved_masks" ]]', status)
        self.assertNotIn("modified 40-CU module", verify)
        self.assertNotIn("40/40 routed", verify)
        self.assertNotIn("partial CU routing table", verify)
        self.assertNotIn("40/40 active and routed", diagnose)

    def test_cu_routing_cell_parser_classifies_dashboard_states(self) -> None:
        source = (ROOT / "cmd/system/cu-status.sh").read_text(encoding="utf-8")
        start = source.index("routing_cells() {")
        end = source.index("\nsaved_mask_csv() {", start)
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


class FirewallVerificationTests(unittest.TestCase):
    @staticmethod
    def _helper_block() -> str:
        source = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        start = source.index("INTERNAL_FIREWALL_PORTS=(")
        end = source.index("\nif [[ ${EUID} -ne 0 ]]; then", start)
        return source[start:end]

    def test_firewall_port_parser_detects_exact_and_ranged_internal_tcp_ports(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall_port_spec_exposes_internal 11434/tcp || exit 10
firewall_port_spec_exposes_internal 11400-11500/tcp || exit 11
firewall_port_spec_exposes_internal 2999-3001/tcp || exit 12
firewall_port_spec_exposes_internal 11400-11433/tcp && exit 13
firewall_port_spec_exposes_internal 11400-11500/udp && exit 14
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_firewall_http_parser_accepts_direct_and_ranged_tcp_80(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall_port_spec_exposes_tcp_port 80/tcp 80 || exit 10
firewall_port_spec_exposes_tcp_port 70-90/tcp 80 || exit 11
firewall_port_spec_exposes_tcp_port 81-90/tcp 80 && exit 12
firewall_port_spec_exposes_tcp_port 70-90/udp 80 && exit 13
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_firewall_http_custom_service_and_rich_rules(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall-cmd() {
  case "$1" in
    --info-service=http-custom) printf '%s\n' 'http-custom' '  ports: 80/tcp' ;;
    --info-service=no-http) printf '%s\n' 'no-http' '  ports: 443/tcp' ;;
    *) return 7 ;;
  esac
}
firewalld_service_exposes_tcp_port http-custom 80 || exit 20
firewalld_service_exposes_tcp_port no-http 80 && exit 21
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" port port="80" protocol="tcp" accept' 80 || exit 22
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" port port="70-90" protocol="tcp" accept' 80 || exit 23
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" service name="http" accept' 80 || exit 24
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" service name="http-custom" accept' 80 || exit 25
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" port port="80" protocol="tcp" reject' 80 && exit 26
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" service name="no-http" accept' 80 && exit 27
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_firewall_http_service_lookup_failure_is_unverified(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall-cmd() { return 7; }
firewalld_service_exposes_tcp_port unknown-service 80
[[ $? == 2 ]] || exit 30
firewall_rich_rules_expose_tcp_port 'rule family="ipv4" service name="unknown-service" accept' 80
[[ $? == 2 ]] || exit 31
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_firewalld_custom_service_ports_are_resolved(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall-cmd() {
  case "$1" in
    --info-service=bc250-bad) printf '%s\n' 'bc250-bad' '  ports: 443/tcp 11400-11500/tcp' ;;
    --info-service=bc250-safe) printf '%s\n' 'bc250-safe' '  ports: 443/tcp' ;;
    *) return 1 ;;
  esac
}
firewalld_service_exposes_internal bc250-bad || exit 20
firewalld_service_exposes_internal bc250-safe && exit 21
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_firewalld_service_lookup_failure_is_not_treated_as_safe(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall-cmd() { return 7; }
firewalld_service_exposes_internal unknown-service
rc=$?
[[ "$rc" == 2 ]] || exit 40
firewall_rich_rules_expose_internal 'rule family="ipv4" service name="unknown-service" accept'
rc=$?
[[ "$rc" == 2 ]] || exit 41
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rich_rules_detect_ranges_and_custom_services(self) -> None:
        helpers = self._helper_block()
        command = helpers + r'''
firewall-cmd() {
  [[ "$1" == --info-service=bc250-bad ]] || return 1
  printf '%s\n' 'bc250-bad' '  ports: 9998/tcp'
}
firewall_rich_rules_expose_internal 'rule family="ipv4" port port="11400-11500" protocol="tcp" accept' || exit 30
firewall_rich_rules_expose_internal 'rule family="ipv4" service name="bc250-bad" accept' || exit 31
firewall_rich_rules_expose_internal 'rule family="ipv4" port port="11400-11433" protocol="tcp" accept' && exit 32
firewall_rich_rules_expose_internal 'rule family="ipv4" port port="11400-11500" protocol="tcp" reject' && exit 33
exit 0
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


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


    @staticmethod
    def _swap_deactivation_helpers() -> str:
        source = (ROOT / "cmd/system/swap-profile.sh").read_text(encoding="utf-8")
        start = source.index("managed_swap_is_active() {")
        end = source.index("\nensure_capacity() {", start)
        return source[start:end]

    def test_swap_lifecycle_refuses_destructive_change_when_swapoff_fails(self) -> None:
        helpers = self._swap_deactivation_helpers()
        command = helpers + r'''
SWAP_FILE=/managed/swapfile
swapon() { printf '%s\n' "$SWAP_FILE"; }
swapoff() { return 7; }
deactivate_managed_swap
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing destructive swap-file changes", result.stderr)

        source = (ROOT / "cmd/system/swap-profile.sh").read_text(encoding="utf-8")
        self.assertNotIn('swapoff "$SWAP_FILE" 2>/dev/null || true', source)
        resize = source[source.index("ensure_profile() {"):source.index("\nremove_profile() {")]
        removal = source[source.index("remove_profile() {"):source.index('\ncase "${1:-status}" in')]
        self.assertLess(resize.index("deactivate_managed_swap"), resize.index('rm -f "$SWAP_FILE"'))
        self.assertLess(removal.index("deactivate_managed_swap"), removal.index('rm -f "$SWAP_FILE"'))

    def test_swap_lifecycle_fails_closed_when_active_state_cannot_be_read(self) -> None:
        helpers = self._swap_deactivation_helpers()
        command = helpers + r'''
SWAP_FILE=/managed/swapfile
swapon() { return 5; }
swapoff() { echo unexpected-swapoff; return 0; }
deactivate_managed_swap
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot determine active swap state", result.stderr)
        self.assertNotIn("unexpected-swapoff", result.stdout)

    def test_swap_deactivation_is_noop_when_managed_swap_is_not_active(self) -> None:
        helpers = self._swap_deactivation_helpers()
        command = helpers + r'''
SWAP_FILE=/managed/swapfile
swapon() { return 0; }
swapoff() { echo unexpected-swapoff; return 9; }
deactivate_managed_swap
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("unexpected-swapoff", result.stdout)


if __name__ == "__main__":
    unittest.main()

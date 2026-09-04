from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "install"
INSTALLER = ROOT / "cmd/system/install.sh"


def source_probe(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"\n{body}', "installer-test", str(INSTALLER)],
        stdin=subprocess.DEVNULL,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


class InstallerTests(unittest.TestCase):
    def test_bootstrap_only_installs_rpm_and_hands_off(self) -> None:
        source = BOOTSTRAP.read_text()
        self.assertNotIn("dnf upgrade", source)
        self.assertIn("--setopt=install_weak_deps=False --exclude=ollama", source)
        self.assertIn("exec bc250-install", source)
        self.assertNotIn("bc250-memory-profile", source)
        self.assertLess(len(source.splitlines()), 50)

    def test_packaged_installer_is_pre_v1_greenfield_and_self_contained(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("pre-1.0", source)
        self.assertIn('readonly BC250_OLLAMA_VERSION="0.33.2"', source)
        result = subprocess.run(["bash", str(INSTALLER), "--help"], text=True, stdout=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sudo bc250-install", result.stdout)

    def test_official_ollama_install_keeps_conflict_guard(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("rpm -e --test ollama", source)
        self.assertIn("Refusing to install a second Ollama copy", source)
        self.assertIn('requested="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', source)

    def test_official_ollama_installer_is_commit_and_hash_pinned(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text()
        runtime = (ROOT / "config/runtime.env").read_text()
        self.assertIn("BC250_OLLAMA_INSTALLER_COMMIT=", runtime)
        self.assertIn("BC250_OLLAMA_INSTALLER_SHA256=", runtime)
        self.assertIn("raw.githubusercontent.com/ollama/ollama/$INSTALLER_COMMIT", helper)
        self.assertIn("Ollama installer SHA-256 mismatch", helper)
        self.assertIn("package-owned Ollama service is missing", helper)
        self.assertIn("refusing to replace custom Ollama service override", helper)
        self.assertNotIn('URL="https://ollama.com/install.sh"', helper)

    def test_one_unified_model_selection_is_used_after_required_baseline(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("bc250-model list all --all", source)
        self.assertIn('BC250_MODEL_SELECTION', source)
        self.assertIn('task-gemma3-1b-unsloth-ud-q4-k-xl,embed-jina-v5-small-retrieval-q4-k-m', source)
        self.assertIn('bc250-model install all "$selection" --include-disabled', source)
        for old in ("BC250_PRODUCTION_SELECTION", "BC250_TASK_SELECTION", "BC250_AGENTIC_SELECTION", "BC250_EMBEDDING_SELECTION", "BC250_EXPERIMENT_SELECTION", "BC250_MTP_SELECTION"):
            self.assertNotIn(old, source)

    def test_noninteractive_unselected_models_install_baseline_without_reading_stdin(self) -> None:
        result = source_probe('''
input_is_interactive() { return 1; }
require_progress_terminal() { :; }
prepare_hf_authentication() { :; }
bc250-model() { printf 'model:%s\n' "$*"; }
step_7_models
''')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("model:list all --all", result.stdout)
        self.assertIn("task-gemma3-1b-unsloth-ud-q4-k-xl,embed-jina-v5-small-retrieval-q4-k-m", result.stdout)
        self.assertIn("no additional models selected", result.stdout)
        self.assertEqual(result.stdout.count("model:install"), 1)

    def test_noninteractive_unified_selection_dispatches_once(self) -> None:
        result = source_probe('''
input_is_interactive() { return 1; }
require_progress_terminal() { :; }
prepare_hf_authentication() { :; }
bc250-model() { printf 'model:%s\\n' "$*"; }
BC250_MODEL_SELECTION='recommended,19-20'
step_7_models
''')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("model:install all recommended,19-20 --include-disabled", result.stdout)
        self.assertIn("task-gemma3-1b-unsloth-ud-q4-k-xl,embed-jina-v5-small-retrieval-q4-k-m", result.stdout)
        self.assertEqual(result.stdout.count("model:install"), 2)

    def test_original_noninteractive_input_survives_transcript_pty(self) -> None:
        result = source_probe('''
BC250_INPUT_INTERACTIVE=0
input_is_interactive && exit 9 || exit 0
''')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("BC250_INPUT_INTERACTIVE", INSTALLER.read_text())

    def test_model_download_progress_terminal_is_explicit(self) -> None:
        source = INSTALLER.read_text()
        block = source[source.index("step_7_models() {"):source.index("step_8_application_services() {")]
        self.assertIn("require_progress_terminal", block)
        self.assertLess(block.index("require_progress_terminal"), block.index("bc250-model install all"))

    def test_runtime_topology_is_established_before_model_registration(self) -> None:
        source = INSTALLER.read_text()
        main = source[source.index("main() {"):]
        order = [main.index(name) for name in (
            "step_6_runtime_topology",
            "step_7_models",
            "step_8_application_services",
            "step_9_open_webui",
            "step_10_verify",
        )]
        self.assertEqual(order, sorted(order))
        topology = source[source.index("step_6_runtime_topology() {"):source.index("step_7_models() {")]
        self.assertIn("ollama.service ollama-task.service ollama-embedding.service ollama-agent.service", topology)
        self.assertIn("systemctl enable ollama.service ollama-task.service ollama-embedding.service", topology)
        self.assertIn('FragmentPath --value "$unit"', topology)
        self.assertIn('/usr/lib/systemd/system/$unit', topology)
        self.assertIn("bc250-agent-mode leave", topology)

    def test_agent_mode_switches_static_topology_and_restores_normal(self) -> None:
        script = ROOT / "cmd/system/agent-mode.sh"
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            log = tmpdir / "systemctl.log"
            systemctl = tmpdir / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'systemctl:%s\\n' \"$*\" >> \"$BC250_TEST_LOG\"\n"
                "case \"${1:-}\" in\n"
                "  cat|start|stop|status) exit 0 ;;\n"
                "  is-active) exit 1 ;;\n"
                "esac\n"
                "exit 0\n"
            )
            curl = tmpdir / "curl"
            curl.write_text("#!/usr/bin/env bash\nexit 0\n")
            systemctl.chmod(0o755)
            curl.chmod(0o755)
            env = {
                "PATH": f"{tmpdir}:/usr/bin:/bin",
                "BC250_TEST_LOG": str(log),
            }
            result = subprocess.run(
                ["bash", "-c", 'script="$1"; set --; source "$script"; enter_agent; leave_agent', "agent-mode-test", str(script)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            calls = log.read_text()
            self.assertIn("systemctl:start ollama-agent.service", calls)
            self.assertIn("systemctl:stop ollama-agent.service", calls)
            self.assertIn(
                "systemctl:start ollama.service ollama-task.service ollama-embedding.service",
                calls,
            )


    def test_fresh_install_lifecycle_defers_open_webui_until_models(self) -> None:
        # First invocation reaches the primary reboot boundary before topology,
        # model or application phases. This is a hermetic lifecycle contract,
        # not a VM/reboot integration framework.
        first = source_probe('''
require_root() { :; }
capture_input_mode() { :; }
start_transcript() { :; }
capture_install_state() { :; }
show_plan() { printf 'phase:plan\n'; }
step_1_grow_root_filesystem() { printf 'phase:grow\n'; }
record_added_packages() { :; }
step_2_update_fedora() { printf 'phase:update\n'; }
capture_package_baseline() { :; }
step_3_install_ollama() { printf 'phase:ollama\n'; }
step_4_memory_and_swap() { printf 'phase:memory\n'; }
request_primary_reboot_if_needed() { printf 'phase:reboot\n'; exit 10; }
step_5_prepare_40cu() { printf 'UNEXPECTED:40cu\n'; }
step_6_runtime_topology() { printf 'UNEXPECTED:topology\n'; }
step_7_models() { printf 'UNEXPECTED:models\n'; }
step_8_application_services() { printf 'UNEXPECTED:applications\n'; }
main
''')
        self.assertEqual(first.returncode, 10, first.stdout)
        self.assertIn("phase:reboot", first.stdout)
        self.assertNotIn("UNEXPECTED:", first.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            log = tmpdir / "lifecycle.log"
            enable_target = tmpdir / "open-webui.container.d" / "90-enable.conf"
            enable_source = ROOT / "config/openwebui/open-webui-enable.conf"
            body = r'''
systemctl() {
  printf 'systemctl:%s\n' "$*" >> "$BC250_TEST_LOG"
  case "${1:-}" in
    cat) return 0 ;;
    show) printf '/usr/lib/systemd/system/%s\n' "${!#}"; return 0 ;;
    is-active) return 0 ;;
  esac
  return 0
}
bc250-agent-mode() { printf 'mode:%s\n' "$*" >> "$BC250_TEST_LOG"; }
bc250-model() { printf 'model:%s\n' "$*" >> "$BC250_TEST_LOG"; }
firewall-cmd() { printf 'firewall:%s\n' "$*" >> "$BC250_TEST_LOG"; }
setsebool() { :; }
require_progress_terminal() { :; }
prepare_hf_authentication() { :; }
input_is_interactive() { return 1; }
step_6_runtime_topology
step_7_models
step_8_application_services
'''
            env = {
                "PATH": "/usr/bin:/bin",
                "BC250_TEST_LOG": str(log),
                "BC250_OWUI_ENABLE_SOURCE": str(enable_source),
                "BC250_OWUI_ENABLE_DROPIN": str(enable_target),
            }
            resumed = subprocess.run(
                ["bash", "-c", 'source "$1"\n' + body, "lifecycle-test", str(INSTALLER)],
                stdin=subprocess.DEVNULL,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stdout)
            calls = log.read_text()
            baseline = calls.index(
                "model:install all task-gemma3-1b-unsloth-ud-q4-k-xl,embed-jina-v5-small-retrieval-q4-k-m"
            )
            owui = calls.index("systemctl:start tika.service open-webui.service")
            self.assertLess(baseline, owui)
            self.assertIn("mode:leave", calls)
            self.assertTrue(enable_target.is_file())
            self.assertIn("WantedBy=multi-user.target", enable_target.read_text())

    def test_setup_plan_covers_resume_decision_points(self) -> None:
        source = INSTALLER.read_text()
        block = source[source.index("show_plan() {"):source.index("wait_for_open_webui() {")]
        for label in ("root grow", "Fedora update", "Ollama", "TTM profile", "swap", "40-CU", "storage headroom", "primary reboot"):
            self.assertIn(label, block)

    def test_primary_reboot_happens_after_update_ollama_and_memory(self) -> None:
        source = INSTALLER.read_text()
        main = source[source.index("main() {"):]
        order = [main.index(name) for name in ("step_2_update_fedora", "step_3_install_ollama", "step_4_memory_and_swap", "request_primary_reboot_if_needed", "step_5_prepare_40cu")]
        self.assertEqual(order, sorted(order))

    def test_40cu_prepare_targets_running_kernel_and_second_reboot_is_conditional(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn('kernel="$(uname -r)"', source)
        self.assertIn('dnf install -y "kernel-devel-$kernel"', source)
        self.assertIn("bc250-40cu prepare", source)
        self.assertIn("/etc/modprobe.d/bc250-40cu.conf", source)
        self.assertIn("/sys/module/amdgpu/parameters/bc250_cc_write_mode", source)
        self.assertNotIn("bc250-40cu enable", source)

    def test_root_growth_skips_lvm_when_no_free_extents(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("vg_free", source)
        self.assertIn("Root LV already uses available volume-group space.", source)

    def test_fresh_marker_allows_safe_ownership_capture(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn('! -e "$STATE_DIR/fresh-package"', source)
        self.assertIn('rm -f -- "$STATE_DIR/fresh-package"', source)
        self.assertIn("firewall-http-before", source)
        self.assertIn("selinux-httpd-before", source)

    def test_verification_runs_both_reports_before_returning_failure(self) -> None:
        source = INSTALLER.read_text()
        block = source[source.index("step_10_verify() {"):source.index("run_models_only() {")]
        self.assertIn("bc250-verify || verify_status=$?", block)
        self.assertIn("llm-run-diagnose --no-load || diagnose_status=$?", block)

    def test_models_only_resume_is_public(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("sudo bc250-install [--models-only]", source)
        self.assertIn('if [[ "$INSTALL_MODE" == models ]]; then', source)
        self.assertIn("run_models_only", source)


if __name__ == "__main__":
    unittest.main()

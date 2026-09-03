from __future__ import annotations

import subprocess
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
        self.assertNotIn('URL="https://ollama.com/install.sh"', helper)

    def test_one_unified_model_selection_is_used(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("bc250-model list all --all", source)
        self.assertIn('BC250_MODEL_SELECTION', source)
        self.assertIn('bc250-model install all "$selection" --include-disabled', source)
        for old in ("BC250_PRODUCTION_SELECTION", "BC250_TASK_SELECTION", "BC250_AGENTIC_SELECTION", "BC250_EMBEDDING_SELECTION", "BC250_EXPERIMENT_SELECTION", "BC250_MTP_SELECTION"):
            self.assertNotIn(old, source)

    def test_noninteractive_unselected_models_do_not_read_stdin(self) -> None:
        result = source_probe('''
input_is_interactive() { return 1; }
bc250-model() { printf 'model:%s\\n' "$*"; }
step_7_models
''')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("model:list all --all", result.stdout)
        self.assertIn("model setup skipped in non-interactive mode", result.stdout)
        self.assertNotIn("model:install", result.stdout)

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
        self.assertEqual(result.stdout.count("model:install"), 1)

    def test_original_noninteractive_input_survives_transcript_pty(self) -> None:
        result = source_probe('''
BC250_INPUT_INTERACTIVE=0
input_is_interactive && exit 9 || exit 0
''')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("BC250_INPUT_INTERACTIVE", INSTALLER.read_text())

    def test_model_download_progress_terminal_is_explicit(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("require_progress_terminal", source)
        self.assertLess(source.index('[[ -n "$selection" ]]'), source.index("require_progress_terminal", source.index("step_7_models")))

    def test_agent_restoration_fix_is_retained(self) -> None:
        source = (ROOT / "models/setup-ollama-instance.sh").read_text()
        self.assertIn('restore_normal_services() {\n    local rc="${1:-0}"', source)
        self.assertIn("restore_normal_services 0", source)
        self.assertIn("trap - EXIT", source)

    def test_agent_restoration_status_behavior(self) -> None:
        source = (ROOT / "models/setup-ollama-instance.sh").read_text()
        start = source.index("  restore_normal_services() {")
        end = source.index("  trap 'restore_normal_services", start)
        function = source[start:end]

        def run(original_rc: int, fail_start: str = "") -> subprocess.CompletedProcess[str]:
            script = f"""
set -u
restore_normal=1
service=ollama-agent.service
FAIL_START={fail_start!r}
systemctl() {{
  action="$1"; unit="${{2:-}}"
  case "$action" in
    cat) return 0 ;;
    start) [[ "$unit" == "$FAIL_START" && -n "$FAIL_START" ]] && return 1 ;;
  esac
  return 0
}}
{function}
restore_normal_services {original_rc}
"""
            return subprocess.run(["bash", "-c", script], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

        self.assertEqual(run(0).returncode, 0)
        self.assertEqual(run(7).returncode, 7)
        failed_restore = run(0, "ollama-task.service")
        self.assertNotEqual(failed_restore.returncode, 0)
        self.assertIn("restoration incomplete", failed_restore.stdout)


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
        block = source[source.index("step_9_verify() {"):source.index("run_models_only() {")]
        self.assertIn("bc250-verify || verify_status=$?", block)
        self.assertIn("llm-run-diagnose --no-load || diagnose_status=$?", block)

    def test_models_only_resume_is_public(self) -> None:
        source = INSTALLER.read_text()
        self.assertIn("sudo bc250-install [--models-only]", source)
        self.assertIn('if [[ "$INSTALL_MODE" == models ]]; then', source)
        self.assertIn("run_models_only", source)


if __name__ == "__main__":
    unittest.main()

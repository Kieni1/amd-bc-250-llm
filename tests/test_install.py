from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "install"


def run_remove_probe(status: int) -> subprocess.CompletedProcess[str]:
    script = f"""
source "$1"
rpm() {{
  case "$*" in
    "-q ollama") return 0 ;;
    "-e --test ollama") echo "probe status {status}"; return {status} ;;
    *) return 1 ;;
  esac
}}
dnf() {{ printf 'dnf %s\\n' "$*"; }}
systemctl() {{ :; }}
remove_fedora_ollama
"""
    return subprocess.run(
        ["bash", "-c", script, "installer-test", str(INSTALLER)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def run_model_phase_probe() -> subprocess.CompletedProcess[str]:
    script = r'''
source "$1"
script() { :; }
require_progress_terminal() { printf 'progress-terminal\n'; }
bc250-model() { printf 'model:%s\n' "$*"; }
bc250-setup-task-model() { printf 'task:%s\n' "$*"; }
bc250-setup-coding-agent() { printf 'agentic:%s\n' "$*"; }
HF_TOKEN=dummy
step_7_models
'''
    return subprocess.run(
        ["bash", "-c", script, "installer-test", str(INSTALLER)],
        input="0\n0\n\n1\n\n0\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


class InstallerTests(unittest.TestCase):
    def test_rpm_transaction_excludes_fedora_ollama(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("--setopt=install_weak_deps=False", source)
        self.assertIn("--exclude=ollama", source)
        self.assertIn("dnf_action=reinstall", source)

    def test_installer_records_only_its_package_additions(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("packages-added.txt", source)
        self.assertIn('LC_ALL=C comm -13 "$PACKAGE_BASELINE" "$current"', source)
        self.assertIn('local name="$1" value="$2" path\n  path=', source)
        self.assertIn("capture_package_baseline\n  step_3_install_rpm", source)
        self.assertIn("firewall-http-before", source)
        self.assertIn("selinux-httpd-before", source)
        self.assertIn("Earlier releases did not record", source)

    def test_erasable_fedora_ollama_is_removed(self) -> None:
        result = run_remove_probe(0)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("dnf remove -y ollama", result.stdout)

    def test_required_fedora_ollama_blocks_a_second_install(self) -> None:
        result = run_remove_probe(1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to install a second Ollama copy", result.stdout)
        self.assertNotIn("dnf remove", result.stdout)

    def test_standard_ollama_version_is_used_unless_overridden(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('VERSION="${OLLAMA_VERSION:-0.32.15}"', helper)
        self.assertIn('requested="${OLLAMA_VERSION:-0.32.15}"', installer)

    def test_latest_is_not_sent_as_an_upstream_version_query(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        self.assertIn("env -u OLLAMA_VERSION sh", helper)
        self.assertIn('OLLAMA_VERSION="$VERSION" sh', helper)

    def test_model_setup_does_not_pipe_download_stderr(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        helper = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        self.assertNotIn("2> >(sed", installer)
        self.assertIn('api/tags" >/dev/null 2>&1 && break', helper)

    def test_model_setup_uses_discovered_modelfiles(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        phases = (
            "production|Production|BC250_PRODUCTION_SELECTION",
            "task|Task|BC250_TASK_SELECTION",
            "agentic|Agentic|BC250_AGENTIC_SELECTION",
            "embedding|Embedding|BC250_EMBEDDING_SELECTION",
            "experiments|Experiments|BC250_EXPERIMENT_SELECTION",
            "mtp|MTP|BC250_MTP_SELECTION",
        )
        for phase in phases:
            self.assertIn(phase, source)
        self.assertIn('bc250-model install "$category" "$selection"', source)
        self.assertIn('bc250-setup-task-model "$selection"', source)
        self.assertIn('bc250-setup-coding-agent "$selection"', source)
        self.assertIn('bc250-model list mtp --all', source)
        self.assertIn('bc250-model install mtp "$selection" --include-disabled', source)

    def test_model_categories_prompt_and_run_as_separate_phases(self) -> None:
        result = run_model_phase_probe()
        self.assertEqual(result.returncode, 0, result.stdout)
        expected_order = (
            "model:list production",
            "model:install production 0",
            "model:list task",
            "task:0",
            "model:list agentic",
            "Skipping agentic models.",
            "model:list embedding",
            "model:install embedding 1",
            "model:list experiments",
            "Skipping experiments models.",
            "model:list mtp --all",
            "model:install mtp 0 --include-disabled",
        )
        positions = [result.stdout.index(value) for value in expected_order]
        self.assertEqual(positions, sorted(positions), result.stdout)
        self.assertEqual(result.stdout.count("Using HF_TOKEN supplied"), 1)

    def test_unattended_model_setup_defaults_to_anonymous_hugging_face(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('if [[ "${BC250_ASSUME_YES:-0}" == 1 ]]; then', source)
        self.assertIn('export BC250_HF_ANONYMOUS=1', source)
        self.assertIn("HF_TOKEN is unset; using anonymous", source)

    def test_progress_terminal_is_required_only_for_selected_model_downloads(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("Fedora package: util-linux-script", source)
        self.assertIn("command -v script >/dev/null 2>&1; then", source)
        self.assertNotIn("require_progress_terminal\n  start_transcript", source)
        self.assertLess(source.index("require_progress_terminal", source.index("run_model_phase()")),
                        source.index("prepare_hf_authentication", source.index("run_model_phase()")))

    def test_tooling_helpers_require_an_explicit_model_selection(self) -> None:
        helper = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        self.assertIn("[MODEL-SELECTION]", helper)
        self.assertNotIn('SELECTION:-all', helper)
        self.assertIn('[[ -z "$selection" ]] || manager_args+=("$selection")', helper)

    def test_installer_prepares_40cu_for_the_exact_running_kernel(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('kernel="$(uname -r)"', source)
        self.assertIn('dnf install -y "kernel-devel-$kernel"', source)
        self.assertIn("bc250-40cu prepare", source)
        self.assertLess(source.index("step_6_prepare_40cu"), source.index("step_7_models"))
        self.assertNotIn("BC250_ASSUME_YES=1 bc250-40cu enable", source)

    def test_rpm_action_distinguishes_upgrade_from_same_nevra_reinstall(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('[[ "$installed_nevra" != "$candidate_nevra" ]] || dnf_action=reinstall', source)
        self.assertIn('[[ "$installed_after" == "$candidate_nevra" ]]', source)

    def test_verification_runs_both_reports_before_returning_failure(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        verify = source.index("bc250-verify || verify_status=$?")
        diagnose = source.index("llm-run-diagnose --no-load || diagnose_status=$?")
        summary = source.index("verification reported failures")
        self.assertLess(verify, diagnose)
        self.assertLess(diagnose, summary)

    def test_full_rerun_converges_managed_settings_and_deployed_models(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        helper = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        self.assertIn("/usr/share/bc250-llm-server/defaults", source)
        self.assertIn("installer-convergence", source)
        self.assertIn("Environment=RESET_CONFIG_ON_START=true", source)
        self.assertIn("bc250-model reconcile", source)
        self.assertIn('--service-only', helper)
        self.assertIn("Accounts, chats, uploads and Knowledge data were retained", source)
        self.assertIn("Operator models.d, maintenance/API secrets, HTTPS material and persistent data were retained", source)
        self.assertLess(source.index("step_3b_converge_package_defaults"), source.index("step_4_install_ollama", source.index("main()")))
        self.assertLess(source.index("step_4b_converge_existing_runtime"), source.index("step_5_memory_and_swap", source.index("main()")))

    def test_models_only_resumes_after_an_interrupted_system_setup(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("sudo ./install --models-only", source)
        self.assertIn('INSTALL_MODE="models"', source)
        self.assertIn("run_models_only()", source)
        resume = source.index(
            'if [[ "$INSTALL_MODE" == models ]]; then\n    run_models_only'
        )
        self.assertLess(resume, source.index("capture_install_state", resume))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import pty
import subprocess
import tempfile
import unittest
from pathlib import Path

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


def run_same_nevra_probe() -> subprocess.CompletedProcess[str]:
    script = r"""
source "$1"
heading() { :; }
find_binary_rpm() { printf '/tmp/bc250-current.x86_64.rpm\n'; }
rpm() {
  case "$*" in
    "-qp --qf %{NAME}-%{VERSION}-%{RELEASE}.%{ARCH} /tmp/bc250-current.x86_64.rpm")
      printf 'bc250-llm-server-0.9.7-0.11.testing.fc44.x86_64\n' ;;
    "-q --qf %{NAME}-%{VERSION}-%{RELEASE}.%{ARCH} bc250-llm-server.x86_64")
      printf 'bc250-llm-server-0.9.7-0.11.testing.fc44.x86_64\n' ;;
    "-q --provides bc250-llm-server.x86_64")
      printf 'user(ollama)\ngroup(ollama)\n' ;;
    "-q bc250-llm-server.x86_64") return 0 ;;
    *) return 1 ;;
  esac
}
dnf() { printf 'UNEXPECTED-DNF %s\n' "$*"; return 99; }
command() {
  if [[ "$1" == -v && "$2" == bc250-install-ollama ]]; then
    return 0
  fi
  builtin command "$@"
}
step_3_install_rpm
"""
    return subprocess.run(
        ["bash", "-c", script, "installer-test", str(INSTALLER)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def run_model_phase_probe() -> subprocess.CompletedProcess[str]:
    script = r"""
source "$1"
script() { :; }
require_progress_terminal() { printf 'progress-terminal\n'; }
bc250-model() { printf 'model:%s\n' "$*"; }
bc250-setup-task-model() { printf 'task:%s\n' "$*"; }
bc250-setup-coding-agent() { printf 'agentic:%s\n' "$*"; }
bc250-setup-embedding-model() { printf 'embedding:%s\n' "$*"; }
HF_TOKEN=dummy
BC250_PRODUCTION_SELECTION=0
BC250_TASK_SELECTION=0
BC250_AGENTIC_SELECTION=
BC250_EMBEDDING_SELECTION=1
BC250_EXPERIMENT_SELECTION=
BC250_MTP_SELECTION=0
step_7_models
"""
    return subprocess.run(
        ["bash", "-c", script, "installer-test", str(INSTALLER)],
        stdin=subprocess.DEVNULL,
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
        self.assertNotIn("dnf_action=reinstall", source)

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

    def test_pre_v1_green_field_policy_is_explicit(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("green-field/test appliance", source)
        self.assertIn("may reapply the reviewed project baseline", source)

    def test_standard_ollama_version_is_used_unless_overridden(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('VERSION="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', helper)
        self.assertIn('readonly BC250_OLLAMA_VERSION="0.33.2"', installer)
        self.assertIn('requested="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', installer)
        self.assertNotIn('source "$SCRIPT_DIR/config/runtime.env"', installer)

    def test_installer_help_is_self_contained_when_copied_beside_rpm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "install"
            copied.write_bytes(INSTALLER.read_bytes())
            result = subprocess.run(
                ["bash", str(copied), "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("The package standard is Ollama 0.33.2", result.stdout)

    def test_latest_is_not_sent_as_an_upstream_version_query(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        self.assertIn("env -u OLLAMA_VERSION sh", helper)
        self.assertIn('OLLAMA_VERSION="$VERSION" sh', helper)

    def test_official_ollama_installer_is_commit_and_hash_pinned(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        runtime = (ROOT / "config/runtime.env").read_text(encoding="utf-8")
        commit = "f96e7aa0513b9973a0ccc71be414c2ecb9d65b1a"
        sha256 = "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f"
        self.assertIn(f"BC250_OLLAMA_INSTALLER_COMMIT={commit}", runtime)
        self.assertIn(f"BC250_OLLAMA_INSTALLER_SHA256={sha256}", runtime)
        self.assertIn("raw.githubusercontent.com/ollama/ollama/$INSTALLER_COMMIT", helper)
        self.assertIn('[[ "$INSTALLER_COMMIT" =~ ^[0-9a-f]{40}$ ]]', helper)
        self.assertIn('[[ "$INSTALLER_SHA256" =~ ^[0-9a-f]{64}$ ]]', helper)
        self.assertIn('[[ "$actual_sha256" != "$INSTALLER_SHA256" ]]', helper)
        self.assertIn("Ollama installer SHA-256 mismatch", helper)
        self.assertNotIn('URL="https://ollama.com/install.sh"', helper)

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
        self.assertIn('bc250-setup-embedding-model "$selection"', source)
        self.assertIn("bc250-model list mtp --all", source)
        self.assertIn('bc250-model install mtp "$selection" --include-disabled', source)

    def test_noninteractive_model_categories_use_environment_selections(self) -> None:
        result = run_model_phase_probe()
        self.assertEqual(result.returncode, 0, result.stdout)
        expected_order = (
            "model:list production",
            "model:install production 0",
            "model:list task",
            "task:0",
            "model:list agentic",
            "BC250_AGENTIC_SELECTION is unset; agentic models are skipped in non-interactive mode.",
            "model:list embedding",
            "embedding:1",
            "model:list experiments",
            "BC250_EXPERIMENT_SELECTION is unset; experiments models are skipped in non-interactive mode.",
            "model:list mtp --all",
            "model:install mtp 0 --include-disabled",
        )
        positions = [result.stdout.index(value) for value in expected_order]
        self.assertEqual(positions, sorted(positions), result.stdout)
        self.assertEqual(result.stdout.count("Using HF_TOKEN supplied"), 1)

    def test_unattended_model_setup_defaults_to_anonymous_hugging_face(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('! input_is_interactive', source)
        self.assertIn("export BC250_HF_ANONYMOUS=1", source)
        self.assertIn("HF_TOKEN is unset; using anonymous", source)

    def test_original_noninteractive_input_survives_a_transcript_pty(self) -> None:
        script = r"""
source "$1"
heading() { :; }
bc250-model() { printf 'model:%s\n' "$*"; }
require_progress_terminal() { printf 'UNEXPECTED-PROGRESS\n'; }
step_7_models
"""
        env = os.environ.copy()
        env["BC250_INPUT_INTERACTIVE"] = "0"
        master_fd, slave_fd = pty.openpty()
        try:
            os.close(master_fd)
            result = subprocess.run(
                ["bash", "-c", script, "installer-test", str(INSTALLER)],
                stdin=slave_fd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=5,
                check=False,
            )
        finally:
            os.close(slave_fd)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("skipped in non-interactive mode"), 6)
        self.assertNotIn("UNEXPECTED-PROGRESS", result.stdout)

    def test_transcript_preserves_original_input_mode(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("capture_input_mode\n  start_transcript", source)
        self.assertIn('BC250_INPUT_INTERACTIVE="$BC250_INPUT_INTERACTIVE"', source)
        self.assertNotIn("|| ! -t 0", source)

    def test_noninteractive_model_setup_skips_unselected_models_without_reading(self) -> None:
        script = r"""
source "$1"
heading() { :; }
bc250-model() { printf 'model:%s\n' "$*"; }
require_progress_terminal() { printf 'UNEXPECTED-PROGRESS\n'; }
step_7_models
"""
        result = subprocess.run(
            ["bash", "-c", script, "installer-test", str(INSTALLER)],
            stdin=subprocess.DEVNULL,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("skipped in non-interactive mode"), 6)
        self.assertNotIn("UNEXPECTED-PROGRESS", result.stdout)

    def test_agent_failure_restoration_reports_restart_failures(self) -> None:
        setup = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        mode = (ROOT / "cmd/system/agent-mode.sh").read_text(encoding="utf-8")
        for source in (setup, mode):
            self.assertIn("normal-service restoration incomplete", source)
            self.assertNotIn("start_normal >/dev/null 2>&1 || true", source)
        self.assertIn("original setup failure status", setup)
        self.assertIn("incomplete after model registration", setup)
        self.assertIn("original agent-mode failure status", mode)

    def test_progress_terminal_is_required_only_for_selected_model_downloads(
        self,
    ) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("Fedora package: util-linux-script", source)
        self.assertIn("command -v script >/dev/null 2>&1; then", source)
        self.assertNotIn("require_progress_terminal\n  start_transcript", source)
        self.assertLess(
            source.index(
                "require_progress_terminal", source.index("run_model_phase()")
            ),
            source.index(
                "prepare_hf_authentication", source.index("run_model_phase()")
            ),
        )

    def test_tooling_helpers_require_an_explicit_model_selection(self) -> None:
        helper = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        self.assertIn("[MODEL-SELECTION]", helper)
        self.assertNotIn("SELECTION:-all", helper)
        self.assertIn('[[ -z "$selection" ]] || manager_args+=("$selection")', helper)

    def test_installer_prepares_40cu_for_the_exact_running_kernel(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('kernel="$(uname -r)"', source)
        self.assertIn('dnf install -y "kernel-devel-$kernel"', source)
        self.assertIn("bc250-40cu prepare", source)
        self.assertLess(
            source.index("step_6_prepare_40cu"), source.index("step_7_models")
        )
        self.assertNotIn("BC250_ASSUME_YES=1 bc250-40cu enable", source)

    def test_rpm_action_skips_same_nevra_instead_of_reinstalling(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('[[ "$installed_nevra" == "$candidate_nevra" ]]', source)
        self.assertIn("Already current:", source)
        self.assertIn("skipping RPM transaction", source)
        self.assertNotIn("dnf_action=reinstall", source)
        self.assertIn('[[ "$installed_after" == "$candidate_nevra" ]]', source)

        result = run_same_nevra_probe()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Already current:", result.stdout)
        self.assertNotIn("UNEXPECTED-DNF", result.stdout)

    def test_verification_runs_both_reports_before_returning_failure(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        verify = source.index("bc250-verify || verify_status=$?")
        diagnose = source.index("llm-run-diagnose --no-load || diagnose_status=$?")
        summary = source.index("verification reported failures")
        self.assertLess(verify, diagnose)
        self.assertLess(diagnose, summary)

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

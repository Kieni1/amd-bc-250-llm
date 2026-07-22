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

    def test_latest_is_not_sent_as_an_upstream_version_query(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        self.assertIn("env -u OLLAMA_VERSION sh", helper)
        self.assertIn('OLLAMA_VERSION="$VERSION" sh', helper)

    def test_model_setup_does_not_pipe_download_stderr(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        helper = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        self.assertNotIn("2> >(sed", installer)
        self.assertIn('api/tags" >/dev/null 2>&1 && break', helper)

    def test_installer_prepares_40cu_for_the_exact_running_kernel(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('kernel="$(uname -r)"', source)
        self.assertIn('dnf install -y "kernel-devel-$kernel"', source)
        self.assertIn("bc250-40cu prepare", source)
        self.assertLess(source.index("step_6_prepare_40cu"), source.index("step_7_models"))
        self.assertNotIn("BC250_ASSUME_YES=1 bc250-40cu enable", source)

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

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent
UNINSTALLER = ROOT / "uninstall.sh"


class UninstallerTests(unittest.TestCase):
    def test_help_is_available_without_running_the_purge(self) -> None:
        result = subprocess.run(
            [str(UNINSTALLER), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PURGE-BC250-LLM", result.stdout)

    def test_full_purge_has_bounded_destructive_targets(self) -> None:
        source = UNINSTALLER.read_text(encoding="utf-8")
        self.assertIn("packages-added.txt", source)
        self.assertIn("dnf remove -y bc250-llm-server.x86_64", source)
        self.assertIn('dnf remove -y "${installed[@]}"', source)
        self.assertNotIn("dnf autoremove", source)
        self.assertNotIn("podman system prune", source)
        self.assertNotIn("rm -rf -- / ", source)
        for path in (
            "/var/lib/bc250-llm-server",
            "/var/cache/bc250-llm-server",
            "/var/lib/open-webui",
            "/var/backups/bc250-llm-server",
            "/var/lib/ollama",
        ):
            self.assertIn(path, source)

    def test_40cu_restore_requires_a_verified_stock_backup(self) -> None:
        source = UNINSTALLER.read_text(encoding="utf-8")
        self.assertIn("module_has_unlock", source)
        self.assertIn("no verifiable stock AMDGPU backup", source)
        self.assertIn("depmod -a", source)
        self.assertIn("dracut --force --kver", source)
        self.assertIn("/etc/modprobe.d/bc250-40cu.conf", source)
        self.assertIn("/etc/dracut.conf.d/90-bc250-40cu.conf", source)
        self.assertIn("bc250-cu-live-manager.service", source)


if __name__ == "__main__":
    unittest.main()

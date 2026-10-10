from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESET = ROOT / "uninstall.sh"


class ResetTests(unittest.TestCase):
    def test_help_is_available_without_running_reset(self) -> None:
        result = subprocess.run(
            [str(RESET), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PURGE-BC250-LLM", result.stdout)
        self.assertIn("bc250 reset", result.stdout)

    def test_greenfield_reset_has_bounded_destructive_targets(self) -> None:
        source = RESET.read_text(encoding="utf-8")
        self.assertNotIn("packages-added.txt", source)
        self.assertNotIn("firewall-http-before", source)
        self.assertNotIn("selinux-httpd-before", source)
        self.assertIn("dnf remove -y bc250-llm-server.x86_64", source)
        self.assertNotIn("dnf autoremove", source)
        self.assertNotIn("podman system prune", source)
        self.assertNotIn("rm -rf -- / ", source)
        for path in (
            "/var/lib/bc250-llm-server",
            "/var/cache/bc250-llm-server",
            "/var/lib/open-webui",
            "/var/backups/bc250-llm-server",
        ):
            self.assertIn(path, source)
        self.assertIn("/srv/bc250-documents", source)

    def test_reset_removes_live_cu_manager_state_without_kernel_module_rewrites(self) -> None:
        source = RESET.read_text(encoding="utf-8")
        self.assertIn("bc250-cu-live-manager.service", source)
        self.assertIn("/etc/bc250-cu-live-manager.conf", source)
        self.assertNotIn("bc250_cc_write_mode", source)
        self.assertNotIn("dracut --force --kver", source)

    def test_reset_restores_gfx1013_before_any_destructive_reset_work(self) -> None:
        source = RESET.read_text(encoding="utf-8")
        self.assertIn('"$GFX1013" disable --reset', source)
        self.assertIn("reset is fail-closed", source)
        self.assertLess(source.index("restore_gfx1013_stock_boot"), source.index("stop_services"))
        main = source[source.index("main() {"):]
        self.assertLess(main.index("restore_gfx1013_stock_boot"), main.index("stop_services"))

    def test_reset_delegates_component_profiles_and_declares_network_ownership(self) -> None:
        source = RESET.read_text(encoding="utf-8")
        self.assertIn('"$MEMORY_PROFILE" remove', source)
        self.assertIn('"$SWAP_PROFILE" remove', source)
        self.assertIn("--remove-service=http", source)
        self.assertIn("setsebool -P httpd_can_network_connect 0", source)
        self.assertIn("Fedora upgrades and filesystem growth were not reversed", source)


if __name__ == "__main__":
    unittest.main()

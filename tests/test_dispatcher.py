from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
DISPATCHER = ROOT / "packaging/bc250"


class DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.libexec = root / "libexec"
        self.share = root / "share"
        self.doc = root / "doc"
        (self.libexec / "coding-agent").mkdir(parents=True)
        (self.share / "examples/task-model").mkdir(parents=True)
        (self.share / "examples/coding-agent").mkdir(parents=True)
        self.doc.mkdir()
        for relative in (
            "modelctl",
            "verify.sh",
            "verify-lan.sh",
            "compare-models.sh",
            "check-temp.sh",
        ):
            self._stub(self.libexec / relative, relative)
        self._stub(self.share / "examples/task-model/setup-ollama.sh", "task-setup")
        self._stub(self.share / "examples/coding-agent/setup-ollama.sh", "agent-setup")
        (self.doc / "UNINSTALL.md").write_text("uninstall\n", encoding="utf-8")
        self.environment = {
            **os.environ,
            "BC250_LIBEXEC": str(self.libexec),
            "BC250_SHARE": str(self.share),
            "BC250_DOCDIR": str(self.doc),
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _stub(path: Path, label: str) -> None:
        path.write_text(f'#!/usr/bin/env bash\nprintf \'%s\\n\' "{label}:$*"\n', encoding="utf-8")
        path.chmod(0o755)

    def run_dispatcher(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(DISPATCHER), *arguments],
            env=self.environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_fetch_compatibility_commands_select_the_right_catalog(self) -> None:
        production = self.run_dispatcher("fetch-models", "0")
        experiments = self.run_dispatcher("fetch-experiments", "all")
        mtp = self.run_dispatcher("fetch-mtp", "all")
        self.assertEqual(production.returncode, 0, production.stderr)
        self.assertEqual(experiments.returncode, 0, experiments.stderr)
        self.assertEqual(mtp.returncode, 0, mtp.stderr)
        self.assertIn("modelctl:install production 0", production.stdout)
        self.assertIn("modelctl:install experiments all", experiments.stdout)
        self.assertIn("modelctl:install mtp all", mtp.stdout)

    def test_server_and_lan_verifiers_remain_distinct(self) -> None:
        server = self.run_dispatcher("verify")
        lan = self.run_dispatcher("verify-lan", "192.0.2.10")
        self.assertIn("verify.sh:", server.stdout)
        self.assertIn("verify-lan.sh:192.0.2.10", lan.stdout)

    def test_setup_commands_keep_their_public_names(self) -> None:
        task = self.run_dispatcher("setup-task-model")
        agent = self.run_dispatcher("setup-coding-agent")
        self.assertIn("task-setup:", task.stdout)
        self.assertIn("agent-setup:", agent.stdout)

    def test_alias_invocation_uses_argv_zero(self) -> None:
        alias = Path(self.temporary.name) / "bc250-verify-lan"
        alias.symlink_to(DISPATCHER)
        result = subprocess.run(
            [str(alias), "server.example"],
            env=self.environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verify-lan.sh:server.example", result.stdout)


if __name__ == "__main__":
    unittest.main()

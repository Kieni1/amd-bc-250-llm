from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class MaintenanceTests(unittest.TestCase):
    def test_public_helper_and_conservative_office_defaults(self) -> None:
        result = subprocess.run(
            [str(ROOT / "cmd/maintenance/maintenance.sh"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("setup --defaults", result.stdout)

        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        defaults = (ROOT / "cmd/maintenance/owui-maintenance.env").read_text(
            encoding="utf-8"
        )
        self.assertIn('"maintenance|$LIBEXEC/maintenance.sh"', dispatcher)
        self.assertIn("DRY_RUN=1", defaults)
        self.assertIn("WARMUP_KEEP_ALIVE=15m", defaults)
        self.assertIn("NIGHT_POWER_ACTION=poweroff", defaults)
        self.assertIn("REQUIRE_WOL=0", defaults)

    def test_open_webui_model_baseline_enforces_qwen_non_thinking(self) -> None:
        helper = (ROOT / "cmd/maintenance/owui-model-baseline.py").read_text(encoding="utf-8")
        maintenance = (ROOT / "cmd/maintenance/maintenance.sh").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn('QWEN_MODEL = "prod-qwen35-9b-unsloth-q6-k:latest"', helper)
        self.assertIn('custom["think"] = False', helper)
        self.assertIn('/api/v1/models/model/update', helper)
        self.assertIn('/api/v1/models/create', helper)
        self.assertIn('"access_grants":', helper)
        self.assertIn('model-baseline', maintenance)
        self.assertIn('cmd/maintenance/owui-model-baseline.py\t{libexec}/owui-model-baseline.py', manifest)

    def test_backups_are_persistent_and_serialized(self) -> None:
        config_timer = (ROOT / "cmd/maintenance/owui-backup-config.timer").read_text()
        users_timer = (ROOT / "cmd/maintenance/owui-backup-users.timer").read_text()
        service = (ROOT / "cmd/maintenance/owui-maintenance@.service").read_text()
        self.assertIn("Persistent=true", config_timer)
        self.assertIn("Persistent=true", users_timer)
        self.assertIn("/usr/bin/flock --wait 1800", service)
        self.assertIn("IOSchedulingClass=idle", service)

    def test_cache_cleanup_is_explicit_and_keeps_persistent_model_data(self) -> None:
        source = (ROOT / "cmd/maintenance/maintenance.sh").read_text(encoding="utf-8")
        self.assertIn("clean-cache", source)
        self.assertIn("system-wide journal archives", source)
        self.assertIn("/var/cache/bc250-llm-server/huggingface", source)
        self.assertIn("podman image prune -f", source)
        self.assertIn("journalctl --vacuum-size=512M", source)
        self.assertNotIn("find /var/lib/bc250-llm-server/gguf", source)
        self.assertNotIn("find /var/lib/bc250-llm-server/ollama", source)

    def test_power_action_is_explicit_and_wol_is_optional(self) -> None:
        source = (ROOT / "cmd/maintenance/safe-power.sh").read_text(encoding="utf-8")
        self.assertIn("22 80 443 3000 11434 11435 11436", source)
        self.assertIn("poweroff or suspend", source)
        self.assertIn("REQUIRE_WOL", source)
        self.assertIn("active SSH, UI or Ollama TCP session", source)
        self.assertNotIn(
            "safe-suspend.sh", (ROOT / "packaging/install-manifest.tsv").read_text()
        )

    def test_pruning_disables_zero_rules_and_preserves_uncertain_metadata(self) -> None:
        script = ROOT / "cmd/maintenance/prune-uploads.sh"
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "curl"
            fake.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf '%s\\n' '[
                      {"id":"known-old","created_at":"2026-01-01T00:00:00Z","meta":{"size":2147483648}},
                      {"id":"uncertain","created_at":null,"meta":{"size":2147483648}}
                    ]'
                    """
                ),
                encoding="utf-8",
            )
            fake.chmod(0o755)
            env = os.environ | {
                "PATH": f"{temporary}:{os.environ['PATH']}",
                "OWUI_API_KEY": "test-key",
                "MAX_AGE_DAYS": "0",
                "MAX_TOTAL_GB": "1",
                "DRY_RUN": "1",
            }
            result = subprocess.run(
                [str(script)],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("WOULD delete [size-ceiling] id=known-old", result.stdout)
            self.assertNotIn("WOULD delete [size-ceiling] id=uncertain", result.stdout)
            self.assertIn("preserving uncertain metadata", result.stdout)

            env["MAX_TOTAL_GB"] = "0"
            disabled = subprocess.run(
                [str(script)],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertNotEqual(disabled.returncode, 0)
            self.assertIn("cannot both be disabled", disabled.stdout)

    def test_pruning_fetches_all_open_webui_file_pages_before_selection(self) -> None:
        script = ROOT / "cmd/maintenance/prune-uploads.sh"
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "curl"
            log = Path(temporary) / "pages.log"
            fake.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    url="${@: -1}"
                    page="${url##*page=}"
                    printf '%s\\n' "$page" >> "$CURL_LOG"
                    python3 - "$page" <<'PY'
                    import json, sys
                    page = int(sys.argv[1])
                    total = 120
                    start = (page - 1) * 50
                    stop = min(start + 50, total)
                    items = [
                        {"id": f"file-{i:03d}", "created_at": 1_700_000_000 + i, "meta": {"size": 10 * 1024 * 1024}}
                        for i in range(start, stop)
                    ]
                    print(json.dumps({"items": items, "total": total}))
                    PY
                    """
                ),
                encoding="utf-8",
            )
            fake.chmod(0o755)
            env = os.environ | {
                "PATH": f"{temporary}:{os.environ['PATH']}",
                "CURL_LOG": str(log),
                "OWUI_API_KEY": "test-key",
                "MAX_AGE_DAYS": "0",
                "MAX_TOTAL_GB": "1",
                "DRY_RUN": "1",
            }
            result = subprocess.run(
                [str(script)],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("Files=120", result.stdout)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(), ["1", "2", "3"]
            )


if __name__ == "__main__":
    unittest.main()

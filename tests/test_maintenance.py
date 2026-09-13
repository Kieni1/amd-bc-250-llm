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

    def test_companion_contract_uses_safe_shutdown_and_only_office_network_paths(self) -> None:
        maintenance = (ROOT / "cmd/maintenance/maintenance.sh").read_text(encoding="utf-8")
        companion = (ROOT / "cmd/maintenance/maintenance-companion.sh").read_text(encoding="utf-8")
        contract = (ROOT / "docs/MAINTENANCE-CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("request-shutdown", maintenance)
        self.assertIn("bc250-night-shutdown.service", maintenance)
        self.assertIn("--add-service=\"$service\"", companion)
        self.assertIn("for service in http ssh", companion)
        self.assertIn("--get-zone-of-interface", companion)
        self.assertIn("HTTP http://<BC250_HOST>/", contract)
        self.assertIn("3000", contract)
        self.assertIn("not part of the companion readiness contract", contract)
        self.assertNotIn('command="/usr/bin/sudo /usr/bin/systemctl poweroff"', companion)

    def test_backup_export_is_optional_read_only_and_publishes_group_rights(self) -> None:
        companion = (ROOT / "cmd/maintenance/maintenance-companion.sh").read_text(encoding="utf-8")
        config = (ROOT / "cmd/maintenance/backup-config.sh").read_text(encoding="utf-8")
        users = (ROOT / "cmd/maintenance/backup-users.sh").read_text(encoding="utf-8")
        self.assertIn("/usr/bin/rrsync -ro $BACKUP_ROOT/config", companion)
        self.assertIn("/usr/bin/rrsync -ro $BACKUP_ROOT/users", companion)
        self.assertIn("sudo dnf install rsync-rrsync", companion)
        self.assertIn("rollback backups:      not exported", companion)
        for producer in (config, users):
            self.assertIn("id bc250-backup-export", producer)
            self.assertIn('chgrp bc250-backup-export -- "$out" "$out.sha256"', producer)
            self.assertIn('chmod 0640 -- "$out" "$out.sha256"', producer)
            self.assertNotIn("chgrp bc250-backup-export -- \"$out\" \"$out.sha256\" || true", producer)

    def test_backup_producers_preserve_export_directory_modes_behaviorally(self) -> None:
        producers = (
            (ROOT / "cmd/maintenance/backup-config.sh", "CFG_OUT_DIR"),
            (ROOT / "cmd/maintenance/backup-users.sh", "USERS_OUT_DIR"),
        )
        for script, output_variable in producers:
            for group_present, initial_mode, expected_mode in (
                (True, 0o700, 0o750),
                (False, 0o750, 0o700),
            ):
                with (
                    self.subTest(script=script.name, group_present=group_present),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    tmp = Path(temporary)
                    fake_bin = tmp / "bin"
                    fake_bin.mkdir()
                    data = tmp / "owui"
                    data.mkdir()
                    db = data / "webui.db"
                    db.write_bytes(b"placeholder")
                    out_dir = tmp / "backup"
                    out_dir.mkdir(mode=initial_mode)
                    out_dir.chmod(initial_mode)
                    install_log = tmp / "install.args"

                    (fake_bin / "sqlite3").write_text(
                        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
                    )
                    (fake_bin / "mktemp").write_text(
                        "#!/usr/bin/env bash\nexit 97\n", encoding="utf-8"
                    )
                    (fake_bin / "getent").write_text(
                        "#!/usr/bin/env bash\n"
                        + (
                            "[[ ${1-} == group && ${2-} == bc250-backup-export ]] && exit 0\n"
                            if group_present
                            else "[[ ${1-} == group && ${2-} == bc250-backup-export ]] && exit 2\n"
                        )
                        + "exec /usr/bin/getent \"$@\"\n",
                        encoding="utf-8",
                    )
                    (fake_bin / "install").write_text(
                        "#!/usr/bin/env bash\n"
                        "printf '%s\n' \"$*\" >> \"$INSTALL_LOG\"\n"
                        "args=()\n"
                        "while (($#)); do\n"
                        "  case $1 in\n"
                        "    -o) shift 2 ;;\n"
                        "    -g) shift 2 ;;\n"
                        "    *) args+=(\"$1\"); shift ;;\n"
                        "  esac\n"
                        "done\n"
                        "exec /usr/bin/install \"${args[@]}\"\n",
                        encoding="utf-8",
                    )
                    for fake in fake_bin.iterdir():
                        fake.chmod(0o755)

                    env = os.environ | {
                        "PATH": f"{fake_bin}:{os.environ['PATH']}",
                        "OWUI_DATA": str(data),
                        "OWUI_DB": str(db),
                        output_variable: str(out_dir),
                        "INSTALL_LOG": str(install_log),
                    }
                    result = subprocess.run(
                        [str(script)],
                        env=env,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertEqual(out_dir.stat().st_mode & 0o777, expected_mode)
                    install_args = install_log.read_text(encoding="utf-8")
                    if group_present:
                        self.assertIn("-g bc250-backup-export", install_args)
                    else:
                        self.assertNotIn("bc250-backup-export", install_args)

    def test_contract_default_path_matches_installed_document_hierarchy(self) -> None:
        maintenance = (ROOT / "cmd/maintenance/maintenance.sh").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn(
            "/usr/share/doc/bc250-llm-server/docs/MAINTENANCE-CONTRACT.md",
            maintenance,
        )
        self.assertIn("docs/*.md\t{docdir}/docs/", manifest)

    def test_interactive_maintenance_values_reprompt_instead_of_aborting(self) -> None:
        script = ROOT / "cmd/maintenance/maintenance.sh"
        command = (
            "source <(sed '$d' " + str(script) + "); "
            "if ask_yes_no 'Continue' yes; then echo YES; else echo NO; fi; "
            "action=$(ask_power_action poweroff); "
            "when=$(ask_power_time 18:30); "
            "count=$(ask_nonnegative_integer 'Count' 7); "
            "printf 'ACTION=%s\nTIME=%s\nCOUNT=%s\n' \"$action\" \"$when\" \"$count\""
        )
        result = subprocess.run(
            ["bash", "-c", command],
            input="maybe\ny\ny\n2\n25:00\n19:15\nnope\n5\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Please answer yes or no.", result.stdout)
        self.assertIn("Please choose 1 for power off or 2 for suspend.", result.stdout)
        self.assertIn("Please use 24-hour HH:MM", result.stdout)
        self.assertIn("Please enter a non-negative whole number.", result.stdout)
        self.assertIn("YES", result.stdout)
        self.assertIn("ACTION=suspend", result.stdout)
        self.assertIn("TIME=19:15", result.stdout)
        self.assertIn("COUNT=5", result.stdout)

    def test_wol_interface_prompt_explains_ip_address_and_reprompts(self) -> None:
        script = ROOT / "cmd/maintenance/maintenance.sh"
        command = (
            "source <(sed '$d' " + str(script) + "); "
            "default_route_interface() { echo enp0s16f0u1; }; "
            "interface_ipv4_address() { echo 192.168.1.191; }; "
            "network_interface_exists() { [[ $1 == enp0s16f0u1 ]]; }; "
            "nic=$(ask_wol_interface); printf 'NIC=%s\n' \"$nic\""
        )
        result = subprocess.run(
            ["bash", "-c", command],
            input="n\n192.168.1.191\nenp0s16f0u1\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("detected: enp0s16f0u1", result.stdout)
        self.assertIn("address:  192.168.1.191", result.stdout)
        self.assertIn("That looks like an IP address.", result.stdout)
        self.assertIn("NIC=enp0s16f0u1", result.stdout)

    def test_open_webui_model_import_preserves_qwen_non_thinking(self) -> None:
        helper = (ROOT / "cmd/openwebui/openwebui-setup.py").read_text(encoding="utf-8")
        models = (ROOT / "config/openwebui/models.json").read_text(encoding="utf-8")
        maintenance = (ROOT / "cmd/maintenance/maintenance.sh").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn('"think": false', models)
        self.assertIn('/api/v1/models/import', helper)
        self.assertIn('openwebui/models.json', manifest)
        self.assertNotIn('model-baseline', maintenance)
        self.assertNotIn('owui-model-baseline.py', manifest)

    def test_backup_log_is_scoped_to_current_systemd_invocation(self) -> None:
        script = ROOT / "cmd/maintenance/maintenance.sh"
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            systemctl = tmp / "systemctl"
            journalctl = tmp / "journalctl"
            args_log = tmp / "journal.args"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ $1 == show ]]; then echo invocation-test; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            journalctl.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" > \"$JOURNAL_ARGS\"\n"
                "echo CURRENT-RUN\n",
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            journalctl.chmod(0o755)
            command = (
                "source <(sed '$d' " + str(script) + " ); "
                "systemd_available() { return 0; }; run_task backup-config"
            )
            result = subprocess.run(
                ["bash", "-c", command],
                env=os.environ | {
                    "PATH": f"{tmp}:{os.environ['PATH']}",
                    "JOURNAL_ARGS": str(args_log),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("CURRENT-RUN", result.stdout)
            args = args_log.read_text(encoding="utf-8")
            self.assertIn("_SYSTEMD_INVOCATION_ID=invocation-test", args)
            self.assertNotIn("-n 20", args)

    def test_prune_preflight_rejects_missing_key_without_exposing_credentials(self) -> None:
        script = ROOT / "cmd/maintenance/maintenance.sh"
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "maintenance.env"
            config.write_text(
                "OWUI_API_KEY=REPLACE_WITH_ADMIN_API_KEY\n"
                "MAX_AGE_DAYS=90\nMAX_TOTAL_GB=20\nDRY_RUN=1\n",
                encoding="utf-8",
            )
            command = (
                "source <(sed '$d' " + str(script) + " ); CONFIG="
                + str(config) + "; preflight_prune"
            )
            result = subprocess.run(
                ["bash", "-c", command],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("API key is not configured", result.stdout)
            self.assertIn("dry_run=1", result.stdout)
            self.assertNotIn("REPLACE_WITH_ADMIN_API_KEY", result.stdout)

        source = script.read_text(encoding="utf-8")
        self.assertIn("prune) preflight_prune && run_task prune-uploads", source)

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
        self.assertIn("22 80 443 3000 11434 11435 11436 11437", source)
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
                      {"id":"unknown-size-old","created_at":"2026-01-01T00:00:00Z","meta":{}},
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
            self.assertNotIn("id=unknown-size-old", "\n".join(
                line for line in result.stdout.splitlines() if "WOULD delete" in line
            ))
            self.assertIn("preserving uncertain metadata", result.stdout)

            # Exercise the age-pruning path independently: an old file with a
            # known timestamp but unknown size must still be preserved.
            env["MAX_AGE_DAYS"] = "1"
            env["MAX_TOTAL_GB"] = "0"
            aged = subprocess.run(
                [str(script)],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(aged.returncode, 0, aged.stdout)
            self.assertIn("WOULD delete [age>1d] id=known-old", aged.stdout)
            age_deletes = "\n".join(
                line for line in aged.stdout.splitlines() if "WOULD delete" in line
            )
            self.assertNotIn("id=unknown-size-old", age_deletes)
            self.assertNotIn("id=uncertain", age_deletes)

            env["MAX_AGE_DAYS"] = "0"
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

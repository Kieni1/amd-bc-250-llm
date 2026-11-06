"""Focused, hermetic MC1–MC8 safety regressions for 0.20.0-5 OPEN WIP."""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class MaintenanceReviewTests(unittest.TestCase):
    def test_mc1_knowledge_inventory_paginates_and_fails_closed(self):
        helper = ROOT / "cmd/maintenance/knowledge-prune-refs.py"
        spec = importlib.util.spec_from_file_location("mc_knowledge", helper)
        assert spec and spec.loader
        import sys
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        requests = []
        responses = {
            "/api/v1/knowledge/?page=1": '{"items":[{"id":"k1"}],"total":2}',
            "/api/v1/knowledge/?page=2": '{"items":[{"id":"k2"}],"total":2}',
            "/api/v1/knowledge/k1/files?page=1": '{"items":[{"id":"document"}],"total":1}',
            "/api/v1/knowledge/k2/files?page=1": '{"items":[{"id":"another"}],"total":1}',
        }

        def fake_open(request, timeout):
            self.assertEqual(timeout, 30)
            path = request.full_url.removeprefix("http://127.0.0.1:3000")
            requests.append(path)
            return Response(responses[path].encode())

        with patch.object(module, "urlopen", side_effect=fake_open):
            protected, count = module.inventory("http://127.0.0.1:3000", "fake-key")
        self.assertEqual((protected, count), ({"document", "another"}, 2))
        self.assertEqual(len(requests), 4)
        responses["/api/v1/knowledge/?page=2"] = '{"items":[],"total":2}'
        with (
            patch.object(module, "urlopen", side_effect=fake_open),
            self.assertRaises(module.InventoryError),
        ):
            module.inventory("http://127.0.0.1:3000", "fake-key")
        with self.assertRaises(module.InventoryError):
            module.require_page({"items": [], "total": None})

    def test_mc1_deletes_only_files_not_in_knowledge(self):
        script = ROOT / "cmd/maintenance/prune-uploads.sh"
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            fake_curl = tmp / "curl"
            calls = tmp / "calls"
            fake_curl.write_text(textwrap.dedent('''\
                #!/usr/bin/env bash
                printf '%s\n' "$*" >> "$CALLS"
                if [[ "$*" == *" -X DELETE "* ]]; then exit 0; fi
                url="${@: -1}"
                if [[ "$url" == *"page=1"* ]]; then
                  printf '%s\n' '[{"id":"linked","created_at":1700000000,"meta":{"size":100}},{"id":"orphan","created_at":1700000000,"meta":{"size":100}}]'
                else printf '%s\n' '[]'; fi
            '''))
            fake_curl.chmod(0o755)
            helper = tmp / "refs.py"
            helper.write_text('import sys\nopen(sys.argv[1], "w").write("linked\\n")\n')
            result = subprocess.run(["bash", str(script)], env=os.environ | {
                "PATH": str(tmp) + ":" + os.environ["PATH"],
                "CALLS": str(calls), "OWUI_API_KEY": "fake", "DRY_RUN": "0",
                "MAX_AGE_DAYS": "1", "MAX_TOTAL_GB": "0",
                "OWUI_API_KEY_FILE": str(tmp / "absent"),
                "BC250_KNOWLEDGE_PRUNE_HELPER": str(helper),
            }, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PROTECTED Knowledge-linked file id=linked", result.stdout)
            delete_calls = [line for line in calls.read_text().splitlines() if "-X DELETE" in line]
            self.assertEqual(len(delete_calls), 1)
            self.assertIn("/orphan", delete_calls[0])
            self.assertNotIn("/linked", delete_calls[0])

    def test_mc1_protected_bytes_do_not_trigger_size_ceiling_deletion(self):
        script = ROOT / "cmd/maintenance/prune-uploads.sh"
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            calls = tmp / "calls"
            fake_curl = tmp / "curl"
            fake_curl.write_text(textwrap.dedent('''\
                #!/usr/bin/env bash
                if [[ "$*" == *" -X DELETE "* ]]; then
                  printf '%s\n' "$*" >> "$CALLS"
                  exit 0
                fi
                url="${@: -1}"
                if [[ "$url" == *"page=1"* ]]; then
                  printf '%s\n' '[{"id":"linked","created_at":1700000000,"meta":{"size":23622320128}},{"id":"orphan","created_at":1700000000,"meta":{"size":1024}}]'
                else printf '%s\n' '[]'; fi
            '''))
            fake_curl.chmod(0o755)
            helper = tmp / "refs.py"
            helper.write_text('import sys\nopen(sys.argv[1], "w").write("linked\\n")\n')
            result = subprocess.run(["bash", str(script)], env=os.environ | {
                "PATH": str(tmp) + ":" + os.environ["PATH"],
                "CALLS": str(calls), "OWUI_API_KEY": "fake", "DRY_RUN": "0",
                "MAX_AGE_DAYS": "0", "MAX_TOTAL_GB": "20",
                "OWUI_API_KEY_FILE": str(tmp / "absent"),
                "BC250_KNOWLEDGE_PRUNE_HELPER": str(helper),
            }, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("eligible_known_total=1KiB", result.stdout)
            self.assertFalse(calls.exists(), "the protected 22GiB must not force deletion of the 1KiB attachment")

    def test_mc2_documents_backup_captures_source_and_verifies(self):
        script = ROOT / "cmd/maintenance/backup-documents.sh"
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            corpus = tmp / "corpus"
            (corpus / "sources").mkdir(parents=True)
            (corpus / "active").mkdir()
            (corpus / "superseded").mkdir()
            (corpus / "sources" / "sample.pdf").write_bytes(b"example")
            (corpus / "active" / "sample.md").write_text("approved")
            (corpus / "collection.json").write_text('{"scope":"test"}')
            out = tmp / "backups"
            result = subprocess.run(["bash", str(script)], env=os.environ | {
                "BC250_DOCUMENT_ROOT": str(corpus), "DOCS_OUT_DIR": str(out),
                "BC250_BACKUP_EXPORT_GROUP": "nonexistent-bc250-export-group",
                "BC250_BACKUP_EXPORT_USER": "nonexistent-bc250-export-user",
            }, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            archives = list(out.glob("bc250-documents-*.tar.gz"))
            self.assertEqual(len(archives), 1)
            self.assertTrue(archives[0].with_name(archives[0].name + ".sha256").exists())
            with tarfile.open(archives[0], "r:gz") as archive:
                self.assertIn("./sources/sample.pdf", archive.getnames())
                self.assertIn("./active/sample.md", archive.getnames())
                self.assertIn("./collection.json", archive.getnames())
            (corpus / "active" / "unsafe").symlink_to("/etc/passwd")
            bad = subprocess.run(["bash", str(script)], env=os.environ | {
                "BC250_DOCUMENT_ROOT": str(corpus), "DOCS_OUT_DIR": str(out),
                "BC250_BACKUP_EXPORT_GROUP": "nonexistent-bc250-export-group",
            }, capture_output=True, text=True, check=False)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("does not allow links", bad.stderr)

    def test_mc6_identity_restore_keeps_wal_and_requires_checkpoint(self):
        # MC5 staging is covered by executing the scripts in
        # test_backup_roundtrip_02005.py; only the WAL rule stays a source check.
        users = (ROOT / "cmd/maintenance/restore-users.sh").read_text()
        self.assertNotIn('rm -f -- "$DB-wal" "$DB-shm"', users)
        self.assertIn('[[ "${checkpoint%%|*}" == 0 ]]', users)

    def test_mc7_mc8_wol_and_firewall_safety(self):
        companion = (ROOT / "cmd/maintenance/maintenance-companion.sh").read_text()
        self.assertIn('systemctl enable --now sshd.service', companion)
        self.assertNotIn('systemctl enable --now sshd.service firewalld.service', companion)
        maint = (ROOT / "cmd/maintenance/maintenance.sh").read_text()
        self.assertNotIn('disable_units "${OPTIONAL_TIMERS[@]}" bc250-enable-wol.service', maint)
        self.assertNotIn('disable_units "${ALL_TIMERS[@]}" bc250-enable-wol.service', maint)
        self.assertIn('run_task backup-config || failed=1', maint)
        self.assertIn('run_task backup-users || failed=1', maint)
        self.assertIn('run_task backup-documents || failed=1', maint)
        self.assertIn('older than 48 hours', maint)
        self.assertIn('current_time="$(sed', maint)

    def test_mc2_mc4_package_manifest_and_pi_examples(self):
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text()
        for name in ["knowledge-prune-refs.py", "pull-bc250-backups.sh", "request-bc250-shutdown.sh"]:
            self.assertIn(name, manifest)
        self.assertIn("backup-documents", (ROOT / "cmd/maintenance/maintenance.sh").read_text())
        self.assertTrue((ROOT / "config/systemd/maintenance/owui-backup-documents.timer").exists())
        self.assertIn("bc250-documents", (ROOT / "cmd/maintenance/maintenance-companion.sh").read_text())
        self.assertIn("sha256sum --check", (ROOT / "examples/raspi-wol/pull-bc250-backups.sh").read_text())
        self.assertIn("StrictHostKeyChecking yes", (ROOT / "examples/raspi-wol/bc250-pi-ssh-config.example").read_text())
        self.assertIn("BC250_READINESS_URL", (ROOT / "examples/raspi-wol/wake-bc250.sh").read_text())


if __name__ == "__main__":
    unittest.main()

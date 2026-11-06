"""Hermetic behaviour tests for the 0.20.0-5 backup chain (T5.1–T5.3, T5.5).

They execute the real scripts with small fakes on PATH (sqlite3, rsync, ssh,
date, systemctl, id/chgrp) instead of asserting on source text.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAINT = ROOT / "cmd/maintenance"
PI_PULL = ROOT / "examples/raspi-wol/pull-bc250-backups.sh"

SQLITE_SHIM = f"""#!{sys.executable}
# Minimal sqlite3 CLI: ".timeout N", ".backup 'path'" and plain SQL.
import re, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
for command in sys.argv[2:]:
    if command.startswith(".timeout"):
        con.execute("PRAGMA busy_timeout=%d" % int(command.split()[1]))
    elif command.startswith(".backup"):
        target = sqlite3.connect(re.fullmatch(r"\\.backup '(.*)'", command).group(1))
        con.backup(target)
        target.close()
    else:
        for row in con.execute(command):
            print("|".join(str(value) for value in row))
        con.commit()
"""

# rsync stand-in for "bc250-<kind>:/ <dest>/": copy changed files via a temp
# name plus rename (new inode, like real rsync), skip dot entries, delete extras.
RSYNC_SHIM = f"""#!{sys.executable}
import os, shutil, sys
src, dest = sys.argv[-2], sys.argv[-1]
kind = src.split(":", 1)[0].removeprefix("bc250-")
remote = os.path.join(os.environ["FAKE_REMOTE"], kind)
if not os.path.isdir(remote):
    sys.exit(23)
os.makedirs(dest, exist_ok=True)
wanted = set()
for name in os.listdir(remote):
    if name.startswith("."):
        continue
    wanted.add(name)
    s, d = os.path.join(remote, name), os.path.join(dest, name)
    st = os.stat(s)
    if os.path.exists(d) and os.stat(d).st_size == st.st_size and int(os.stat(d).st_mtime) == int(st.st_mtime):
        continue
    tmp = os.path.join(dest, "." + name + ".tmp")
    shutil.copyfile(s, tmp)
    os.utime(tmp, (st.st_atime, st.st_mtime))
    os.replace(tmp, d)
for name in os.listdir(dest):
    if not name.startswith(".") and name not in wanted:
        os.unlink(os.path.join(dest, name))
"""

DATE_SHIM = """#!/usr/bin/env bash
# Deterministic, increasing snapshot stamps; other formats use the real date.
if [[ "${1:-}" == "+%F_%H%M%S" ]]; then
  n=$(( $(cat "$DATE_COUNTER" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$DATE_COUNTER"
  printf '2026-11-%02d_182000\\n' "$n"
else
  exec /usr/bin/date "$@"
fi
"""


def write_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def publish_pair(directory: Path, name: str, payload: bytes, sidecar: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(payload)
    if sidecar:
        digest = hashlib.sha256(payload).hexdigest()
        (directory / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")


class ConfigBackupRestoreRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        write_exe(self.bin / "sqlite3", SQLITE_SHIM)
        write_exe(self.bin / "systemctl", "#!/usr/bin/env bash\nexit 3\n")
        self.data = self.tmp / "open-webui"
        (self.data / "uploads").mkdir(parents=True)
        (self.data / "uploads" / "attachment.bin").write_bytes(b"bulky")
        (self.data / "config.json").write_text('{"v":1}', encoding="utf-8")
        con = sqlite3.connect(self.data / "webui.db")
        con.execute("CREATE TABLE user (id TEXT, name TEXT)")
        con.execute("INSERT INTO user VALUES ('u1', 'original')")
        con.commit()
        con.close()
        self.out = self.tmp / "backups" / "config"
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "OWUI_DATA": str(self.data),
            "CFG_OUT_DIR": str(self.out),
            "CFG_ROLLBACK_DIR": str(self.tmp / "rollback"),
            "BC250_BACKUP_EXPORT_USER": "nonexistent-bc250-export-user",
            "BC250_BACKUP_EXPORT_GROUP": "nonexistent-bc250-export-group",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def backup(self, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(MAINT / "backup-config.sh")], env=env or self.env,
                              capture_output=True, text=True, check=False)

    def restore(self, archive: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", 'source "$1"; require_root(){ :; }; main "$2"', "restore",
             str(MAINT / "restore-config.sh"), str(archive)],
            env=self.env | {"CONFIRM_RESTORE": "YES"}, capture_output=True, text=True, check=False)

    def test_backup_publishes_pair_outside_stage_and_restore_round_trips(self) -> None:
        stage_root = self.tmp / "backups" / ".stage"
        stale = [stage_root / ".backup-stage.stale", self.out / ".backup-stage.legacy"]
        for path in stale:
            path.mkdir(parents=True)
            os.utime(path, (time.time() - 3 * 86400,) * 2)
        fresh = stage_root / ".backup-stage.running"
        fresh.mkdir()

        result = self.backup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archives = sorted(self.out.glob("owui-config-*.tar.gz"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         [archives[0].name, archives[0].name + ".sha256"],
                         "the export scope holds only published pairs, no staging")
        subprocess.run(["sha256sum", "--check", "--strict", "--status", archives[0].name + ".sha256"],
                       cwd=self.out, check=True)
        self.assertFalse(any(p.exists() for p in stale), "stages older than a day are removed")
        self.assertTrue(fresh.exists(), "a possibly running stage is left alone")
        with tarfile.open(archives[0]) as bundle:
            names = bundle.getnames()
        self.assertIn("./webui.db", names)
        self.assertFalse(any("uploads" in name for name in names))

        (self.data / "config.json").write_text('{"v":2}', encoding="utf-8")
        (self.data / "stray.txt").write_text("added after backup", encoding="utf-8")
        con = sqlite3.connect(self.data / "webui.db")
        con.execute("UPDATE user SET name='changed'")
        con.commit()
        con.close()

        restored = self.restore(archives[0])
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertEqual((self.data / "config.json").read_text(encoding="utf-8"), '{"v":1}')
        self.assertFalse((self.data / "stray.txt").exists())
        self.assertEqual((self.data / "uploads" / "attachment.bin").read_bytes(), b"bulky")
        con = sqlite3.connect(self.data / "webui.db")
        self.assertEqual(con.execute("SELECT name FROM user").fetchone()[0], "original")
        con.close()
        rollbacks = list((self.tmp / "rollback").glob("owui-config-pre-restore-*.tar.gz"))
        self.assertEqual(len(rollbacks), 1)
        self.assertTrue(Path(str(rollbacks[0]) + ".sha256").exists())

    def test_restore_refuses_a_tampered_archive_without_touching_data(self) -> None:
        self.assertEqual(self.backup().returncode, 0)
        archive = next(self.out.glob("owui-config-*.tar.gz"))
        with archive.open("ab") as handle:
            handle.write(b"tamper")
        (self.data / "config.json").write_text('{"v":"live"}', encoding="utf-8")
        result = self.restore(archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.data / "config.json").read_text(encoding="utf-8"), '{"v":"live"}')

    def test_export_group_rights_are_set_before_publication(self) -> None:
        log = self.tmp / "chgrp.log"
        write_exe(self.bin / "id", "#!/usr/bin/env bash\nexit 0\n")
        write_exe(self.bin / "chgrp", f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{log}"\n')
        result = self.backup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive = next(self.out.glob("owui-config-*.tar.gz"))
        for path in (archive, Path(str(archive) + ".sha256")):
            self.assertEqual(path.stat().st_mode & 0o777, 0o640, path)
        self.assertIn("nonexistent-bc250-export-group", log.read_text(encoding="utf-8"))
        self.assertNotIn(str(self.out), log.read_text(encoding="utf-8"),
                         "rights are applied in staging, before the pair becomes visible")


class DocumentBackupBehaviour(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.corpus = self.tmp / "corpus"
        (self.corpus / "sources").mkdir(parents=True)
        (self.corpus / "active").mkdir()
        (self.corpus / "sources" / "sample.pdf").write_bytes(b"%PDF example")
        (self.corpus / "active" / "sample.md").write_text("approved", encoding="utf-8")
        self.out = self.tmp / "backups" / "documents"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "BC250_DOCUMENT_ROOT": str(self.corpus),
            "DOCS_OUT_DIR": str(self.out),
            "BC250_BACKUP_EXPORT_USER": "nonexistent-bc250-export-user",
            "BC250_BACKUP_EXPORT_GROUP": "nonexistent-bc250-export-group",
            "BC250_BACKUP_RESERVE_MB": "0",
            "BC250_BACKUP_RETRY_DELAY": "0",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_backup(self, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(MAINT / "backup-documents.sh")], env=self.env | extra,
                              capture_output=True, text=True, check=False)

    def archives(self) -> list[Path]:
        return sorted(self.out.glob("bc250-documents-*.tar.gz"))

    def test_round_trip_then_unchanged_skip_then_change_writes_new_archive(self) -> None:
        first = self.run_backup()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        [archive] = self.archives()
        extracted = self.tmp / "extracted"
        extracted.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(extracted, filter="data")
        self.assertEqual((extracted / "sources" / "sample.pdf").read_bytes(), b"%PDF example")
        self.assertEqual((extracted / "active" / "sample.md").read_text(encoding="utf-8"), "approved")

        state = self.tmp / "backups" / ".stage" / "documents.state"
        os.utime(state, (time.time() - 3600,) * 2)
        before = state.stat().st_mtime
        skipped = self.run_backup()
        self.assertEqual(skipped.returncode, 0, skipped.stdout + skipped.stderr)
        self.assertIn("unchanged", skipped.stdout)
        self.assertEqual(self.archives(), [archive], "an unchanged corpus adds no archive")
        self.assertGreater(state.stat().st_mtime, before, "the freshness marker is renewed")

        (self.corpus / "active" / "second.md").write_text("new", encoding="utf-8")
        time.sleep(1.1)  # distinct archive timestamp
        changed = self.run_backup()
        self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
        self.assertEqual(len(self.archives()), 2)

    def test_skip_is_refused_when_the_last_archive_no_longer_verifies(self) -> None:
        self.assertEqual(self.run_backup().returncode, 0)
        [archive] = self.archives()
        with archive.open("ab") as handle:
            handle.write(b"bitrot")
        time.sleep(1.1)
        again = self.run_backup()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertNotIn("unchanged", again.stdout)
        self.assertEqual(len(self.archives()), 2)

    def test_insufficient_space_writes_nothing(self) -> None:
        result = self.run_backup(BC250_BACKUP_RESERVE_MB=str(1 << 40))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not enough space", result.stderr)
        self.assertEqual(self.archives(), [])

    def test_change_during_archive_is_retried_and_published_consistently(self) -> None:
        flag = self.tmp / "changed-once"
        write_exe(self.bin / "tar", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [[ ! -e "{flag}" ]]; then
              touch "{flag}"
              printf 'late import' > "{self.corpus}/active/late.md"
            fi
            exec /usr/bin/tar "$@"
            """))
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("changed during backup attempt 1", result.stderr)
        [archive] = self.archives()
        with tarfile.open(archive) as bundle:
            self.assertIn("./active/late.md", bundle.getnames())


class PiPullBehaviour(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        write_exe(self.bin / "rsync", RSYNC_SHIM)
        write_exe(self.bin / "ssh", "#!/usr/bin/env bash\nexit 0\n")
        write_exe(self.bin / "date", DATE_SHIM)
        self.remote = self.tmp / "bc250"
        self.base = self.tmp / "pi"
        ssh_config = self.tmp / "ssh_config"
        ssh_config.write_text("Host *\n", encoding="utf-8")
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_REMOTE": str(self.remote),
            "DATE_COUNTER": str(self.tmp / "date-counter"),
            "BC250_PI_BACKUP_DIR": str(self.base),
            "BC250_PI_SSH_CONFIG": str(ssh_config),
            "BC250_PI_BACKUP_SCOPES": "config documents",
        }
        publish_pair(self.remote / "config", "owui-config-2026-11-01_174500.tar.gz", b"cfg-1")
        publish_pair(self.remote / "documents", "bc250-documents-2026-11-01_180500.tar.gz", b"D" * 4096)
        (self.remote / "config" / ".backup-stage.x").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def pull(self, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(PI_PULL)], env=self.env | extra,
                              capture_output=True, text=True, check=False)

    def snapshots(self) -> list[Path]:
        return sorted(p for p in self.base.iterdir() if p.name.startswith("2026-"))

    def test_repeated_pulls_share_inodes_instead_of_copying(self) -> None:
        for _ in range(2):
            result = self.pull()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        first, second = self.snapshots()
        name = "documents/bc250-documents-2026-11-01_180500.tar.gz"
        self.assertEqual((first / name).stat().st_ino, (second / name).stat().st_ino)
        self.assertEqual((self.base / "mirror" / name).stat().st_ino, (first / name).stat().st_ino)
        self.assertFalse(any(p.name.startswith(".") for p in (self.base / "mirror" / "config").iterdir()))

        # A rotated-out archive stays in older snapshots after the mirror drops it.
        old = self.remote / "config" / "owui-config-2026-11-01_174500.tar.gz"
        old.unlink()
        Path(str(old) + ".sha256").unlink()
        publish_pair(self.remote / "config", "owui-config-2026-11-02_174500.tar.gz", b"cfg-2")
        self.assertEqual(self.pull().returncode, 0)
        self.assertTrue((first / "config" / old.name).exists())
        self.assertFalse((self.base / "mirror" / "config" / old.name).exists())

    def test_archive_without_sidecar_is_skipped_not_fatal(self) -> None:
        publish_pair(self.remote / "documents", "bc250-documents-2026-11-02_180500.tar.gz", b"partial",
                     sidecar=False)
        result = self.pull()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no sidecar yet", result.stderr)
        [snapshot] = self.snapshots()
        self.assertFalse((snapshot / "documents" / "bc250-documents-2026-11-02_180500.tar.gz").exists())
        self.assertTrue((snapshot / "documents" / "bc250-documents-2026-11-01_180500.tar.gz").exists())

    def test_checksum_mismatch_fails_and_records_no_snapshot(self) -> None:
        (self.remote / "config" / "owui-config-2026-11-01_174500.tar.gz").write_bytes(b"cfg-X")
        result = self.pull()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertEqual(self.snapshots(), [])
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.startswith(".pull.")], [])

    def test_scope_without_any_verified_pair_fails(self) -> None:
        result = self.pull(BC250_PI_BACKUP_SCOPES="config users")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshots(), [])

    def test_retention_keeps_only_the_newest_snapshots(self) -> None:
        for _ in range(3):
            self.assertEqual(self.pull(BC250_PI_BACKUP_KEEP="2").returncode, 0)
        self.assertEqual([p.name for p in self.snapshots()], ["2026-11-02_182000", "2026-11-03_182000"])
        self.assertTrue((self.base / "mirror").is_dir())


class PruneDryRunFidelity(unittest.TestCase):
    """T5.5: a dry run plans exactly the deletions a real run performs."""

    def test_dry_run_candidates_equal_real_deletions(self) -> None:
        old, recent = 1_600_000_000, int(time.time())
        listing = (
            f'[{{"id":"linked-old","created_at":{old},"meta":{{"size":10}}}},'
            f'{{"id":"orphan-old","created_at":{old},"meta":{{"size":10}}}},'
            f'{{"id":"orphan-big","created_at":{recent - 60},"meta":{{"size":3221225472}}}},'
            f'{{"id":"linked-big","created_at":{recent - 120},"meta":{{"size":3221225472}}}},'
            f'{{"id":"recent","created_at":{recent},"meta":{{"size":10}}}}]'
        )
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            calls = tmp / "calls"
            write_exe(tmp / "curl", textwrap.dedent(f"""\
                #!/usr/bin/env bash
                if [[ "$*" == *" -X DELETE "* ]]; then printf '%s\\n' "${{@: -1}}" >> "{calls}"; exit 0; fi
                if [[ "${{@: -1}}" == *"page=1"* ]]; then printf '%s\\n' '{listing}'; else echo '[]'; fi
                """))
            helper = tmp / "refs.py"
            helper.write_text('import sys\nopen(sys.argv[1], "w").write("linked-old\\nlinked-big\\n")\n',
                              encoding="utf-8")
            env = os.environ | {
                "PATH": f"{tmp}:{os.environ['PATH']}", "OWUI_API_KEY": "fake",
                "OWUI_API_KEY_FILE": str(tmp / "absent"), "MAX_AGE_DAYS": "30", "MAX_TOTAL_GB": "2",
                "BC250_KNOWLEDGE_PRUNE_HELPER": str(helper),
            }
            script = str(MAINT / "prune-uploads.sh")
            dry = subprocess.run(["bash", script], env=env | {"DRY_RUN": "1"},
                                 capture_output=True, text=True, check=False)
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
            self.assertFalse(calls.exists())
            planned = sorted(line.split("id=")[1].split()[0]
                             for line in dry.stdout.splitlines() if "WOULD delete" in line)
            real = subprocess.run(["bash", script], env=env | {"DRY_RUN": "0"},
                                  capture_output=True, text=True, check=False)
            self.assertEqual(real.returncode, 0, real.stdout + real.stderr)
            deleted = sorted(url.rsplit("/", 1)[1] for url in calls.read_text().splitlines())
            self.assertEqual(planned, deleted)
            self.assertEqual(planned, ["orphan-big", "orphan-old"])

    def test_dry_run_reports_unverifiable_knowledge_and_plans_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            write_exe(tmp / "curl", textwrap.dedent("""\
                #!/usr/bin/env bash
                if [[ "${@: -1}" == *"page=1"* ]]; then
                  echo '[{"id":"orphan-old","created_at":1600000000,"meta":{"size":10}}]'
                else echo '[]'; fi
                """))
            helper = tmp / "refs.py"
            helper.write_text("raise SystemExit(1)\n", encoding="utf-8")
            result = subprocess.run(["bash", str(MAINT / "prune-uploads.sh")], env=os.environ | {
                "PATH": f"{tmp}:{os.environ['PATH']}", "OWUI_API_KEY": "fake",
                "OWUI_API_KEY_FILE": str(tmp / "absent"), "MAX_AGE_DAYS": "30", "MAX_TOTAL_GB": "0",
                "BC250_KNOWLEDGE_PRUNE_HELPER": str(helper), "DRY_RUN": "1",
            }, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("a real run would abort", result.stdout)
            self.assertNotIn("WOULD delete", result.stdout)


if __name__ == "__main__":
    unittest.main()

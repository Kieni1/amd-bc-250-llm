#!/usr/bin/env bash
# Full stopped-state Open WebUI rollback snapshot before a version migration.
set -Eeuo pipefail
umask 0077

DATA="${OWUI_DATA:-/var/lib/open-webui}"
DB="${OWUI_DB:-$DATA/webui.db}"
OUT_DIR="${OWUI_UPGRADE_BACKUP_DIR:-/var/backups/bc250-llm-server/rollback/openwebui}"
FROM_VERSION="${1:-unknown}"
TO_VERSION="${2:-unknown}"

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: run as root." >&2; exit 1; }
[[ -d "$DATA" && -f "$DB" ]] || { echo "ERROR: existing Open WebUI data/DB missing; no upgrade snapshot created." >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERROR: sqlite3 is required." >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 is required." >&2; exit 1; }
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet open-webui.service 2>/dev/null; then
  echo "ERROR: open-webui.service must be stopped before a full migration snapshot." >&2
  exit 1
fi
[[ "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: live Open WebUI SQLite database failed integrity_check." >&2
  exit 1
}

install -d -m0700 "$OUT_DIR"
tmpdir="$(mktemp -d "$OUT_DIR/.upgrade-backup.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT
archive_tmp="$tmpdir/archive.tar.gz"
stamp="$(date +%F_%H%M%S)"
safe_from="${FROM_VERSION//[^A-Za-z0-9._-]/_}"
safe_to="${TO_VERSION//[^A-Za-z0-9._-]/_}"
out="$OUT_DIR/openwebui-${safe_from}-to-${safe_to}-${stamp}.tar.gz"

# Service is stopped, so the complete package-owned persistent tree can be copied
# consistently, including uploads, vector data and any migration-relevant sidecars.
tar --xattrs --acls --numeric-owner -C "$(dirname -- "$DATA")" \
  -czf "$archive_tmp" "$(basename -- "$DATA")"
tar -tzf "$archive_tmp" >/dev/null
python3 - "$archive_tmp" "$(basename -- "$DATA")/webui.db" <<'PY'
import pathlib
import sys
import tarfile

archive_path, expected_db = sys.argv[1:]
seen_db = False
with tarfile.open(archive_path, "r:gz") as archive:
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe backup member: {member.name}")
        if not (member.isdir() or member.isfile()):
            raise SystemExit(f"unsupported backup member: {member.name}")
        if member.name.rstrip("./") == expected_db:
            seen_db = True
if not seen_db:
    raise SystemExit("upgrade backup does not contain webui.db")
PY

mv -- "$archive_tmp" "$out"
sha256sum "$out" > "$out.sha256"
sha256sum -c "$out.sha256" >/dev/null
chmod 0600 "$out" "$out.sha256"
printf 'Verified Open WebUI pre-migration rollback snapshot: %s\n' "$out"

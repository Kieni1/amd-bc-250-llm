#!/usr/bin/env bash
# Restore an identity backup only into the same Open WebUI schema revision.
set -Eeuo pipefail
umask 0077
DB="${OWUI_DB:-/var/lib/open-webui/webui.db}"
SRC="${1:?Usage: restore-users.sh <owui-users-*.sql.gz>}"
ROLLBACK_DIR="${USERS_ROLLBACK_DIR:-/var/backups/bc250-llm-server/rollback/users}"
FORCE_SCHEMA_MISMATCH="${FORCE_SCHEMA_MISMATCH:-0}"

[[ ${EUID} -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ -f "$DB" && -r "$SRC" ]] || { echo "ERROR: DB or backup missing." >&2; exit 1; }
for cmd in sqlite3 gzip zcat python3 sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done
gzip -t "$SRC"
if [[ -f "$SRC.sha256" ]]; then
  ( cd "$(dirname "$SRC")" && sha256sum --check --strict "$(basename "$SRC").sha256" )
fi
if systemctl is-active --quiet open-webui.service 2>/dev/null; then
  echo "ERROR: stop Open WebUI before restoring: sudo systemctl stop open-webui" >&2
  exit 1
fi

backup_rev="$(python3 - "$SRC" <<'PY_REV'
import gzip, sys
revision = ""
with gzip.open(sys.argv[1], "rt", encoding="utf-8") as src:
    for line in src:
        if line.startswith("-- OWUI_SCHEMA_REVISION="):
            revision = line.split("=", 1)[1].strip()
            break
print(revision)
PY_REV
)"
current_rev="$(sqlite3 "$DB" "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || true)"
[[ -n "$backup_rev" && -n "$current_rev" ]] || {
  echo "ERROR: missing Open WebUI schema revision in backup or database." >&2
  exit 1
}
if [[ "$backup_rev" != "$current_rev" && "$FORCE_SCHEMA_MISMATCH" != "1" ]]; then
  printf 'ERROR: schema mismatch (backup=%q current=%q). Refusing.\n' "$backup_rev" "$current_rev" >&2
  echo "Set FORCE_SCHEMA_MISMATCH=1 only after reviewing the SQL and migration impact." >&2
  exit 1
fi

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  printf 'This replaces identity rows in %s. Type RESTORE to continue: ' "$DB"
  read -r answer
  [[ "$answer" == "RESTORE" ]] || { echo "Cancelled."; exit 1; }
fi

install -d -m 0700 "$ROLLBACK_DIR"
sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
rm -f -- "$DB-wal" "$DB-shm"
stamp="$(date +%F_%H%M%S)"
pre="$ROLLBACK_DIR/webui.db.pre-users-restore-$stamp"
sqlite3 "$DB" ".timeout 10000" ".backup '$pre'"
chown --reference="$DB" "$pre"
chmod --reference="$DB" "$pre"
[[ "$(sqlite3 "$pre" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: pre-restore snapshot failed integrity_check." >&2; exit 1;
}
( cd "$ROLLBACK_DIR" && sha256sum "$(basename "$pre")" > "$(basename "$pre").sha256" )

rollback_db(){
  echo "Restoring pre-restore snapshot: $pre" >&2
  rm -f -- "$DB-wal" "$DB-shm"
  cp -a -- "$pre" "$DB"
}
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
zcat "$SRC" > "$tmp"
if ! sqlite3 "$DB" < "$tmp"; then
  echo "ERROR: restore failed; restoring pre-restore snapshot." >&2
  rollback_db
  exit 1
fi
[[ "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: restored DB failed integrity_check." >&2
  rollback_db
  exit 1
}
fk_issues="$(sqlite3 "$DB" 'PRAGMA foreign_key_check;' 2>/dev/null || true)"
[[ -z "$fk_issues" ]] || {
  echo "ERROR: restored DB failed foreign_key_check." >&2
  printf '%s\n' "$fk_issues" >&2
  rollback_db
  exit 1
}
sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
echo "Identity rows restored. Pre-restore DB: $pre"
echo "Start Open WebUI and test an administrator login."

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
for cmd in sqlite3 gzip zcat python3 sha256sum sort comm awk; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done
gzip -t "$SRC"
if [[ -f "$SRC.sha256" ]]; then
  ( cd "$(dirname "$SRC")" && sha256sum --check --strict "$(basename "$SRC").sha256" )
elif [[ "${ALLOW_UNVERIFIED_BACKUP:-0}" != 1 ]]; then
  echo "ERROR: checksum sidecar is missing: $SRC.sha256" >&2
  echo "Set ALLOW_UNVERIFIED_BACKUP=1 only after independently verifying this backup." >&2
  exit 1
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
  if ! sqlite3 "$pre" ".timeout 10000" ".backup '$DB'"; then
    echo "CRITICAL: automatic database rollback failed. Keep Open WebUI stopped." >&2
    return 1
  fi
  chown --reference="$pre" "$DB"
  chmod --reference="$pre" "$DB"
  if [[ "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" != ok ]]; then
    echo "CRITICAL: automatic database rollback restored a database that failed integrity_check. Keep Open WebUI stopped." >&2
    return 1
  fi
  echo "Automatic rollback: successful." >&2
}

capture_fk_set(){
  local database="$1" output="$2" raw="${2}.raw"
  if ! sqlite3 -batch -noheader -separator $'\t' "$database" 'PRAGMA foreign_key_check;' > "$raw"; then
    rm -f -- "$raw"
    return 1
  fi
  LC_ALL=C sort -u "$raw" > "$output"
  rm -f -- "$raw"
}

tmpdir="$(mktemp -d)"
trap 'rm -rf -- "$tmpdir"' EXIT
tmp="$tmpdir/restore.sql"
fk_before="$tmpdir/fk-before.tsv"
fk_after="$tmpdir/fk-after.tsv"
fk_new="$tmpdir/fk-new.tsv"
if ! capture_fk_set "$pre" "$fk_before"; then
  echo "ERROR: could not record pre-restore foreign-key state; refusing to modify identity rows." >&2
  exit 1
fi
baseline_fk_count="$(awk 'END { print NR + 0 }' "$fk_before")"
zcat "$SRC" > "$tmp"
if ! sqlite3 "$DB" < "$tmp"; then
  echo "ERROR: restore failed; restoring pre-restore snapshot." >&2
  rollback_db || true
  exit 1
fi
[[ "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: restored DB failed integrity_check." >&2
  rollback_db || true
  exit 1
}
if ! capture_fk_set "$DB" "$fk_after"; then
  echo "ERROR: restored DB foreign-key validation could not be completed." >&2
  rollback_db || true
  exit 1
fi
LC_ALL=C comm -13 "$fk_before" "$fk_after" > "$fk_new"
new_fk_count="$(awk 'END { print NR + 0 }' "$fk_new")"
if (( new_fk_count > 0 )); then
  echo "ERROR: identity restore introduced ${new_fk_count} new foreign-key violation(s)." >&2
  awk 'NR <= 20 { print "  " $0 }' "$fk_new" >&2
  if (( new_fk_count > 20 )); then
    echo "  ... additional new violations omitted from normal output." >&2
  fi
  rollback_db || true
  exit 1
fi
sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
echo "Integrity: OK"
echo "Baseline FK violations: $baseline_fk_count"
echo "New FK violations: 0"
echo "Restore: successful"
echo "Pre-restore DB: $pre"
echo "Start Open WebUI and test an administrator login."

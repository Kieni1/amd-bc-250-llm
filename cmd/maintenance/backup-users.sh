#!/usr/bin/env bash
# Back up only identity-related rows from a consistent SQLite snapshot.
set -Eeuo pipefail
umask 0077
DB="${OWUI_DB:-/var/lib/open-webui/webui.db}"
OUT_DIR="${USERS_OUT_DIR:-${OUT_DIR:-/var/backups/bc250-llm-server/users}}"
EXPORT_USER="${BC250_BACKUP_EXPORT_USER:-bc250-backup-export}"
EXPORT_GROUP="${BC250_BACKUP_EXPORT_GROUP:-bc250-backup-export}"
KEEP="${KEEP_USERS:-${KEEP:-14}}"

[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: KEEP_USERS must be positive." >&2; exit 1; }
[[ -f "$DB" ]] || { echo "ERROR: DB not found: $DB" >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERROR: install sqlite." >&2; exit 1; }
if getent group "$EXPORT_GROUP" >/dev/null 2>&1; then
  install -d -m 0750 -o root -g "$EXPORT_GROUP" "$OUT_DIR"
else
  # Source-tree/direct execution fallback before package sysusers has created the reserved group.
  install -d -m 0700 "$OUT_DIR"
fi

# N3: stage beside, not inside, the read-only export scope (same filesystem, so
# publication stays an atomic rename). Remove stages left by a killed run.
STAGE_ROOT="${BC250_BACKUP_STAGE_DIR:-$(dirname -- "$OUT_DIR")/.stage}"
[[ "$STAGE_ROOT" == /* && "$STAGE_ROOT" != / ]] || { echo "ERROR: unsafe backup stage directory: $STAGE_ROOT" >&2; exit 1; }
install -d -m 0700 "$STAGE_ROOT"
find "$STAGE_ROOT" "$OUT_DIR" -mindepth 1 -maxdepth 1 -type d -name '.backup-stage.*' -mmin +1440 \
  -exec rm -rf -- {} + 2>/dev/null || true
tmpdir="$(mktemp -d "$STAGE_ROOT/.backup-stage.XXXXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT
snapshot="$tmpdir/webui.db"
sql="$tmpdir/users.sql"
sqlite3 "$DB" ".timeout 10000" ".backup '$snapshot'"
[[ "$(sqlite3 "$snapshot" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: snapshot integrity check failed." >&2; exit 1;
}

python3 - "$snapshot" "$sql" <<'PY_USERS'
import sqlite3, sys, datetime
src, dst = sys.argv[1:]
conn = sqlite3.connect(src)
existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
allow = [
    "access_grant", "group_member", "group", "groups",
    "auth", "user", "api_key", "model_access", "user_settings"
]
tables = [t for t in allow if t in existing]
missing = {"auth", "user"} - existing
if missing:
    raise SystemExit("required identity tables are missing: " + ", ".join(sorted(missing)))
revision = ""
if "alembic_version" in existing:
    row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    revision = row[0] if row else ""

def ident(name):
    return '"' + name.replace('"', '""') + '"'
def literal(v):
    if v is None: return "NULL"
    if isinstance(v, bytes): return "X'" + v.hex() + "'"
    if isinstance(v, (int, float)): return repr(v)
    return "'" + str(v).replace("'", "''") + "'"

with open(dst, "w", encoding="utf-8") as out:
    out.write("-- Open WebUI identity backup\n")
    out.write(f"-- OWUI_SCHEMA_REVISION={revision}\n")
    out.write(f"-- CREATED_UTC={datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
    out.write("PRAGMA foreign_keys=OFF;\nBEGIN IMMEDIATE;\n")
    for table in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({ident(table)})")]
        out.write(f"DELETE FROM {ident(table)};\n")
        q = f"SELECT * FROM {ident(table)}"
        for row in conn.execute(q):
            out.write(
                f"INSERT INTO {ident(table)} ({','.join(map(ident, cols))}) VALUES "
                f"({','.join(literal(v) for v in row)});\n"
            )
    out.write("COMMIT;\n")
PY_USERS

gzip -9 "$sql"
gzip -t "$sql.gz"
stamp="$(date +%F_%H%M%S)"
out="$OUT_DIR/owui-users-$stamp.sql.gz"
# Publish the archive first and its sidecar last: a Pi pull treats an archive
# without a sidecar as still in progress and collects it next time.
digest="$(sha256sum < "$tmpdir/users.sql.gz" | cut -d' ' -f1)"
printf '%s  %s\n' "$digest" "$(basename "$out")" > "$tmpdir/users.sql.gz.sha256"
if id "$EXPORT_USER" >/dev/null 2>&1; then
  chgrp "$EXPORT_GROUP" -- "$tmpdir/users.sql.gz" "$tmpdir/users.sql.gz.sha256"
  chmod 0640 -- "$tmpdir/users.sql.gz" "$tmpdir/users.sql.gz.sha256"
fi
mv -- "$tmpdir/users.sql.gz" "$out"
mv -- "$tmpdir/users.sql.gz.sha256" "$out.sha256"
mapfile -t old < <(ls -1t "$OUT_DIR"/owui-users-*.sql.gz 2>/dev/null | tail -n "+$((KEEP+1))")
for f in "${old[@]}"; do rm -f -- "$f" "$f.sha256"; done
printf 'Wrote and verified %s (%s)\n' "$out" "$(du -h "$out" | cut -f1)"

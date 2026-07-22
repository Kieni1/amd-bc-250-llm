#!/usr/bin/env bash
# Back up only identity-related rows from a consistent SQLite snapshot.
set -Eeuo pipefail
umask 0077
DB="${OWUI_DB:-/var/lib/open-webui/webui.db}"
OUT_DIR="${USERS_OUT_DIR:-${OUT_DIR:-/var/backups/bc250-llm-server/users}}"
KEEP="${KEEP_USERS:-${KEEP:-14}}"

[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: KEEP_USERS must be positive." >&2; exit 1; }
[[ -f "$DB" ]] || { echo "ERROR: DB not found: $DB" >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERROR: install sqlite." >&2; exit 1; }
install -d -m 0700 "$OUT_DIR"

tmpdir="$(mktemp -d)"
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
if not tables:
    raise SystemExit("no supported identity tables found")
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
print(" ".join(tables))
PY_USERS

gzip -9 "$sql"
gzip -t "$sql.gz"
stamp="$(date +%F_%H%M%S)"
out="$OUT_DIR/owui-users-$stamp.sql.gz"
mv "$sql.gz" "$out"
( cd "$OUT_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256" )
mapfile -t old < <(ls -1t "$OUT_DIR"/owui-users-*.sql.gz 2>/dev/null | tail -n "+$((KEEP+1))")
for f in "${old[@]}"; do rm -f -- "$f" "$f.sha256"; done
printf 'Wrote and verified %s (%s)\n' "$out" "$(du -h "$out" | cut -f1)"

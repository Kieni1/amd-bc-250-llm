#!/usr/bin/env bash
# Consistent Open WebUI snapshot: use SQLite online backup, exclude the live
# DB/WAL/SHM and bulky uploads/vector/cache, verify archive, then move atomically.
set -Eeuo pipefail
umask 0077
DATA="${OWUI_DATA:-/var/lib/open-webui}"
DB="${OWUI_DB:-$DATA/webui.db}"
OUT_DIR="${CFG_OUT_DIR:-/var/backups/bc250-llm-server/config}"
KEEP="${KEEP_CONFIG:-${KEEP:-7}}"

[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: KEEP_CONFIG must be positive." >&2; exit 1; }
[[ -d "$DATA" && -f "$DB" ]] || { echo "ERROR: Open WebUI data/DB missing." >&2; exit 1; }
command -v sqlite3 >/dev/null || { echo "ERROR: install sqlite." >&2; exit 1; }

install -d -m 0700 "$OUT_DIR"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
stage="$tmpdir/stage"
mkdir -m 0700 "$stage"
snapshot="$tmpdir/webui.db"
archive_tmp="$tmpdir/archive.tar.gz"

sqlite3 "$DB" ".timeout 10000" ".backup '$snapshot'"
[[ "$(sqlite3 "$snapshot" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: SQLite snapshot failed integrity_check." >&2; exit 1;
}

tar -C "$DATA" \
  --exclude='./uploads' --exclude='./vector_db' --exclude='./cache' \
  --exclude='./webui.db' --exclude='./webui.db-wal' --exclude='./webui.db-shm' \
  -cf - . | tar -C "$stage" -xf -
cp -- "$snapshot" "$stage/webui.db"
chown --reference="$DB" "$stage/webui.db"
chmod --reference="$DB" "$stage/webui.db"
touch --reference="$DB" "$stage/webui.db"
tar -C "$stage" -czf "$archive_tmp" .
tar -tzf "$archive_tmp" >/dev/null

stamp="$(date +%F_%H%M%S)"
out="$OUT_DIR/owui-config-$stamp.tar.gz"
mv "$archive_tmp" "$out"
( cd "$OUT_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256" )
mapfile -t old < <(ls -1t "$OUT_DIR"/owui-config-*.tar.gz 2>/dev/null | tail -n "+$((KEEP+1))")
for f in "${old[@]}"; do rm -f -- "$f" "$f.sha256"; done
printf 'Wrote and verified %s (%s)\n' "$out" "$(du -h "$out" | cut -f1)"

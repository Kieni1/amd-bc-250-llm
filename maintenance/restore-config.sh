#!/usr/bin/env bash
# Restore a verified Open WebUI configuration snapshot while preserving bulky
# uploads/vector/cache directories. Open WebUI must be stopped.
set -Eeuo pipefail
umask 0077
DATA="${OWUI_DATA:-/var/lib/open-webui}"
DB="${OWUI_DB:-$DATA/webui.db}"
SRC="${1:?Usage: restore-config.sh <owui-config-*.tar.gz>}"
ROLLBACK_DIR="${CFG_ROLLBACK_DIR:-/var/backups/bc250-llm-server/rollback/config}"

[[ ${EUID} -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ -d "$DATA" && "$DATA" != / ]] || { echo "ERROR: unsafe or missing OWUI_DATA: $DATA" >&2; exit 1; }
[[ -r "$SRC" ]] || { echo "ERROR: backup not readable: $SRC" >&2; exit 1; }
for cmd in sqlite3 tar python3 sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done
if systemctl is-active --quiet open-webui.service 2>/dev/null; then
  echo "ERROR: stop Open WebUI before restoring: sudo systemctl stop open-webui" >&2
  exit 1
fi
if [[ -f "$SRC.sha256" ]]; then
  ( cd "$(dirname "$SRC")" && sha256sum --check --strict "$(basename "$SRC").sha256" )
fi
tar -tzf "$SRC" >/dev/null

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
stage="$tmpdir/stage"
mkdir -m 0700 "$stage"
python3 - "$SRC" <<'PY_VALIDATE'
import pathlib, sys, tarfile
src = sys.argv[1]
seen_db = False
with tarfile.open(src, "r:gz") as tf:
    for member in tf.getmembers():
        p = pathlib.PurePosixPath(member.name)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit(f"unsafe archive path: {member.name}")
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise SystemExit(f"unsupported archive member: {member.name}")
        if p.name == "webui.db":
            seen_db = True
if not seen_db:
    raise SystemExit("archive does not contain webui.db")
PY_VALIDATE
tar --numeric-owner -xzf "$SRC" -C "$stage"
restored_db="$(find "$stage" -maxdepth 2 -type f -name webui.db -print -quit)"
[[ -n "$restored_db" ]] || { echo "ERROR: extracted database missing." >&2; exit 1; }
[[ "$(sqlite3 "$restored_db" 'PRAGMA integrity_check;')" == "ok" ]] || {
  echo "ERROR: backup database failed integrity_check." >&2; exit 1;
}

if [[ "${CONFIRM_RESTORE:-}" != YES ]]; then
  printf 'This replaces Open WebUI configuration and DB in %s while preserving uploads/vector/cache. Type RESTORE to continue: ' "$DATA"
  read -r answer
  [[ "$answer" == RESTORE ]] || { echo "Cancelled."; exit 1; }
fi

install -d -m 0700 "$ROLLBACK_DIR"
stamp="$(date +%F_%H%M%S)"
rollback="$ROLLBACK_DIR/owui-config-pre-restore-$stamp.tar.gz"
tar -C "$DATA" \
  --exclude='./uploads' --exclude='./vector_db' --exclude='./cache' \
  -czf "$rollback" .
tar -tzf "$rollback" >/dev/null
( cd "$ROLLBACK_DIR" && sha256sum "$(basename "$rollback")" > "$(basename "$rollback").sha256" )

clear_nonbulk(){
  find "$DATA" -mindepth 1 -maxdepth 1 \
    ! -name uploads ! -name vector_db ! -name cache \
    -exec rm -rf -- {} +
}
rollback_now(){
  echo "ERROR: restore failed; rolling back from $rollback" >&2
  local rollback_failed=0
  clear_nonbulk || rollback_failed=1
  tar --numeric-owner -xzf "$rollback" -C "$DATA" || rollback_failed=1
  if ((rollback_failed)); then
    echo "CRITICAL: automatic rollback was incomplete. Keep Open WebUI stopped and restore manually from: $rollback" >&2
    return 1
  fi
  echo "Rollback completed successfully." >&2
}

ok=1
clear_nonbulk || ok=0
if ((ok)); then tar -C "$stage" -cf - . | tar --numeric-owner -C "$DATA" -xpf - || ok=0; fi
if ((ok)); then
  [[ -f "$DB" && "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" == ok ]] || ok=0
fi
if (( ! ok )); then
  rollback_status=0
  rollback_now || rollback_status=$?
  ((rollback_status == 0)) || echo "CRITICAL: automatic rollback requires manual follow-up." >&2
  exit 1
fi

echo "Configuration restored. Preserved uploads/vector/cache. Rollback archive: $rollback"
echo "Do not run restorecon on $DATA; the Podman :Z mount restores its private container label."
echo "Start Open WebUI and verify administrator login, files, and RAG before deleting rollback data."

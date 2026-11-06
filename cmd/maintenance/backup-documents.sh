#!/usr/bin/env bash
# Snapshot the managed document SOURCE OF TRUTH, not rebuildable OWUI vectors.
set -Eeuo pipefail
umask 0077
DOC_ROOT="${BC250_DOCUMENT_ROOT:-/srv/bc250-documents}"
OUT_DIR="${DOCS_OUT_DIR:-/var/backups/bc250-llm-server/documents}"
KEEP="${KEEP_DOCUMENTS:-7}"
EXPORT_USER="${BC250_BACKUP_EXPORT_USER:-bc250-backup-export}"
EXPORT_GROUP="${BC250_BACKUP_EXPORT_GROUP:-bc250-backup-export}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: KEEP_DOCUMENTS must be positive.' >&2; exit 1; }
[[ "$DOC_ROOT" == /* && "$DOC_ROOT" != / && -d "$DOC_ROOT" && ! -L "$DOC_ROOT" ]] || {
  echo "ERROR: managed document root is absent, unsafe, or a symlink: $DOC_ROOT" >&2; exit 1;
}
for cmd in tar python3 sha256sum du df; do command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing $cmd" >&2; exit 1; }; done
if getent group "$EXPORT_GROUP" >/dev/null 2>&1; then
  install -d -m0750 -o root -g "$EXPORT_GROUP" "$OUT_DIR"
else
  install -d -m0700 "$OUT_DIR"
fi
# N3: stage beside, not inside, the read-only export scope (same filesystem, so
# publication stays an atomic rename). Remove stages left by a killed run.
STAGE_ROOT="${BC250_BACKUP_STAGE_DIR:-$(dirname -- "$OUT_DIR")/.stage}"
[[ "$STAGE_ROOT" == /* && "$STAGE_ROOT" != / ]] || { echo "ERROR: unsafe backup stage directory: $STAGE_ROOT" >&2; exit 1; }
install -d -m 0700 "$STAGE_ROOT"
find "$STAGE_ROOT" "$OUT_DIR" -mindepth 1 -maxdepth 1 -type d -name '.backup-stage.*' -mmin +1440 \
  -exec rm -rf -- {} + 2>/dev/null || true
# "<manifest digest> <archive name>" of the newest archive; its mtime is the
# last time the corpus was verified as backed up (read by maintenance status).
STATE_FILE="$STAGE_ROOT/documents.state"
RESERVE_MB="${BC250_BACKUP_RESERVE_MB:-1024}"
[[ "$RESERVE_MB" =~ ^[0-9]+$ ]] || { echo 'ERROR: BC250_BACKUP_RESERVE_MB must be an integer.' >&2; exit 1; }

# Digest of the corpus layout (path, type, size, mtime, mode). It refuses links
# and device entries, so the archive never follows links outside the corpus.
corpus_manifest() {
  python3 - "$DOC_ROOT" <<'PY_SOURCE'
import hashlib
import os
import stat
import sys
from pathlib import Path
root = Path(sys.argv[1])
digest = hashlib.sha256()
entries = []
for directory, dirs, files in os.walk(root, followlinks=False):
    for name in dirs + files:
        path = Path(directory) / name
        info = path.lstat()
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise SystemExit(f"ERROR: managed document backup does not allow links/devices: {path}")
        size = info.st_size if stat.S_ISREG(info.st_mode) else 0
        entries.append(f"{path.relative_to(root)}\0{info.st_mode:o}\0{size}\0{info.st_mtime_ns}")
for entry in sorted(entries):
    digest.update(entry.encode("utf-8", "surrogateescape") + b"\n")
print(digest.hexdigest())
PY_SOURCE
}

manifest="$(corpus_manifest)"
if [[ -f "$STATE_FILE" ]]; then
  read -r last_manifest last_archive _ < "$STATE_FILE" || true
  if [[ "${last_manifest:-}" == "$manifest" && "${last_archive:-}" == bc250-documents-*.tar.gz &&
        -f "$OUT_DIR/$last_archive" && -f "$OUT_DIR/$last_archive.sha256" ]] &&
     ( cd "$OUT_DIR" && sha256sum --check --strict --status -- "$last_archive.sha256" ); then
    touch -- "$STATE_FILE"
    printf 'Managed corpus unchanged since %s; verified it and skipped a new archive.\n' "$last_archive"
    exit 0
  fi
fi

# Compressed PDFs/office files barely shrink: require the uncompressed corpus
# size plus a reserve on the staging filesystem before writing anything.
need_bytes="$(du -sb -- "$DOC_ROOT" | cut -f1)"
avail_bytes="$(df -B1 --output=avail -- "$STAGE_ROOT" | tail -n1 | tr -d ' ')"
if [[ "$need_bytes" =~ ^[0-9]+$ && "$avail_bytes" =~ ^[0-9]+$ ]] &&
   (( avail_bytes < need_bytes + RESERVE_MB * 1024 * 1024 )); then
  echo "ERROR: not enough space for the corpus backup (need ~$((need_bytes / 1048576)) MiB + ${RESERVE_MB} MiB reserve, have $((avail_bytes / 1048576)) MiB)." >&2
  exit 1
fi

tmpdir="$(mktemp -d "$STAGE_ROOT/.backup-stage.XXXXXXXX")"
trap 'rm -rf -- "$tmpdir"' EXIT
archive="$tmpdir/documents.tar.gz"
# Complete contents: sources/, active/, superseded/, collection metadata and
# provenance. An import during the archive changes the manifest (or makes tar
# exit 1); retry so the published archive is one consistent corpus state.
consistent=0
for attempt in 1 2 3; do
  rm -f -- "$archive"
  tar_rc=0
  tar -C "$DOC_ROOT" --numeric-owner -czf "$archive" . || tar_rc=$?
  after="$(corpus_manifest)"
  if ((tar_rc == 0)) && [[ "$after" == "$manifest" ]]; then
    consistent=1
    break
  fi
  ((tar_rc <= 1)) || { echo "ERROR: tar failed (rc=$tar_rc) while archiving the managed corpus." >&2; exit 1; }
  echo "WARNING: managed corpus changed during backup attempt $attempt; retrying." >&2
  manifest="$after"
  sleep "${BC250_BACKUP_RETRY_DELAY:-30}"
done
((consistent)) || { echo 'ERROR: managed corpus kept changing; no new archive published.' >&2; exit 1; }
python3 - "$archive" <<'PY_VALIDATE'
import pathlib
import sys
import tarfile
with tarfile.open(sys.argv[1], 'r:gz') as bundle:
    for member in bundle:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
            raise SystemExit(f'ERROR: unsafe corpus backup member: {member.name}')
PY_VALIDATE
stamp="$(date +%F_%H%M%S)"
out="$OUT_DIR/bc250-documents-$stamp.tar.gz"
# Publish the archive first and its sidecar last: a Pi pull treats an archive
# without a sidecar as still in progress and collects it next time.
digest="$(sha256sum < "$archive" | cut -d' ' -f1)"
printf '%s  %s\n' "$digest" "$(basename "$out")" > "$archive.sha256"
if id "$EXPORT_USER" >/dev/null 2>&1; then
  chgrp "$EXPORT_GROUP" -- "$archive" "$archive.sha256"
  chmod 0640 -- "$archive" "$archive.sha256"
fi
mv -- "$archive" "$out"
mv -- "$archive.sha256" "$out.sha256"
printf '%s %s\n' "$manifest" "$(basename "$out")" > "$STATE_FILE.tmp"
mv -- "$STATE_FILE.tmp" "$STATE_FILE"
mapfile -t old < <(ls -1t "$OUT_DIR"/bc250-documents-*.tar.gz 2>/dev/null | tail -n "+$((KEEP+1))")
for file in "${old[@]}"; do rm -f -- "$file" "$file.sha256"; done
printf 'Wrote and verified managed corpus: %s\n' "$out"

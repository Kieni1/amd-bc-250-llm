#!/usr/bin/env bash
# Raspberry Pi: mirror the read-only rrsync backup scopes, verify SHA-256
# sidecars and keep dated, hardlinked snapshots of complete archive pairs.
#
# Storage stays proportional to the distinct archives seen during the retention
# window: an archive that already exists in an earlier snapshot is hardlinked,
# not copied again. An archive whose sidecar is not published yet (the BC-250 is
# still writing it) is skipped with a warning and picked up on the next pull.
set -Eeuo pipefail
umask 0077
BASE="${BC250_PI_BACKUP_DIR:-/var/backups/bc250}"
SSH_CONFIG="${BC250_PI_SSH_CONFIG:-/etc/bc250/ssh_config}"
KEEP="${BC250_PI_BACKUP_KEEP:-14}"
SCOPES="${BC250_PI_BACKUP_SCOPES:-config users documents}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: retention must be positive.' >&2; exit 2; }
[[ -n "$BASE" && "$BASE" == /* && "$BASE" != / ]] || { echo "ERROR: unsafe backup directory: ${BASE:-<empty>}" >&2; exit 2; }
[[ -r "$SSH_CONFIG" ]] || { echo "ERROR: missing SSH configuration: $SSH_CONFIG" >&2; exit 1; }
for cmd in rsync ssh sha256sum; do command -v "$cmd" >/dev/null || { echo "ERROR: missing $cmd" >&2; exit 1; }; done

archive_pattern() {
  case "$1" in
    config) printf '%s' 'owui-config-*.tar.gz' ;;
    users) printf '%s' 'owui-users-*.sql.gz' ;;
    documents) printf '%s' 'bc250-documents-*.tar.gz' ;;
    *) return 1 ;;
  esac
}

install -d -m0700 "$BASE" "$BASE/mirror"
work="$(mktemp -d "$BASE/.pull.XXXXXXXX")"
trap 'rm -rf -- "${work:?}"' EXIT
failed=0

for kind in $SCOPES; do
  pattern="$(archive_pattern "$kind")" || { echo "ERROR: unknown backup scope: $kind" >&2; exit 2; }
  mirror="$BASE/mirror/$kind"
  install -d -m0700 "$mirror" "$work/$kind"
  # The mirror follows the BC-250 retention set. rsync writes each file to a
  # temporary name and renames it, so snapshots hardlinked to an older inode keep
  # their bytes. Dot entries (BC-250 staging) are never part of the contract.
  rc=0
  rsync -a --no-owner --no-group --no-perms --delete-after --exclude='.*' --timeout=120 \
    -e "ssh -F $SSH_CONFIG -o BatchMode=yes" \
    "bc250-${kind}:/" "$mirror/" || rc=$?
  if ((rc != 0 && rc != 24)); then
    # 24 = source files vanished during transfer (BC-250 retention ran); harmless.
    echo "ERROR: rsync of $kind scope failed (exit $rc)." >&2
    failed=1
    continue
  fi

  verified=0
  mapfile -t archives < <(find "$mirror" -maxdepth 1 -type f -name "$pattern" -printf '%f\n' | LC_ALL=C sort)
  for name in "${archives[@]}"; do
    sidecar="$mirror/$name.sha256"
    if [[ ! -f "$sidecar" ]]; then
      echo "WARNING: $kind/$name has no sidecar yet (backup in progress?); skipped this time." >&2
      continue
    fi
    # The sidecar must name exactly this archive; then verify its bytes.
    if [[ "$(awk 'NR == 1 {print $2}' "$sidecar")" != "$name" ]] || \
       ! ( cd "$mirror" && sha256sum --check --strict --status -- "$name.sha256" ); then
      echo "ERROR: checksum verification failed for $kind/$name." >&2
      failed=1
      continue
    fi
    ln -- "$mirror/$name" "$work/$kind/$name"
    ln -- "$sidecar" "$work/$kind/$name.sha256"
    verified=$((verified + 1))
  done
  if ((verified == 0)); then
    echo "ERROR: no complete verified $kind archive pair is available." >&2
    failed=1
  fi
done

if ((failed)); then
  echo "ERROR: Pi backup pull incomplete; no new snapshot recorded. The mirror keeps the transferred files." >&2
  exit 1
fi

stamp="$(date +%F_%H%M%S)"
final="$BASE/$stamp"
[[ ! -e "$final" ]] || { echo "ERROR: backup destination already exists: $final" >&2; exit 1; }
mv -- "$work" "$final"
trap - EXIT
# Retain only timestamped complete snapshots; keep the mirror and operator files.
mapfile -t old < <(find "$BASE" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??_??????' -printf '%f\n' | LC_ALL=C sort -r | tail -n "+$((KEEP+1))")
for name in "${old[@]}"; do rm -rf -- "${BASE:?}/${name:?}"; done
printf 'Verified Pi backup snapshot: %s\n' "$final"

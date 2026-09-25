#!/usr/bin/env bash
# Read-only, redacted BC-250 support evidence bundle.
set -Eeuo pipefail
umask 077

BUNDLE_VERSION=2
DEFAULT_OUTPUT=/var/lib/bc250-llm-server/support
OUTPUT_DIR="$DEFAULT_OUTPUT"
CAPTURE_TIMEOUT=${BC250_SUPPORT_CAPTURE_TIMEOUT:-20}

usage() {
  cat <<'USAGE'
Usage: sudo bc250-support-bundle [--output-dir DIR]

Create a timestamped, read-only support archive containing appliance state,
health summaries and redacted diagnostics. The bundle intentionally excludes
Open WebUI tokens, prompts, chats, uploaded document contents, database rows,
identity SQL and backup contents.
USAGE
}

while (($#)); do
  case "$1" in
    --output-dir)
      (($# >= 2)) || { echo "ERROR: --output-dir requires a directory." >&2; exit 2; }
      OUTPUT_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

((EUID == 0)) || { echo "ERROR: run with sudo for complete support evidence." >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required." >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "ERROR: sha256sum is required." >&2; exit 1; }
command -v timeout >/dev/null 2>&1 || { echo "ERROR: timeout is required." >&2; exit 1; }
[[ "$CAPTURE_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: BC250_SUPPORT_CAPTURE_TIMEOUT must be a positive integer." >&2; exit 2; }

run_id="$(date +%Y%m%dT%H%M%S%z)-$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
started="$(date --iso-8601=seconds)"
work="$(mktemp -d /run/bc250-support-bundle.XXXXXX)"
evidence="$work/evidence"
archive="$OUTPUT_DIR/${run_id}-bc250-support-bundle.tar.gz"
trap 'rm -rf "$work"' EXIT
install -d -m 0700 "$evidence" "$OUTPUT_DIR"

capture() {
  local file="$1"; shift
  {
    printf '$'; printf ' %q' "$@"; echo
    set +e
    timeout --signal=TERM --kill-after=5s "${CAPTURE_TIMEOUT}s" "$@"
    rc=$?
    set -e
    echo "command_rc=$rc"
    [[ $rc -ne 124 ]] || echo "interpretation=TIMEOUT after ${CAPTURE_TIMEOUT}s"
  } > "$evidence/$file" 2>&1
}

capture_shell() {
  local file="$1" command="$2"
  {
    printf '$ %s\n' "$command"
    set +e
    timeout --signal=TERM --kill-after=5s "${CAPTURE_TIMEOUT}s" bash -o pipefail -c "$command"
    rc=$?
    set -e
    echo "command_rc=$rc"
    [[ $rc -ne 124 ]] || echo "interpretation=TIMEOUT after ${CAPTURE_TIMEOUT}s"
  } > "$evidence/$file" 2>&1
}

capture package.txt rpm -q bc250-llm-server
capture package-verify.txt rpm -V bc250-llm-server
capture status.txt bc250-status
capture verify-summary.txt bc250-verify --summary
capture topology.txt bc250-agent-mode status
capture cu-routing.txt bc250-cu-status --summary
capture maintenance.txt bc250-maintenance status
capture failed-units.txt systemctl --failed --no-pager --full
capture memory.txt free -h
capture swap.txt swapon --show
capture disk.txt df -hT / /boot /var/lib/bc250-llm-server
capture inodes.txt df -ih / /var/lib/bc250-llm-server
command -v sensors >/dev/null 2>&1 && capture sensors.txt sensors

{
  echo "current_boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
  journalctl --list-boots --no-pager 2>/dev/null | tail -2 || true
} > "$evidence/boots.txt"

for port in 11434 11435 11436 11437; do
  curl -fsS --connect-timeout 1 --max-time 3 "http://127.0.0.1:${port}/api/ps" \
    > "$evidence/ollama-${port}-residency.json" 2>/dev/null || true
done

{
  for unit in ollama.service ollama-task.service ollama-embedding.service ollama-agent.service open-webui.service tika.service nginx.service; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    printf '%s active=%s enabled=%s\n' "$unit" "${state:-unknown}" "${enabled:-unknown}"
    cg="$(systemctl show -p ControlGroup --value "$unit" 2>/dev/null || true)"
    if [[ -n "$cg" && -r "/sys/fs/cgroup${cg}/memory.events" ]]; then
      echo "  cgroup=$cg"
      sed 's/^/  memory.events /' "/sys/fs/cgroup${cg}/memory.events"
      [[ -r "/sys/fs/cgroup${cg}/memory.current" ]] && echo "  memory.current $(cat "/sys/fs/cgroup${cg}/memory.current")"
    fi
  done
} > "$evidence/services.txt"

capture_shell kernel-events.txt \
  "journalctl -k -b --no-pager | grep -Ei 'out of memory|oom-kill|amdgpu.*(gpu reset|device lost|vm fault|ring[^ ]*.*timeout)|not enough memory for command submission' | tail -200 || true"

{
  if [[ -d /sys/fs/pstore ]]; then
    find /sys/fs/pstore -maxdepth 1 -type f -printf '%f %s bytes\n' 2>/dev/null | sort
  else
    echo "pstore unavailable"
  fi
} > "$evidence/pstore-presence.txt"

{
  for root in /etc/bc250-llm-server /etc/cyan-skillfish-governor-smu; do
    [[ -d "$root" ]] || continue
    find "$root" -xdev -type f -print0 2>/dev/null
  done | sort -z | xargs -0 -r sha256sum
} > "$evidence/package-config-sha256.txt"

ended="$(date --iso-8601=seconds)"
package="$(rpm -q bc250-llm-server 2>/dev/null || echo unknown)"
kernel="$(uname -r)"
python3 - "$work/manifest.json" "$run_id" "$BUNDLE_VERSION" "$package" "$kernel" "$started" "$ended" <<'PY'
import json
import sys
from pathlib import Path

path, run_id, version, package, kernel, started, ended = sys.argv[1:]
manifest = {
    "schema_version": 1,
    "bundle_version": version,
    "run_id": run_id,
    "package": package,
    "kernel": kernel,
    "started_at": started,
    "ended_at": ended,
    "scope": "redacted-read-only-support-evidence",
    "excludes": [
        "Open WebUI API tokens and passwords",
        "prompts and chat content",
        "uploaded document contents",
        "Open WebUI database rows and identity SQL",
        "backup contents",
    ],
}
Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

(
  cd "$work"
  find manifest.json evidence -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
  sha256sum -c SHA256SUMS.txt >/dev/null
  tar -czf "$archive.tmp" manifest.json SHA256SUMS.txt evidence
)
verify_dir="$work/verify"
install -d -m 0700 "$verify_dir"
tar -xzf "$archive.tmp" -C "$verify_dir"
(cd "$verify_dir" && sha256sum -c SHA256SUMS.txt >/dev/null)
chmod 0600 "$archive.tmp"
mv -f "$archive.tmp" "$archive"

echo "Support bundle created and self-verified: $archive"
echo "The archive is mode 0600 and excludes user content and credentials by design."

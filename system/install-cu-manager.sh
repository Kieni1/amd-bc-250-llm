#!/usr/bin/env bash
# Download the BC-250 live manager only when both a reviewed immutable URL and
# its SHA-256 are supplied. This deliberately refuses moving branch URLs.
set -Eeuo pipefail
umask 0022

DEST="${DEST:-/usr/local/sbin/bc250-cu-live-manager}"
CU_MANAGER_COMMIT="8eb45f07810af738f3e4945ea0cc29d399e378a6"
CU_MANAGER_URL="${CU_MANAGER_URL:-https://raw.githubusercontent.com/WinnieLV/bc250-cu-live-manager/${CU_MANAGER_COMMIT}/bc250-cu-live-manager.sh}"
CU_MANAGER_SHA256="${CU_MANAGER_SHA256:-aa519469967130b07a4e343bf08a60db6bf4a96291b453d8fddcaf8fcc02e833}"

[[ ${EUID} -eq 0 ]] || { echo "ERROR: run with sudo." >&2; exit 1; }
[[ "$CU_MANAGER_URL" =~ ^https://raw\.githubusercontent\.com/WinnieLV/bc250-cu-live-manager/[0-9a-fA-F]{40}/bc250-cu-live-manager\.sh$ ]] || {
  echo "ERROR: CU_MANAGER_URL must contain a full reviewed 40-character commit SHA." >&2
  exit 1
}
[[ "$CU_MANAGER_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || {
  echo "ERROR: set CU_MANAGER_SHA256 to the reviewed script's SHA-256." >&2
  exit 1
}

for cmd in curl sha256sum install; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing command: $cmd" >&2; exit 1; }
done

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 \
  --retry 3 --retry-all-errors --connect-timeout 15 \
  --output "$tmp" "$CU_MANAGER_URL"
printf '%s  %s\n' "$CU_MANAGER_SHA256" "$tmp" | sha256sum --check --strict -
head -n 1 "$tmp" | grep -qx '#!/usr/bin/env bash' || {
  echo "ERROR: unexpected downloaded file." >&2
  exit 1
}
bash -n "$tmp"
install -m 0755 "$tmp" "$DEST"
echo "Installed verified CU manager at $DEST"
echo "Apply changes live first. Save boot persistence only after stress testing."

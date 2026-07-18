#!/usr/bin/env bash
# Prepare the exact WinnieLV CU live-manager archive used as RPM Source4.
set -Eeuo pipefail
umask 0022

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/sources"
COMMIT="8eb45f07810af738f3e4945ea0cc29d399e378a6"
OUT="$OUT_DIR/bc250-cu-live-manager-${COMMIT}.tar.gz"
SUM="$OUT_DIR/bc250-cu-live-manager-${COMMIT}.sha256"
URL="https://github.com/WinnieLV/bc250-cu-live-manager/archive/${COMMIT}.tar.gz"
SOURCE_SHA256="50393641e8abff46d2596f4167d5a43f329f8a7f9a8c8e8dbd697f60145cc020"

for cmd in curl tar sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: $cmd is required." >&2
    exit 1
  }
done
mkdir -p "$OUT_DIR"

if [[ ! -s "$OUT" ]]; then
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  echo "Downloading pinned CU live manager: $COMMIT"
  curl --fail --location --retry 3 --retry-all-errors \
    --proto '=https' --tlsv1.2 --connect-timeout 20 \
    --output "$tmp" "$URL"
  mv "$tmp" "$OUT"
fi
printf '%s  %s\n' "$SOURCE_SHA256" "$OUT" | sha256sum --check --strict -

for required in \
  "bc250-cu-live-manager-${COMMIT}/README.md" \
  "bc250-cu-live-manager-${COMMIT}/bc250-cu-live-manager.sh"
do
  tar -tzf "$OUT" "$required" >/dev/null 2>&1 || {
    echo "ERROR: archive is missing $required" >&2
    exit 1
  }
done

(
  cd "$OUT_DIR"
  sha256sum "$(basename "$OUT")" > "$(basename "$SUM")"
)
echo "Prepared $OUT"
cat "$SUM"

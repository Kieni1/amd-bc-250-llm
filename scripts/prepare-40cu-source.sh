#!/usr/bin/env bash
# Prepare the exact fduraibi 40-CU source archive used as RPM Source3.
set -Eeuo pipefail
umask 0022

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/sources"
COMMIT="6c3969ddee40e894297869e6ca30537f274619cb"
OUT="$OUT_DIR/bc250-40cu-unlock-${COMMIT}.tar.gz"
SUM="$OUT_DIR/bc250-40cu-unlock-${COMMIT}.sha256"
URL="https://github.com/fduraibi/bc250-40cu-unlock/archive/${COMMIT}.tar.gz"
SOURCE_SHA256="803968cebaddf164ecf7e9c63f109b0d2db973254f44be9f77fe6235568992ba"

command -v curl >/dev/null || { echo "ERROR: curl is required." >&2; exit 1; }
command -v tar >/dev/null || { echo "ERROR: tar is required." >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "ERROR: sha256sum is required." >&2; exit 1; }
mkdir -p "$OUT_DIR"

if [[ ! -s "$OUT" ]]; then
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  echo "Downloading pinned 40-CU source: $COMMIT"
  curl --fail --location --retry 3 --retry-all-errors \
    --proto '=https' --tlsv1.2 \
    --connect-timeout 20 --output "$tmp" "$URL"
  mv "$tmp" "$OUT"
fi
printf '%s  %s\n' "$SOURCE_SHA256" "$OUT" | sha256sum --check --strict -

for required in \
  "bc250-40cu-unlock-${COMMIT}/README.md" \
  "bc250-40cu-unlock-${COMMIT}/scripts/bc250-enable-40cu-fedora.sh" \
  "bc250-40cu-unlock-${COMMIT}/patch/bc250-40cu-amdgpu.patch"
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

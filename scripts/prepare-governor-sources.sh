#!/usr/bin/env bash
set -Eeuo pipefail
umask 0022

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMMIT="60ab6e5b354f01f287c73d920990dcd618a674cc"
URL="https://github.com/filippor/cyan-skillfish-governor/archive/${COMMIT}.tar.gz"
SOURCE_SHA256="15fa19ce8fdc13dd629977144f24f8cca8bf1a1e8c65e61820cd89d6ca02bfd3"
SOURCE="$ROOT/sources/cyan-skillfish-governor-${COMMIT}.tar.gz"
VENDOR="$ROOT/sources/cyan-skillfish-governor-vendor-${COMMIT}.tar.xz"
WORK="$ROOT/build/governor-source"

for cmd in curl tar cargo sha256sum xz; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing $cmd" >&2
    exit 1
  }
done
mkdir -p "$ROOT/sources" "$ROOT/build"

if [[ ! -s "$SOURCE" ]]; then
  echo "Downloading pinned governor commit $COMMIT"
  curl --fail --location --retry 3 --retry-all-errors \
    --proto '=https' --tlsv1.2 --output "$SOURCE.tmp" "$URL"
  mv "$SOURCE.tmp" "$SOURCE"
fi
printf '%s  %s\n' "$SOURCE_SHA256" "$SOURCE" | sha256sum --check --strict -

rm -rf "$WORK"
mkdir -p "$WORK"
tar -xzf "$SOURCE" -C "$WORK" --strip-components=1

grep -q 'name = "cyan-skillfish-governor-smu"' "$WORK/Cargo.toml" || {
  echo "ERROR: unexpected governor source archive" >&2
  exit 1
}
for expected in Cargo.lock LICENSE default-config.toml \
  cyan-skillfish-governor-smu.service \
  com.cyanskillfish.Governor.conf \
  scripts/cyan-skillfish-performance-mode; do
  [[ -f "$WORK/$expected" ]] || {
    echo "ERROR: governor source is missing $expected" >&2
    exit 1
  }
done

if [[ ! -s "$VENDOR" ]]; then
  echo "Vendoring Rust dependencies"
  (
    cd "$WORK"
    rm -rf vendor .cargo
    mkdir -p .cargo
    cargo vendor --locked vendor > .cargo/config.toml
    tar -cJf "$VENDOR.tmp" vendor .cargo/config.toml
  )
  mv "$VENDOR.tmp" "$VENDOR"
fi

(
  cd "$ROOT/sources"
  sha256sum "$(basename "$SOURCE")" "$(basename "$VENDOR")" > governor-sources.sha256
)
echo "Governor sources ready."

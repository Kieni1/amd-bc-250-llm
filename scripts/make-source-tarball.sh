#!/usr/bin/env bash
set -Eeuo pipefail
umask 0022

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="bc250-llm-server"
VERSION="$(<"$ROOT/VERSION")"
OUT_DIR="$ROOT/build"
OUT="$OUT_DIR/${NAME}-${VERSION}.tar.gz"
if [[ -z "${SOURCE_DATE_EPOCH:-}" ]]; then
  changelog_date="$(awk '/^%changelog/{seen=1; next} seen && /^\*/ {print $2, $3, $4, $5; exit}' "$ROOT/packaging/bc250-llm-server.spec")"
  SOURCE_DATE_EPOCH="$(LC_ALL=C TZ=UTC date --date="$changelog_date 00:00:00 UTC" +%s)"
fi

mkdir -p "$OUT_DIR"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
stage="$tmp/${NAME}-${VERSION}"

mkdir -p "$stage"
(
  cd "$ROOT"
  tar \
    --exclude='./build' \
    --exclude='./dist' \
    --exclude='./rpmbuild' \
    --exclude='./sources' \
    --exclude='./vendor' \
    --exclude='*/__pycache__' \
    --exclude='*/.ruff_cache' \
    --exclude='*/.pytest_cache' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='./.git' \
    -cf - .
) | tar -xf - -C "$stage"

find "$stage" -print0 | xargs -0 touch --date="@${SOURCE_DATE_EPOCH}"
tar --sort=name \
  --mtime="@${SOURCE_DATE_EPOCH}" \
  --owner=0 --group=0 --numeric-owner \
  --mode='u+rwX,go+rX,go-w,a-s,a-t' \
  -czf "$OUT" -C "$tmp" "${NAME}-${VERSION}"

echo "Created $OUT"

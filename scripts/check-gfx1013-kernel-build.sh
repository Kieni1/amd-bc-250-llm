#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export BC250_GFX1013_LIBRARY_ONLY=1
export BC250_GFX1013_SOURCE="${BC250_GFX1013_SOURCE:-$ROOT/gfx1013/upstream}"
export BC250_GFX1013_CACHE_ROOT="${BC250_GFX1013_CACHE_ROOT:-$ROOT/sources/gfx1013}"

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: GFX1013 kernel build check requires Fedora." >&2
  exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ ${ID:-} != fedora ]]; then
  echo "ERROR: GFX1013 kernel build check requires Fedora (found ${ID:-unknown})." >&2
  exit 2
fi

mapfile -t builds < <(find /usr/src/kernels -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort)
if ((${#builds[@]} != 1)); then
  echo "ERROR: expected exactly one Fedora kernel-devel tree, found ${#builds[@]}." >&2
  printf '  %s\n' "${builds[@]:-}" >&2
  exit 2
fi

build="${builds[0]}"
kernel="${build##*/}"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/build" "$work/abi"

# Source the package implementation rather than reproducing the kernel path in CI.
# The library-only guard prevents CLI dispatch while retaining production functions.
# shellcheck source=../cmd/system/gfx1013.sh
source "$ROOT/cmd/system/gfx1013.sh"

owner="$(kernel_build_owner "$kernel" "$build")" || {
  echo "ERROR: Fedora kernel-devel ownership check failed for $build." >&2
  exit 2
}
[[ "$owner" == "kernel-devel-$kernel" ]] || {
  echo "ERROR: kernel-devel ownership mismatch: $owner" >&2
  exit 2
}

# The stock marker is intentionally only an extension selector. build_kernel_module
# never reads it; production uses the real stock amdgpu path to choose compression.
artifact="$work/amdgpu.ko.zst"
srpm="$(build_kernel_module "$kernel" "$build" "$work/build" "$artifact" "$work/stock-amdgpu.ko.zst")"
[[ -s "$artifact" ]] || { echo "ERROR: kernel build check produced no amdgpu module." >&2; exit 2; }
[[ -s "$srpm" ]] || { echo "ERROR: kernel build check lost its exact Fedora kernel SRPM." >&2; exit 2; }

vermagic="$(modinfo -F vermagic "$artifact" 2>/dev/null || true)"
[[ "$vermagic" == "$kernel "* ]] || {
  echo "ERROR: built amdgpu vermagic does not match $kernel ($vermagic)." >&2
  exit 2
}

abi_sha="$(verify_module_abi "$build" "$artifact" "$work/abi" "$kernel")"
[[ "$abi_sha" =~ ^[0-9a-f]{64}$ ]] || {
  echo "ERROR: module ABI evidence digest is invalid." >&2
  exit 2
}
provenance="$work/build/kernel-source-provenance.txt"
[[ -s "$provenance" ]] || { echo "ERROR: Fedora-prepared kernel provenance evidence is missing." >&2; exit 2; }
grep -qx 'mode=fedora-prepared-source' "$provenance" || {
  echo "ERROR: kernel build check did not use Fedora-prepared source authority." >&2
  exit 2
}
grep -Eq '^target_manifest_sha256=[0-9a-f]{64}$' "$provenance" || {
  echo "ERROR: kernel build check target-manifest evidence is invalid." >&2
  exit 2
}

printf 'Exact Fedora GFX1013 kernel build/ABI check passed: %s / %s / %s\n' \
  "$kernel" "$(basename "$srpm")" "$abi_sha"

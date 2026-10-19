#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export BC250_GFX1013_LIBRARY_ONLY=1
export BC250_GFX1013_SOURCE="${BC250_GFX1013_SOURCE:-$ROOT/gfx1013/upstream}"
export BC250_GFX1013_CACHE_ROOT="${BC250_GFX1013_CACHE_ROOT:-$ROOT/sources/gfx1013}"
export BC250_GFX1013_BUILD_PROGRESS="${BC250_GFX1013_BUILD_PROGRESS:-1}"
export BC250_GFX1013_HEARTBEAT_SECONDS="${BC250_GFX1013_HEARTBEAT_SECONDS:-60}"

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
requested_kernel="${BC250_GFX1013_KERNEL:-}"
running_kernel="$(uname -r)"
qualification_kernel="$(python3 "$ROOT/scripts/release-contract.py" field gfx1013.qualification_kernel)"

if [[ -n "$requested_kernel" ]]; then
  kernel="$requested_kernel"
  build="/usr/src/kernels/$kernel"
elif [[ -d "/usr/src/kernels/$running_kernel" ]]; then
  kernel="$running_kernel"
  build="/usr/src/kernels/$kernel"
elif ((${#builds[@]} == 1)); then
  # Containerized CI may not run the Fedora kernel whose devel tree it installs.
  # In that case a single installed tree is still unambiguous authority.
  build="${builds[0]}"
  kernel="${build##*/}"
else
  echo "ERROR: cannot select an authoritative Fedora kernel-devel tree." >&2
  echo "ERROR: running kernel is $running_kernel and no matching tree exists at /usr/src/kernels/$running_kernel." >&2
  echo "ERROR: set BC250_GFX1013_KERNEL=<kernel-release> explicitly when multiple trees are installed." >&2
  printf '  %s\n' "${builds[@]:-}" >&2
  exit 2
fi

if [[ ! -d "$build" ]]; then
  echo "ERROR: selected kernel-devel tree is missing: $build" >&2
  exit 2
fi

if [[ "$kernel" != "$qualification_kernel" ]]; then
  echo "ERROR: release GFX1013 kernel check selected $kernel but release-contract qualification kernel is $qualification_kernel." >&2
  echo "ERROR: update the explicit qualification identity only when intentionally qualifying a new Fedora kernel." >&2
  exit 2
fi

# Fedora kernel %prep uses macros supplied by its BuildRequires.  Keep the
# actual build unprivileged, but fail early if the privileged provisioning
# step was skipped or incomplete instead of letting an unexpanded %macro reach
# /bin/sh as a misleading "fg: no job control" failure.
if [[ "$(rpm --eval '%{defined py3_shebang_fix}' 2>/dev/null || true)" != 1 ]]; then
  echo "ERROR: Fedora kernel buildroot is incomplete: %py3_shebang_fix is undefined." >&2
  echo "ERROR: provision the exact kernel SRPM BuildRequires first (CI: scripts/provision-gfx1013-kernel-builddeps.sh)." >&2
  exit 2
fi

work="$(mktemp -d)"
diagnostics_root="${BC250_GFX1013_DIAGNOSTICS_DIR:-${BC250_BUILD_DIR:-$ROOT/build}/diagnostics/gfx1013-kernel}"
cleanup() {
  local rc=$?
  if ((rc != 0)); then
    mkdir -p "$diagnostics_root" 2>/dev/null || true
    cp -a "$work"/. "$diagnostics_root"/ 2>/dev/null || true
    echo "ERROR: GFX1013 kernel build check failed; diagnostics copied to $diagnostics_root" >&2
    # Only print logs created by this checker.  The unpacked Linux source tree
    # contains upstream *.log KUnit fixtures, including intentional failures,
    # which are evidence noise rather than output from this invocation.
    while IFS= read -r log; do
      echo "===== ${log#$work/} =====" >&2
      cat "$log" >&2 || true
    done < <(find "$work/build" -maxdepth 1 -type f -name '*.log' -print 2>/dev/null | sort)
  fi
  if [[ ${BC250_GFX1013_KEEP_WORK:-0} == 1 ]]; then
    echo "GFX1013 kernel check work directory: $work" >&2
  else
    rm -rf -- "$work"
  fi
  return "$rc"
}
trap cleanup EXIT
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

mapfile -t module_identity < <(validate_built_module_identity "$build" "$artifact" "$work/abi" "$kernel" "$work/module-identity.txt")
((${#module_identity[@]} == 5)) || {
  echo "ERROR: module identity validation returned incomplete evidence." >&2
  exit 2
}
module_sha="${module_identity[0]}"
vermagic="${module_identity[1]}"
abi_mode="${module_identity[2]}"
abi_sha="${module_identity[3]}"
srcversion="${module_identity[4]}"
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

printf 'Exact Fedora GFX1013 kernel build/ABI/module-identity check passed: %s / %s / %s / srcversion=%s\n' \
  "$kernel" "$(basename "$srpm")" "$abi_sha" "$srcversion"

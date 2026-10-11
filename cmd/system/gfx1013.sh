#!/usr/bin/env bash
# Package-owned opt-in GFX1013 compute-queue lifecycle for the BC-250 LLM appliance.
set -Eeuo pipefail
umask 0022

PREFIX_ROOT="${BC250_GFX1013_PREFIX_ROOT:-/opt/bc250-gfx1013}"
SOURCE="${BC250_GFX1013_SOURCE:-/usr/share/bc250-llm-server/gfx1013/upstream}"
STATE_ROOT="${BC250_GFX1013_STATE_ROOT:-/var/lib/bc250-llm-server/gfx1013}"
CACHE_ROOT="${BC250_GFX1013_CACHE_ROOT:-/var/cache/bc250-llm-server/gfx1013}"
DROPIN="${BC250_GFX1013_DROPIN:-/etc/systemd/system/ollama.service.d/70-bc250-gfx1013.conf}"
UPSTREAM_GENERATOR="${BC250_GFX1013_UPSTREAM_GENERATOR:-/usr/lib/systemd/user-environment-generators/60-bc250-gfx1013-v33}"
UPSTREAM_STATE="${BC250_GFX1013_UPSTREAM_STATE:-/var/lib/bc250-gfx1013}"
PACKAGE_PROFILE=v0.2.2-alpha
UPSTREAM_VERSION=0.2.0-alpha
PINNED_COMMIT=d3e6dc062c34d2523db0abe5741d1f5b0dea00d9
TESTED_KERNEL=7.2.9-200.fc44.x86_64
MESA_VERSION=26.2.4
MESA_FEDORA_RELEASE=1.fc44
MESA_SRPM_NEVRA="mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src"
MESA_SRPM_CANONICAL_URL="https://kojipkgs.fedoraproject.org/packages/mesa/${MESA_VERSION}/${MESA_FEDORA_RELEASE}/src/mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm"
MESA_SRPM_URL="${BC250_GFX1013_MESA_SRPM_URL:-$MESA_SRPM_CANONICAL_URL}"
MESA_SOURCE0="mesa-${MESA_VERSION}.tar.xz"
MESA_SOURCE0_SHA256=bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9
ACTIVE_STATE="$STATE_ROOT/active.env"
PATCH_MARKER=bc250.gfx1013_v33=1
PROFILE_VARIANT=bc250-gfx1013-v33
INSTALLED_SELF="${BC250_GFX1013_INSTALLED_SELF:-/usr/libexec/bc250-llm-server/gfx1013.sh}"

usage() {
  cat <<'USAGE'
Usage: bc250 gfx1013 {status|prepare|enable|disable|reset|benchmark}

Experimental BC-250 GFX1013 compute-queue profile. Default is OFF.

  status [--json]
           Report lifecycle state, package/kernel identity, boot safety and RADV state.
  prepare [--check]
           Check prerequisites or build the pinned V33 module + private RADV for the
           exact running kernel and stage one patched boot. Stock remains default.
  enable   From a successful patched boot, verify the exact BC-250 RADV device, make
           that boot the saved default and enable Ollama-only VK_DRIVER_FILES.
  disable [--check]
           Check rollback or restore a verified stock saved + next boot first, then
           remove the Ollama override and package-owned GFX1013 artifacts.
  reset [--check]
           Recovery path. Prove a current stock boot path, then remove stale/orphaned
           package GFX1013 artifacts. Fails closed if stock boot cannot be proven.
  benchmark {stock|gfx|restored|status|report} ...
           Reboot-aware same-package A1/B/A2 LLM performance campaign. Benchmarking
           never changes boot state or enables/disables GFX1013 itself.

The package profile is v0.2.2-alpha, based on upstream 0.2.0-alpha commit
 d3e6dc062c34d2523db0abe5741d1f5b0dea00d9. Mesh/task, 40-CU, FSR and tuning
changes are outside this profile.
USAGE
}

benchmark_helper() {
  local override script_dir
  override="${BC250_GFX1013_BENCHMARK_HELPER:-}"
  if [[ -n "$override" ]]; then
    printf '%s\n' "$override"
    return 0
  fi
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -x "$script_dir/gfx1013-ab.py" ]]; then
    printf '%s\n' "$script_dir/gfx1013-ab.py"
  elif [[ -x "$script_dir/../benchmark/gfx1013-ab.py" ]]; then
    printf '%s\n' "$script_dir/../benchmark/gfx1013-ab.py"
  else
    return 1
  fi
}

benchmark() {
  local helper
  helper="$(benchmark_helper)" || die "GFX1013 benchmark helper is unavailable"
  shift
  exec python3 "$helper" "$@"
}

say() { printf '%s\n' "$*"; }
die() {
  local message="$*"
  if [[ -n ${PREPARE_DIR:-} && ${PREPARE_COMMITTED:-1} != 1 ]]; then
    PREPARE_FAILURE_REASON="$message"
  fi
  printf 'ERROR: %s\n' "$message" >&2
  exit 2
}
need_root() { [[ ${EUID:-$(id -u)} -eq 0 ]] || die "requires root (run with sudo)"; }
kernel_release() { uname -r; }
prepared_dir_for() { printf '%s/prepared/%s' "$STATE_ROOT" "$1"; }
prepared_stamp_for() { printf '%s/prepared.env' "$(prepared_dir_for "$1")"; }
private_prefix() { printf '%s/%s' "$PREFIX_ROOT" "$UPSTREAM_VERSION"; }
private_icd() { printf '%s/share/vulkan/icd.d/radeon_icd.x86_64.json' "$(private_prefix)"; }
private_radv_lib() { printf '%s/lib64/libvulkan_radeon.so' "$(private_prefix)"; }

package_nevra() {
  command -v rpm >/dev/null 2>&1 || return 0
  rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' bc250-llm-server 2>/dev/null | head -1 || true
}

secure_boot_state() {
  local output value efivar
  if command -v mokutil >/dev/null 2>&1; then
    output="$(LC_ALL=C mokutil --sb-state 2>&1 || true)"
    if grep -qi 'SecureBoot enabled' <<<"$output"; then printf 'enabled\n'; return 0; fi
    if grep -qi 'SecureBoot disabled' <<<"$output"; then printf 'disabled\n'; return 0; fi
    if grep -Eqi "does(n't| not) support Secure Boot|Secure Boot.*unsupported|SecureBoot.*unsupported" <<<"$output"; then
      printf 'disabled-unsupported\n'
      return 0
    fi
  fi
  if [[ ! -d /sys/firmware/efi ]]; then
    printf 'disabled-non-efi\n'
    return 0
  fi
  efivar="$(find /sys/firmware/efi/efivars -maxdepth 1 -type f -name 'SecureBoot-*' -print -quit 2>/dev/null || true)"
  if [[ -n "$efivar" && -r "$efivar" ]]; then
    value="$(python3 - "$efivar" <<'PY_SB'
import sys
from pathlib import Path
try:
    data = Path(sys.argv[1]).read_bytes()
except OSError:
    raise SystemExit(2)
if len(data) < 5:
    raise SystemExit(2)
print(data[4])
PY_SB
    )" || { printf 'unknown\n'; return 0; }
    case "$value" in
      0) printf 'disabled\n' ;;
      1) printf 'enabled\n' ;;
      *) printf 'unknown\n' ;;
    esac
    return 0
  fi
  printf 'unknown\n'
}

secure_boot_prepare_ok() {
  local state
  state="$(secure_boot_state)"
  case "$state" in
    disabled|disabled-non-efi|disabled-unsupported) return 0 ;;
    enabled) die "Secure Boot is enabled; the package does not sign or enroll its locally built amdgpu module. Disable Secure Boot or use an operator-managed signing workflow before prepare." ;;
    *) die "Secure Boot state cannot be established; refusing to stage an unsigned local amdgpu module" ;;
  esac
}

GFX_BUILD_PACKAGES=(
  gcc gcc-c++ make rpm rpm-build cargo rust cargo-rpm-macros binutils bzip2 cpio dracut patch xz
  elfutils-libelf-devel openssl-devel meson ninja-build
  bison flex python3-mako python3-pycparser python3-pyyaml python3-packaging glslang glslang-devel
  vulkan-headers vulkan-loader-devel systemd-devel libdisplay-info-devel
  libdrm-devel libxcb-devel libX11-devel
  libxshmfence-devel libXrandr-devel wayland-devel wayland-protocols-devel expat-devel
  zlib-devel libzstd-devel spirv-tools-devel
)

build_requirement_provider() {
  local requirement=$1
  rpm -q --whatprovides --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' \
    "$requirement" 2>/dev/null | head -1 || true
}

missing_build_packages() {
  local requirement provider missing=()
  for requirement in "${GFX_BUILD_PACKAGES[@]}"; do
    provider="$(build_requirement_provider "$requirement")"
    [[ -n "$provider" ]] || missing+=("$requirement")
  done
  ((${#missing[@]})) && printf '%s\n' "${missing[@]}"
  return 0
}

read_one_line() {
  local file=$1
  [[ -r "$file" ]] || return 1
  IFS= read -r REPLY < "$file" || [[ -n ${REPLY:-} ]]
}

source_identity_ok() {
  local value
  [[ -r "$SOURCE/SOURCE-REVISION" && -r "$SOURCE/PACKAGE-PROFILE-VERSION" && -r "$SOURCE/VERSION" ]] || return 1
  read_one_line "$SOURCE/SOURCE-REVISION" || return 1; value=$REPLY
  [[ "$value" == "$PINNED_COMMIT" ]] || return 1
  read_one_line "$SOURCE/PACKAGE-PROFILE-VERSION" || return 1; value=$REPLY
  [[ "$value" == "${PACKAGE_PROFILE#v}" || "$value" == "$PACKAGE_PROFILE" ]] || return 1
  read_one_line "$SOURCE/VERSION" || return 1; value=$REPLY
  [[ "$value" == "$UPSTREAM_VERSION" ]] || return 1
  [[ -s "$SOURCE/PATCH-SHA256SUMS" && -s "$SOURCE/SOURCE-SHA256SUMS" ]] || return 1
  (cd "$SOURCE" && sha256sum --quiet -c PATCH-SHA256SUMS) || return 1
  (cd "$SOURCE" && sha256sum --quiet -c SOURCE-SHA256SUMS) || return 1
  # Cross-check the package constants against the carried Fedora Mesa provenance.
  [[ -r "$SOURCE/MESA-SOURCE" ]] || return 1
  grep -qx "version=$MESA_VERSION" "$SOURCE/MESA-SOURCE" || return 1
  grep -qx "fedora_release=$MESA_FEDORA_RELEASE" "$SOURCE/MESA-SOURCE" || return 1
  grep -qx "srpm_nevra=$MESA_SRPM_NEVRA" "$SOURCE/MESA-SOURCE" || return 1
  grep -qx "srpm_url=$MESA_SRPM_CANONICAL_URL" "$SOURCE/MESA-SOURCE" || return 1
  grep -qx "source0=$MESA_SOURCE0" "$SOURCE/MESA-SOURCE" || return 1
  grep -qx "source0_sha256=$MESA_SOURCE0_SHA256" "$SOURCE/MESA-SOURCE" || return 1
  # This package profile deliberately applies only the compute-queue Mesa patch.
  [[ "$(grep -Ev '^[[:space:]]*(#|$)' "$SOURCE/patches/mesa/series")" == "0001-gfx1013-compute-queue-fix.patch" ]] || return 1
}

source_manifest_sha() { sha256sum "$SOURCE/SOURCE-SHA256SUMS" | awk '{print $1}'; }
patch_manifest_sha() { sha256sum "$SOURCE/PATCH-SHA256SUMS" | awk '{print $1}'; }

kernel_build_owner() {
  local kernel=$1 build=$2 probe owner
  probe="$build/Makefile"
  [[ -r "$probe" ]] || return 1
  owner="$(rpm -qf --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' "$probe" 2>/dev/null | head -1)"
  [[ "$owner" == "kernel-devel-${kernel}" ]] || return 1
  printf '%s\n' "$owner"
}

bc250_device_present() {
  local d
  for d in /sys/bus/pci/devices/*; do
    [[ -r "$d/vendor" && -r "$d/device" ]] || continue
    [[ "$(<"$d/vendor")" == 0x1002 && "$(<"$d/device")" == 0x13fe ]] && return 0
  done
  return 1
}

patched_boot_running() { grep -qw "$PATCH_MARKER" /proc/cmdline 2>/dev/null; }

grub_value() {
  local key=$1
  command -v grub2-editenv >/dev/null 2>&1 || return 0
  grub2-editenv list 2>/dev/null | sed -n "s/^${key}=//p" | head -1 || true
}

load_active_state() {
  [[ -r "$ACTIVE_STATE" ]] || return 1
  # Root-owned state generated by this script. Restrict all values before use.
  # shellcheck disable=SC1090
  . "$ACTIVE_STATE"
  [[ "${BC250_GFX1013_PROFILE:-}" == "$PACKAGE_PROFILE" ]] || return 1
  [[ "${BC250_GFX1013_UPSTREAM_VERSION:-}" == "$UPSTREAM_VERSION" ]] || return 1
  [[ "${BC250_GFX1013_COMMIT:-}" == "$PINNED_COMMIT" ]] || return 1
  [[ "${BC250_GFX1013_KERNEL:-}" =~ ^[A-Za-z0-9._+-]+$ ]] || return 1
  [[ "${BC250_GFX1013_STOCK_ENTRY_ID:-}" =~ ^[A-Za-z0-9._+-]+$ ]] || return 1
  [[ "${BC250_GFX1013_PATCHED_ENTRY_ID:-}" =~ ^[A-Za-z0-9._+-]+$ ]] || return 1
  [[ "${BC250_GFX1013_BUILD_TREE:-}" == /usr/src/kernels/"$BC250_GFX1013_KERNEL" ||
     "${BC250_GFX1013_BUILD_TREE:-}" == /lib/modules/"$BC250_GFX1013_KERNEL"/build ]] || return 1
  [[ "${BC250_GFX1013_KERNEL_DEVEL_NEVRA:-}" == "kernel-devel-${BC250_GFX1013_KERNEL}" ]] || return 1
  [[ "${BC250_GFX1013_MODULE:-}" == "$STATE_ROOT/prepared/$BC250_GFX1013_KERNEL"/amdgpu.ko* ]] || return 1
  [[ "${BC250_GFX1013_PRIVATE_PREFIX:-}" == "$(private_prefix)" ]] || return 1
  [[ "${BC250_GFX1013_PRIVATE_RADV_LIB:-}" == "$(private_radv_lib)" ]] || return 1
  [[ "${BC250_GFX1013_ICD:-}" == "$(private_icd)" ]] || return 1
  [[ "${BC250_GFX1013_PATCHED_BLS:-}" == "/boot/loader/entries/${BC250_GFX1013_PATCHED_ENTRY_ID}.conf" ]] || return 1
  [[ "${BC250_GFX1013_PATCHED_INITRAMFS:-}" == "/boot/initramfs-${BC250_GFX1013_KERNEL}-${PROFILE_VARIANT}.img" ]] || return 1
  [[ "${BC250_GFX1013_STOCK_BLS:-}" == "/boot/loader/entries/${BC250_GFX1013_STOCK_ENTRY_ID}.conf" ]] || return 1
  [[ "${BC250_GFX1013_STOCK_MODULE:-}" == /usr/lib/modules/"$BC250_GFX1013_KERNEL"/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko* ||
     "${BC250_GFX1013_STOCK_MODULE:-}" == /lib/modules/"$BC250_GFX1013_KERNEL"/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko* ]] || return 1
  [[ "${BC250_GFX1013_ENABLED:-0}" =~ ^[01]$ ]] || return 1
  [[ "${BC250_GFX1013_RECOVERY_REQUIRED:-0}" =~ ^[01]$ ]] || return 1
  [[ "${BC250_GFX1013_TRANSACTION_PHASE:-}" =~ ^(BOOT_ENTRY_STAGING|PREPARED|ENABLING|ENABLED|DISABLING|RECOVERY_REQUIRED|SAFETY_FAILURE)$ ]] || return 1
  [[ "${BC250_GFX1013_KERNEL_SRPM_NEVR:-}" =~ ^kernel-[A-Za-z0-9._+~-]+$ ]] || return 1
  [[ "${BC250_GFX1013_KERNEL_SOURCE_PROVENANCE_MODE:-}" == fedora-prepared-source ]] || return 1
  [[ "${BC250_GFX1013_ABI_MODE:-}" =~ ^(modversions|symbol-resolution)$ ]] || return 1
  [[ "${BC250_GFX1013_MESA_SRPM_NEVRA:-}" == "$MESA_SRPM_NEVRA" ]] || return 1
  local hash_name
  for hash_name in \
    BC250_GFX1013_MODULE_SHA256 BC250_GFX1013_ABI_SHA256 \
    BC250_GFX1013_PATCH_MANIFEST_SHA256 BC250_GFX1013_SOURCE_MANIFEST_SHA256 \
    BC250_GFX1013_KERNEL_SRPM_SHA256 BC250_GFX1013_KERNEL_SOURCE_PROVENANCE_SHA256 \
    BC250_GFX1013_KERNEL_TARGET_MANIFEST_SHA256 BC250_GFX1013_MESA_SRPM_SHA256 \
    BC250_GFX1013_MESA_SOURCE_SHA256 BC250_GFX1013_STOCK_MODULE_SHA256 BC250_GFX1013_STOCK_INITRAMFS_SHA256 \
    BC250_GFX1013_PRIVATE_RADV_SHA256 BC250_GFX1013_ICD_SHA256; do
    [[ "${!hash_name:-}" =~ ^[0-9a-f]{64}$ ]] || return 1
  done
  [[ "${BC250_GFX1013_MODULE_SRCVERSION:-}" =~ ^[A-Za-z0-9]*$ ]] || return 1
  if [[ -n "${BC250_GFX1013_PACKAGE_NEVRA:-}" ]]; then
    [[ "$BC250_GFX1013_PACKAGE_NEVRA" =~ ^bc250-llm-server-[A-Za-z0-9._+~:-]+\.x86_64$ ]] || return 1
  fi
}

kernel_state() {
  local kernel build
  kernel="$(kernel_release)"
  build="/lib/modules/$kernel/build"
  printf 'Running kernel: %s\n' "$kernel"
  if [[ -e "$build" ]]; then
    printf 'Kernel build tree: %s\n' "$(readlink -f "$build")"
  else
    printf 'Kernel build tree: MISSING (%s)\n' "$build"
  fi
  if [[ "$kernel" == "$TESTED_KERNEL" ]]; then
    printf 'Package qualification kernel: MATCH\n'
  else
    printf 'Package qualification kernel: DIFFERENT (reference %s; exact-kernel rebuild required)\n' "$TESTED_KERNEL"
  fi
}

stock_entry_file_safe() {
  local path=$1
  [[ -f "$path" ]] || return 1
  grep -qw "$PATCH_MARKER" "$path" 2>/dev/null && return 1
  return 0
}

GFX_STATE_REASON=''
GFX_LIFECYCLE_STATE='BROKEN'
gfx_lifecycle_state() {
  local current_kernel current_package saved enabled
  GFX_STATE_REASON=''
  current_kernel="$(kernel_release)"
  current_package="$(package_nevra)"
  saved="$(grub_value saved_entry)"

  if [[ ! -e "$ACTIVE_STATE" ]]; then
    if risky_artifacts_without_state; then
      GFX_STATE_REASON='package GFX1013 artifacts exist without valid lifecycle state'
      GFX_LIFECYCLE_STATE=BROKEN
    else
      GFX_STATE_REASON='no prepared or active GFX1013 profile'
      GFX_LIFECYCLE_STATE=DISABLED
    fi
    return 0
  fi
  if ! load_active_state; then
    GFX_STATE_REASON='active lifecycle state exists but failed validation'
    GFX_LIFECYCLE_STATE=BROKEN
    return 0
  fi
  if [[ "${BC250_GFX1013_RECOVERY_REQUIRED:-0}" == 1 || "${BC250_GFX1013_TRANSACTION_PHASE:-}" =~ ^(RECOVERY_REQUIRED|SAFETY_FAILURE|ENABLING|DISABLING|BOOT_ENTRY_STAGING)$ ]]; then
    GFX_STATE_REASON="lifecycle transaction requires recovery (${BC250_GFX1013_TRANSACTION_PHASE:-unknown})"
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if [[ -z "${BC250_GFX1013_PACKAGE_NEVRA:-}" ]]; then
    GFX_STATE_REASON='pre-1.6 preparation lacks package identity; rollback/reprepare required'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if [[ -z "$current_package" || "$current_package" != "$BC250_GFX1013_PACKAGE_NEVRA" ]]; then
    GFX_STATE_REASON="package identity changed since prepare (${BC250_GFX1013_PACKAGE_NEVRA} -> ${current_package:-unavailable})"
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if ! stock_entry_file_safe "$BC250_GFX1013_STOCK_BLS"; then
    GFX_STATE_REASON='recorded stock BLS entry is missing or contains the patched marker'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if [[ "$current_kernel" != "$BC250_GFX1013_KERNEL" ]]; then
    if patched_boot_running; then
      GFX_STATE_REASON="patched marker is present on kernel $current_kernel but preparation belongs to $BC250_GFX1013_KERNEL"
      GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    else
      GFX_STATE_REASON="running kernel $current_kernel differs from prepared kernel $BC250_GFX1013_KERNEL; Ollama start is fail-closed until rollback/reprepare so private RADV cannot run on the stale kernel"
      GFX_LIFECYCLE_STATE=STALE_KERNEL
    fi
    return 0
  fi

  enabled="${BC250_GFX1013_ENABLED:-0}"
  if [[ "$enabled" == 1 ]]; then
    if ! patched_boot_running; then
      GFX_STATE_REASON='state says enabled but current boot is not the marked patched boot'
      GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED; return 0
    fi
    if [[ ! -f "$DROPIN" || ! -f "$BC250_GFX1013_ICD" || ! -f "$BC250_GFX1013_PRIVATE_RADV_LIB" ]]; then
      GFX_STATE_REASON='enabled state is missing the Ollama override or private RADV payload'
      GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED; return 0
    fi
    if [[ "$saved" != "$BC250_GFX1013_PATCHED_ENTRY_ID" ]]; then
      GFX_STATE_REASON='enabled state does not have the patched BLS entry as saved/default'
      GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED; return 0
    fi
    GFX_STATE_REASON='verified lifecycle state records GFX1013 as enabled'
    GFX_LIFECYCLE_STATE=ENABLED
    return 0
  fi

  if [[ -f "$DROPIN" ]]; then
    GFX_STATE_REASON='Ollama private-RADV override exists while lifecycle state is not enabled'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
  elif patched_boot_running; then
    GFX_STATE_REASON='running the one-shot patched boot; enable has not yet committed'
    GFX_LIFECYCLE_STATE=PATCHED_BOOT_UNVERIFIED
  elif [[ "$saved" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]]; then
    GFX_STATE_REASON='patched boot is saved/default while lifecycle state is not enabled'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
  else
    GFX_STATE_REASON='exact-kernel profile is prepared; stock boot remains authoritative'
    GFX_LIFECYCLE_STATE=PREPARED
  fi
}

status_json() {
  local state reason source_ok device_ok secure saved next current_package prepared_package
  local prepared_kernel enabled icd_present radv_present dropin_present patched_running
  gfx_lifecycle_state
  state="$GFX_LIFECYCLE_STATE"; reason="$GFX_STATE_REASON"
  source_ok=false; source_identity_ok && source_ok=true
  device_ok=false; bc250_device_present && device_ok=true
  secure="$(secure_boot_state)"
  saved="$(grub_value saved_entry)"; next="$(grub_value next_entry)"
  current_package="$(package_nevra)"
  prepared_package=''; prepared_kernel=''; enabled='0'
  if load_active_state; then
    prepared_package="${BC250_GFX1013_PACKAGE_NEVRA:-}"
    prepared_kernel="${BC250_GFX1013_KERNEL:-}"
    enabled="${BC250_GFX1013_ENABLED:-0}"
  fi
  icd_present=false; [[ -f "$(private_icd)" ]] && icd_present=true
  radv_present=false; [[ -f "$(private_radv_lib)" ]] && radv_present=true
  dropin_present=false; [[ -f "$DROPIN" ]] && dropin_present=true
  patched_running=false; patched_boot_running && patched_running=true
  python3 - "$state" "$reason" "$PACKAGE_PROFILE" "$UPSTREAM_VERSION" "$PINNED_COMMIT" \
    "$(kernel_release)" "$TESTED_KERNEL" "$secure" "$source_ok" "$device_ok" \
    "$current_package" "$prepared_package" "$prepared_kernel" "$enabled" "$saved" "$next" \
    "$patched_running" "$dropin_present" "$radv_present" "$icd_present" \
    "${BC250_GFX1013_STOCK_ENTRY_ID:-}" "${BC250_GFX1013_PATCHED_ENTRY_ID:-}" \
    "${BC250_GFX1013_VULKAN_VENDOR_ID:-}" "${BC250_GFX1013_VULKAN_DEVICE_ID:-}" \
    "${BC250_GFX1013_VULKAN_DRIVER_NAME:-}" "${BC250_GFX1013_VULKAN_SUMMARY_SHA256:-}" \
    "$MESA_VERSION" "$MESA_SRPM_NEVRA" "$MESA_SOURCE0" "$MESA_SOURCE0_SHA256" <<'PY_JSON'
import json
import sys
(
    state, reason, profile, upstream, commit, running_kernel, tested_kernel, secure_boot,
    source_ok, device_ok, package, prepared_package, prepared_kernel, enabled, saved, next_entry,
    patched_running, dropin, radv, icd, stock_entry, patched_entry, vk_vendor, vk_device,
    vk_driver, vk_summary_sha, mesa_version, mesa_srpm_nevra, mesa_source0, mesa_source0_sha,
) = sys.argv[1:]
def b(value: str) -> bool:
    return value == "true"
payload = {
    "schema": "bc250.gfx1013-status.v1",
    "state": state,
    "reason": reason,
    "experimental": True,
    "default_off": True,
    "profile": profile,
    "upstream": {"version": upstream, "commit": commit},
    "mesa": {
        "version": mesa_version,
        "fedora_source_nevra": mesa_srpm_nevra,
        "source0": mesa_source0,
        "source0_sha256": mesa_source0_sha,
    },
    "package": {"installed_nevra": package or None, "prepared_nevra": prepared_package or None},
    "kernel": {"running": running_kernel, "prepared": prepared_kernel or None, "reference": tested_kernel},
    "secure_boot": secure_boot,
    "source_identity_ok": b(source_ok),
    "bc250_device_present": b(device_ok),
    "enabled_recorded": enabled == "1",
    "boot": {
        "patched_running": b(patched_running),
        "saved_entry": saved or None,
        "next_entry": next_entry or None,
        "stock_entry": stock_entry or None,
        "patched_entry": patched_entry or None,
    },
    "ollama_private_radv_override": b(dropin),
    "private_radv_present": b(radv),
    "private_icd_present": b(icd),
    "vulkan": {
        "vendor_id": vk_vendor or None,
        "device_id": vk_device or None,
        "driver_name": vk_driver or None,
        "summary_sha256": vk_summary_sha or None,
    },
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY_JSON
}

status() {
  local icd saved next state reason secure current_package missing_packages
  gfx_lifecycle_state
  state="$GFX_LIFECYCLE_STATE"; reason="$GFX_STATE_REASON"
  icd="$(private_icd)"
  secure="$(secure_boot_state)"
  current_package="$(package_nevra)"
  echo "GFX1013 state: $state"
  echo "State reason: $reason"
  echo "GFX1013 package profile: $PACKAGE_PROFILE / experimental / default OFF until enable"
  echo "Pinned upstream: $UPSTREAM_VERSION @ $PINNED_COMMIT"
  echo "Mesa baseline: Fedora $MESA_SRPM_NEVRA; Source0 $MESA_SOURCE0 @ sha256:$MESA_SOURCE0_SHA256"
  echo "Installed package: ${current_package:-unavailable}"
  echo "Secure Boot: $secure"
  kernel_state
  bc250_device_present && echo "BC-250 PCI 1002:13fe: present" || echo "BC-250 PCI 1002:13fe: NOT FOUND"
  if source_identity_ok; then
    echo "Package patch/full-source manifests: PASS ($SOURCE)"
  else
    echo "Package patch/full-source manifests: FAIL/MISSING ($SOURCE)"
  fi
  if load_active_state; then
    echo "Exact-kernel preparation: present ($BC250_GFX1013_KERNEL)"
    echo "Prepared package: ${BC250_GFX1013_PACKAGE_NEVRA:-legacy/unrecorded}"
    echo "Prepared module SHA256: $BC250_GFX1013_MODULE_SHA256"
    echo "Prepared vermagic: $BC250_GFX1013_VERMAGIC"
    echo "Stock boot entry: $BC250_GFX1013_STOCK_ENTRY_ID"
    echo "Patched boot entry: $BC250_GFX1013_PATCHED_ENTRY_ID"
    [[ -n "${BC250_GFX1013_VULKAN_DRIVER_NAME:-}" ]] && \
      echo "Private RADV verified device: ${BC250_GFX1013_VULKAN_VENDOR_ID:-?}:${BC250_GFX1013_VULKAN_DEVICE_ID:-?} driver=${BC250_GFX1013_VULKAN_DRIVER_NAME}"
  else
    echo "Exact-kernel preparation: absent or invalid"
  fi
  patched_boot_running && echo "Running boot: patched GFX1013" || echo "Running boot: stock/unmarked"
  command -v grub2-editenv >/dev/null 2>&1 && {
    saved="$(grub_value saved_entry)"; next="$(grub_value next_entry)"
    echo "GRUB saved entry: ${saved:-<unset>}"
    echo "GRUB next entry: ${next:-<unset>}"
  }
  [[ -f "$icd" ]] && echo "Private RADV: present ($icd)" || echo "Private RADV: absent"
  [[ -f "$DROPIN" ]] && echo "Ollama private-RADV override: ENABLED" || echo "Ollama private-RADV override: disabled"
  [[ -e "$UPSTREAM_GENERATOR" || -e "$UPSTREAM_STATE/active.env" ]] \
    && echo "Separate upstream GFX1013 installation: CONFLICT" \
    || echo "Separate upstream GFX1013 installation: absent"
  missing_packages="$(missing_build_packages)"
  if [[ -n "$missing_packages" ]]; then
    echo "Optional GFX build requirements: missing"
    while IFS= read -r package; do
      [[ -n "$package" ]] && printf '  requirement: %s; provider: <none>; status: MISSING\n' "$package"
    done <<< "$missing_packages"
  else
    echo "Optional GFX build requirements: satisfied (provider-aware)"
  fi
}

check_os_and_boot_tools() {
  [[ -r /etc/os-release ]] || die "/etc/os-release is missing"
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == fedora ]] || die "GFX1013 package profile supports Fedora only"
  command -v rpm-ostree >/dev/null 2>&1 && die "image/Atomic Fedora is not supported by this direct exact-kernel profile"
  local cmd missing=()
  for cmd in curl xz zstd gzip bzip2 tar cpio patch gcc g++ make cargo rpm rpm2cpio rpmbuild meson ninja python3 nm \
    sha256sum modinfo modprobe depmod dracut lsinitrd grub2-editenv grub2-set-default awk sed grep find install; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if ((${#missing[@]})); then
    printf 'ERROR: GFX1013 build/install tools missing: %s\n' "${missing[*]}" >&2
    printf 'Install the optional build dependencies and exact running-kernel headers, for example:\n' >&2
    printf '  sudo dnf install kernel-devel-%s gcc gcc-c++ make rpm-build cargo rust cargo-rpm-macros binutils bzip2 elfutils-libelf-devel openssl-devel meson ninja-build bison flex python3-mako python3-pycparser python3-pyyaml python3-packaging glslang glslang-devel vulkan-headers vulkan-loader-devel systemd-devel libdisplay-info-devel libdrm-devel libxcb-devel libX11-devel libxshmfence-devel libXrandr-devel wayland-devel wayland-protocols-devel expat-devel zlib-devel libzstd-devel spirv-tools-devel\n' "$(kernel_release | sed 's/\.x86_64$//')" >&2
    exit 2
  fi
  local missing_packages package
  local -a missing_package_list=()
  missing_packages="$(missing_build_packages)"
  if [[ -n "$missing_packages" ]]; then
    mapfile -t missing_package_list <<< "$missing_packages"
    printf 'ERROR: optional GFX1013 build requirements missing:\n' >&2
    for package in "${missing_package_list[@]}"; do [[ -n "$package" ]] && printf '  requirement: %s; provider: <none>; status: MISSING\n' "$package" >&2; done
    printf 'Install them with: sudo dnf install' >&2
    for package in "${missing_package_list[@]}"; do [[ -n "$package" ]] && printf ' %q' "$package" >&2; done
    printf '\n' >&2
    exit 2
  fi
  secure_boot_prepare_ok
}

fetch_file() {
  local url=$1 dest=$2
  if [[ -s "$dest" ]]; then return 0; fi
  install -d -m 0750 "$(dirname "$dest")"
  curl -fL --retry 3 --retry-delay 2 -o "$dest.part" "$url"
  mv -f "$dest.part" "$dest"
}

find_stock_module() {
  local kernel=$1 path
  path="$(modinfo -n amdgpu 2>/dev/null || true)"
  [[ -n "$path" ]] || return 1
  path="$(readlink -f "$path")"
  [[ "$path" == /usr/lib/modules/"$kernel"/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko* ||
     "$path" == /lib/modules/"$kernel"/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko* ]] || return 1
  printf '%s\n' "$path"
}

find_stock_bls() {
  local kernel=$1 machine candidate entry
  machine="$(< /etc/machine-id)"
  candidate="/boot/loader/entries/${machine}-${kernel}.conf"
  if [[ -f "$candidate" ]]; then printf '%s\n' "$candidate"; return 0; fi
  local -a matches=()
  while IFS= read -r entry; do
    [[ "$entry" == *"-$PROFILE_VARIANT.conf" ]] && continue
    grep -Eq "^version[[:space:]]+${kernel//./\\.}([[:space:]]|$)" "$entry" && matches+=("$entry")
  done < <(find /boot/loader/entries -maxdepth 1 -type f -name '*.conf' -print 2>/dev/null | sort)
  ((${#matches[@]} == 1)) || return 1
  printf '%s\n' "${matches[0]}"
}

compress_module_like_stock() {
  local raw=$1 stock=$2 out=$3
  case "$stock" in
    *.xz) xz -9 -c "$raw" > "$out" ;;
    *.zst) zstd -q -19 -c "$raw" > "$out" ;;
    *.gz) gzip -9 -c "$raw" > "$out" ;;
    *.ko) cp -p "$raw" "$out" ;;
    *) die "unsupported stock amdgpu module compression: $stock" ;;
  esac
}

apply_patch_checked() {
  local tree=$1 patch_file=$2
  patch --batch --forward --fuzz=0 --dry-run -p1 -s -d "$tree" < "$patch_file" >/dev/null || \
    die "patch zero-fuzz dry-run failed: $patch_file"
  patch --batch --forward --fuzz=0 -p1 -s -d "$tree" < "$patch_file"
}

adapt_external_amd_trace_paths() {
  local amd_root=$1
  python3 - "$amd_root" <<'PY_TRACE'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
path = root / "amdgpu" / "amdgpu_trace.h"
old = "#define TRACE_INCLUDE_PATH ../../drivers/gpu/drm/amd/amdgpu"
if not path.is_file():
    raise SystemExit(f"required AMD trace header is missing: {path}")
text = path.read_text(encoding="utf-8", errors="strict")
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one in-tree TRACE_INCLUDE_PATH in {path}, found {count}")
new = f"#define TRACE_INCLUDE_PATH {path.parent.resolve()}"
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print(f"adapted external TRACE_INCLUDE_PATH in {path}")
PY_TRACE
}

materialize_module_ko() {
  local module=$1 out=$2
  case "$module" in
    *.ko) cp -p "$module" "$out" ;;
    *.ko.xz) xz -dc "$module" > "$out" ;;
    *.ko.zst) zstd -q -dc "$module" > "$out" ;;
    *.ko.gz) gzip -dc "$module" > "$out" ;;
    *) die "unsupported built module compression for ABI verification: $module" ;;
  esac
  [[ -s "$out" ]] || die "decompressed module is empty: $module"
}

kernel_modversions_enabled() {
  local build=$1 kernel=$2 config=''
  if [[ -r "$build/.config" ]]; then
    config="$build/.config"
  elif [[ -r "/boot/config-$kernel" ]]; then
    config="/boot/config-$kernel"
  else
    die "exact kernel configuration unavailable for ABI verification"
  fi
  if grep -qx 'CONFIG_MODVERSIONS=y' "$config"; then
    return 0
  fi
  if grep -qx '# CONFIG_MODVERSIONS is not set' "$config" || grep -qx 'CONFIG_MODVERSIONS=n' "$config"; then
    return 1
  fi
  die "CONFIG_MODVERSIONS state is ambiguous in $config"
}

verify_module_abi() {
  local build=$1 module=$2 work=$3 kernel=$4 symvers="$build/Module.symvers"
  local raw="$work/abi-amdgpu.ko" required="$work/abi-required.txt"
  [[ -r "$symvers" ]] || die "kernel Module.symvers is missing: $symvers"
  materialize_module_ko "$module" "$raw"
  if kernel_modversions_enabled "$build" "$kernel"; then
    {
      echo 'mode=modversions'
      modprobe --show-modversions "$raw" 2>/dev/null | sort -u
    } > "$required" || die "unable to read module symbol versions"
    [[ "$(wc -l < "$required")" -gt 1 ]] || die "built amdgpu exposes no versioned ABI requirements"
    python3 - "$symvers" "$required" <<'PY_ABI_CRC' || die "built amdgpu symbol-version ABI does not match the exact kernel build tree"
import sys
from pathlib import Path
symvers, required = map(Path, sys.argv[1:])
known = {}
for line in symvers.read_text(encoding="utf-8", errors="replace").splitlines():
    fields = line.split()
    if len(fields) >= 2:
        known[fields[1]] = fields[0].lower()
errors = []
for line in required.read_text(encoding="utf-8", errors="replace").splitlines():
    fields = line.split()
    if len(fields) < 2 or fields[0].startswith("mode="):
        continue
    crc, symbol = fields[0].lower(), fields[1]
    actual = known.get(symbol)
    if actual is None:
        errors.append(f"missing {symbol}")
    elif actual != crc:
        errors.append(f"crc {symbol}: module={crc} kernel={actual}")
if errors:
    print("; ".join(errors[:20]), file=sys.stderr)
    raise SystemExit(1)
PY_ABI_CRC
  else
    {
      echo 'mode=symbol-resolution'
      nm -u --format=posix "$raw" | awk '$2 == "U" {print $1}' | sort -u
    } > "$required" || die "unable to enumerate built amdgpu imported symbols"
    [[ "$(wc -l < "$required")" -gt 1 ]] || die "built amdgpu exposes no strong imported symbols"
    python3 - "$symvers" "$required" <<'PY_ABI_SYMBOLS' || die "built amdgpu imports symbols absent from the exact kernel Module.symvers"
import sys
from pathlib import Path
symvers, required = map(Path, sys.argv[1:])
known = set()
for line in symvers.read_text(encoding="utf-8", errors="replace").splitlines():
    fields = line.split()
    if len(fields) >= 2:
        known.add(fields[1])
needed = [line for line in required.read_text(encoding="utf-8").splitlines() if line and not line.startswith("mode=")]
missing = [symbol for symbol in needed if symbol not in known]
if missing:
    print("missing imports: " + ", ".join(missing[:20]), file=sys.stderr)
    raise SystemExit(1)
PY_ABI_SYMBOLS
  fi
  sha256sum "$required" | awk '{print $1}'
}

prepare_fedora_kernel_source() {
  local work=$1 srpm=$2 prepared_out=$3
  local rpm_top="$work/kernel-rpmbuild" spec
  local -a specs=()
  rm -rf "$rpm_top"
  mkdir -p "$rpm_top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
  (cd "$rpm_top/SOURCES" && rpm2cpio "$srpm" | cpio -id --quiet) || \
    die "cannot extract exact Fedora kernel source RPM"

  if [[ -f "$rpm_top/SOURCES/kernel.spec" ]]; then
    spec="$rpm_top/SOURCES/kernel.spec"
  else
    mapfile -t specs < <(find "$rpm_top/SOURCES" -maxdepth 1 -type f -name '*.spec' -print | sort)
    ((${#specs[@]} == 1)) || die "kernel source RPM must contain exactly one usable spec file"
    spec="${specs[0]}"
  fi
  mv "$spec" "$rpm_top/SPECS/kernel.spec"

  # Source authority is the exact Fedora-prepared tree, not pristine Source0.
  # --nodeps avoids asking RPM to solve dependencies here; prepare_preflight is
  # responsible for the package-owned prerequisite contract.
  PREPARE_STAGE='kernel-fedora-prep'
  rpmbuild -bp --nodeps --define "_topdir $rpm_top" "$rpm_top/SPECS/kernel.spec" \
    >"$work/kernel-prep.log" 2>&1 || die "Fedora kernel %prep failed; see $work/kernel-prep.log"

  PREPARE_STAGE='kernel-source-provenance'
  python3 "$SOURCE/check-kernel-provenance.py" \
    --prepared-build-root "$rpm_top/BUILD" \
    --patch-dir "$SOURCE/patches/kernel/v33" \
    --root-output "$prepared_out" \
    --output "$work/kernel-source-provenance.txt" \
    >>"$work/kernel-build.log" 2>&1 || \
    die "Fedora-prepared kernel source-provenance check failed; see $work/kernel-build.log"
}

build_kernel_module() {
  local kernel=$1 build=$2 work=$3 artifact=$4 stock_module=$5
  local version release srpm_url srpm expected_vr actual_vr source_package source_root prepared_file linux_root patch_file raw
  version="${kernel%%-*}"
  release="${kernel#*-}"; release="${release%.*}"
  srpm_url="${BC250_GFX1013_KERNEL_SRPM_URL:-https://kojipkgs.fedoraproject.org/packages/kernel/${version}/${release}/src/kernel-${version}-${release}.src.rpm}"
  srpm="$CACHE_ROOT/kernel-${version}-${release}.src.rpm"
  fetch_file "$srpm_url" "$srpm"
  expected_vr="${kernel%.*}"
  actual_vr="$(rpm -qp --qf '%{VERSION}-%{RELEASE}\n' "$srpm" 2>/dev/null || true)"
  source_package="$(rpm -qp --qf '%{SOURCEPACKAGE}\n' "$srpm" 2>/dev/null || true)"
  [[ "$actual_vr" == "$expected_vr" ]] || die "kernel source RPM identity mismatch: expected $expected_vr, got ${actual_vr:-unreadable}"
  [[ "$source_package" == 1 ]] || die "kernel package is not marked as a source RPM"
  rpm -K "$srpm" >/dev/null 2>&1 || die "kernel source RPM failed RPM digest/signature verification"

  source_root="$work/kernel"
  rm -rf "$source_root"
  install -d -m 0750 "$source_root"
  # Keep a member inventory as bounded evidence, but do not use raw SRPM text as
  # a substitute for Fedora's own %prep source transformation.
  mkdir -p "$source_root/srpm-members"
  (cd "$source_root/srpm-members" && rpm2cpio "$srpm" | cpio -it --quiet) | LC_ALL=C sort > "$work/kernel-srpm-members.txt" || \
    die "cannot inventory exact Fedora kernel source RPM"

  prepared_file="$work/kernel-prepared-root"
  prepare_fedora_kernel_source "$work" "$srpm" "$prepared_file"
  linux_root="$(<"$prepared_file")"
  [[ -d "$linux_root/drivers/gpu/drm/amd" ]] || die "Fedora %prep did not produce the expected AMDGPU source tree"

  adapt_external_amd_trace_paths "$linux_root/drivers/gpu/drm/amd" >>"$work/kernel-build.log" 2>&1 || \
    die "AMD external-module trace-path adaptation failed; see $work/kernel-build.log"
  for patch_file in "$SOURCE"/patches/kernel/v33/*.patch; do
    apply_patch_checked "$linux_root" "$patch_file"
  done
  make -C "$build" "M=$linux_root/drivers/gpu/drm/amd/amdgpu" modules "-j$(nproc)" >>"$work/kernel-build.log" 2>&1 || \
    die "amdgpu build failed; see $work/kernel-build.log"
  raw="$linux_root/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
  [[ -f "$raw" ]] || die "amdgpu build produced no module"
  compress_module_like_stock "$raw" "$stock_module" "$artifact"
  printf '%s\n' "$srpm"
}

prepare_fedora_mesa_source() {
  local work=$1 srpm=$2 prepared_out=$3 source0_out=$4
  local rpm_top="$work/mesa-rpmbuild" spec actual_nevr source_package source0
  rm -rf "$rpm_top"
  mkdir -p "$rpm_top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
  (cd "$rpm_top/SOURCES" && rpm2cpio "$srpm" | cpio -id --quiet)
  spec="$(find "$rpm_top/SOURCES" -maxdepth 1 -type f -name 'mesa*.spec' -print -quit)"
  [[ -n "$spec" ]] || die "Mesa source RPM contains no spec file"
  mv "$spec" "$rpm_top/SPECS/mesa.spec"
  source0="$rpm_top/SOURCES/$MESA_SOURCE0"
  [[ -f "$source0" ]] || die "Mesa source RPM does not contain expected Source0: $MESA_SOURCE0"
  printf '%s  %s\n' "$MESA_SOURCE0_SHA256" "$source0" | sha256sum --quiet -c || \
    die "Fedora Mesa Source0 failed pinned SHA-256 verification"
  # Do not use %{ARCH} as the source-RPM discriminator.  Fedora source RPM
  # headers can retain the build architecture; SOURCEPACKAGE is authoritative.
  actual_nevr="$(rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}\n' "$srpm" 2>/dev/null || true)"
  source_package="$(rpm -qp --qf '%{SOURCEPACKAGE}\n' "$srpm" 2>/dev/null || true)"
  [[ "$actual_nevr" == "${MESA_SRPM_NEVRA%.src}" ]] || die "Mesa source RPM identity mismatch: expected ${MESA_SRPM_NEVRA%.src}, got ${actual_nevr:-unreadable}"
  [[ "$source_package" == 1 ]] || die "Mesa package is not marked as a source RPM"
  rpmbuild -bp --nodeps --define "_topdir $rpm_top" "$rpm_top/SPECS/mesa.spec" \
    >"$work/mesa-prep.log" 2>&1 || die "Fedora Mesa %prep failed; see $work/mesa-prep.log"
  local -a candidates=()
  mapfile -t candidates < <(find "$rpm_top/BUILD" -type f -path '*/src/amd/common/ac_gpu_info.c' -print | sort)
  ((${#candidates[@]} == 1)) || die "Fedora Mesa %prep did not produce exactly one ac_gpu_info.c"
  python3 - "${candidates[0]}" "$prepared_out" <<'PY_MESA_ROOT'
import sys
from pathlib import Path
p = Path(sys.argv[1]).resolve()
root = p.parents[3]
Path(sys.argv[2]).write_text(str(root) + "\n", encoding="utf-8")
PY_MESA_ROOT
  printf '%s\n' "$source0" > "$source0_out"
}

build_mesa() {
  local work=$1 stage=$2 info_file=$3 srpm patch_name
  local prepared_file="$work/mesa-prepared-root" source0_file="$work/mesa-source0-path" mesa_src source0
  srpm="$CACHE_ROOT/mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm"
  fetch_file "$MESA_SRPM_URL" "$srpm"
  rpm -K "$srpm" >/dev/null 2>&1 || die "Mesa source RPM failed RPM digest/signature verification"
  prepare_fedora_mesa_source "$work" "$srpm" "$prepared_file" "$source0_file"
  mesa_src="$(<"$prepared_file")"; source0="$(<"$source0_file")"
  [[ -d "$mesa_src" ]] || die "Fedora-prepared Mesa source root is missing"
  rm -rf "$stage"; install -d -m 0750 "$stage"
  while IFS= read -r patch_name; do
    [[ -z "$patch_name" || "$patch_name" == \#* ]] && continue
    apply_patch_checked "$mesa_src" "$SOURCE/patches/mesa/$patch_name"
  done < "$SOURCE/patches/mesa/series"
  meson setup "$work/mesa-build" "$mesa_src" \
    -Dvulkan-drivers=amd -Dgallium-drivers= -Dplatforms=x11,wayland \
    -Dglx=disabled -Dllvm=disabled -Dvideo-codecs= \
    -Dprefix="$(private_prefix)" -Dlibdir=lib64 -Dbuildtype=release \
    >"$work/mesa-setup.log" 2>&1 || die "Mesa setup failed; see $work/mesa-setup.log"
  ninja -C "$work/mesa-build" >"$work/mesa-build.log" 2>&1 || die "Mesa build failed; see $work/mesa-build.log"
  DESTDIR="$stage" ninja -C "$work/mesa-build" install >>"$work/mesa-build.log" 2>&1 || die "Mesa staging install failed"
  [[ -f "$stage$(private_prefix)/lib64/libvulkan_radeon.so" ]] || die "private RADV library missing from staged Mesa"
  [[ -f "$stage$(private_icd)" ]] || die "private RADV ICD missing from staged Mesa"
  printf '%s\n%s\n' "$srpm" "$source0" > "$info_file"
}

pin_private_icd_library() {
  local icd=$1 library=$2
  python3 - "$icd" "$library" <<'PY_ICD'
import json
import os
import sys
from pathlib import Path
path = Path(sys.argv[1])
library = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
icd = data.get("ICD")
if not isinstance(icd, dict):
    raise SystemExit("ICD object missing from private RADV manifest")
icd["library_path"] = library
temporary = path.with_name(path.name + ".tmp")
temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o644)
os.replace(temporary, path)
PY_ICD
}

private_icd_library_ok() {
  local icd=$1 library=$2
  python3 - "$icd" "$library" <<'PY_ICD_CHECK'
import json
import sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if data.get("ICD", {}).get("library_path") == sys.argv[2] else 1)
PY_ICD_CHECK
}

verify_private_radv_device() {
  local icd=$1 library=$2 summary identity sha
  [[ -f "$icd" && -f "$library" ]] || die "private RADV payload is incomplete"
  private_icd_library_ok "$icd" "$library" || die "private ICD does not point at the package private RADV library"
  summary="$(mktemp)"
  if ! VK_DRIVER_FILES="$icd" vulkaninfo --summary >"$summary" 2>&1; then
    rm -f "$summary"
    die "private RADV failed Vulkan loader smoke check"
  fi
  identity="$(python3 - "$summary" <<'PY_VK'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
blocks = re.split(r"(?=GPU(?: id)?\s*[:0-9])", text, flags=re.IGNORECASE)
for block in blocks:
    vendor = re.search(r"vendorID\s*=\s*(0x[0-9a-fA-F]+)", block)
    device = re.search(r"deviceID\s*=\s*(0x[0-9a-fA-F]+)", block)
    driver = re.search(r"driverName\s*=\s*([^\r\n]+)", block)
    if not vendor or not device:
        continue
    if vendor.group(1).lower() == "0x1002" and device.group(1).lower() == "0x13fe":
        name = driver.group(1).strip() if driver else ""
        if name.lower() != "radv":
            continue
        print("0x1002|0x13fe|radv")
        raise SystemExit(0)
raise SystemExit(1)
PY_VK
  )" || { rm -f "$summary"; die "private RADV did not expose BC-250 PCI 1002:13fe through the RADV driver"; }
  sha="$(sha256sum "$summary" | awk '{print $1}')"
  rm -f "$summary"
  printf '%s|%s\n' "$identity" "$sha"
}

PREPARE_COMMITTED=1
PREPARE_PATCHED_BLS=''
PREPARE_PATCHED_INITRAMFS=''
PREPARE_PRIVATE_PREFIX=''
PREPARE_PREVIOUS_NEXT=''
PREPARE_BOOT_STATE_CHANGED=0
PREPARE_DIR=''
PREPARE_FINAL_DIR=''
PREPARE_STAGE='initialization'
PREPARE_FAILURE_REASON=''

stage_patched_boot() {
  local kernel=$1 prepared=$2 module_payload=$3 mesa_stage=$4 stock_module=$5 stock_bls=$6 info_file=$7
  local evidence stock_initramfs machine patched_bls patched_id patched_initramfs verify_root embedded
  local stock_hash initramfs_hash payload_hash saved_before next_before staging_entry private
  local stock_modules_root stock_module_real stock_rel kmod_stage staged_module
  evidence="$prepared/boot-evidence"
  stock_initramfs="${BC250_GFX1013_BOOT_ROOT:-/boot}/initramfs-${kernel}.img"
  [[ -f "$stock_initramfs" ]] || die "stock initramfs missing: $stock_initramfs"
  machine="$(< "${BC250_GFX1013_MACHINE_ID_FILE:-/etc/machine-id}")"
  patched_id="${machine}-${kernel}-${PROFILE_VARIANT}"
  patched_bls="${BC250_GFX1013_BOOT_ROOT:-/boot}/loader/entries/${patched_id}.conf"
  patched_initramfs="${BC250_GFX1013_BOOT_ROOT:-/boot}/initramfs-${kernel}-${PROFILE_VARIANT}.img"
  [[ ! -e "$patched_bls" && ! -e "$patched_initramfs" ]] || die "stale GFX1013 boot artifacts exist; run disable/repair before prepare"
  private="$(private_prefix)"
  [[ ! -e "$private" ]] || die "private GFX1013 prefix already exists: $private"

  install -d -m 0700 "$evidence"
  grub2-editenv list > "$evidence/grubenv-before.txt"
  saved_before="$(grub_value saved_entry)"; next_before="$(grub_value next_entry)"
  printf '%s\n' "$saved_before" > "$evidence/saved-entry-before.txt"
  printf '%s\n' "$next_before" > "$evidence/next-entry-before.txt"
  stock_hash="$(sha256sum "$stock_module" | awk '{print $1}')"
  initramfs_hash="$(sha256sum "$stock_initramfs" | awk '{print $1}')"
  payload_hash="$(sha256sum "$module_payload" | awk '{print $1}')"
  printf '%s  %s\n' "$stock_hash" "$stock_module" > "$evidence/stock-module.sha256"
  printf '%s  %s\n' "$initramfs_hash" "$stock_initramfs" > "$evidence/stock-initramfs.sha256"

  # Safety invariant: never replace the authoritative stock amdgpu.  Build the
  # experimental initramfs from an isolated private module tree; unlink and
  # replace only the staged amdgpu path before asking dracut to use --kmoddir.
  stock_modules_root="$(readlink -f "${BC250_GFX1013_MODULES_ROOT:-/usr/lib/modules}/$kernel")"
  stock_module_real="$(readlink -f "$stock_module")"
  [[ -d "$stock_modules_root" ]] || die "stock module tree is missing: $stock_modules_root"
  case "$stock_module_real" in
    "$stock_modules_root"/*) stock_rel="${stock_module_real#"$stock_modules_root"/}" ;;
    *) die "stock amdgpu is outside the exact stock module tree" ;;
  esac
  kmod_stage="$PREPARE_DIR/kmod/$kernel"
  install -d -m 0700 "$kmod_stage"
  cp -a --reflink=auto "$stock_modules_root/." "$kmod_stage/" || die "failed to construct isolated kernel-module staging tree"
  staged_module="$kmod_stage/$stock_rel"
  [[ -f "$staged_module" ]] || die "isolated module tree does not contain stock amdgpu path"
  rm -f -- "$staged_module"
  install -m 0644 "$module_payload" "$staged_module"
  [[ "$(sha256sum "$stock_module" | awk '{print $1}')" == "$stock_hash" ]] || die "stock amdgpu changed before isolated dracut generation"
  dracut --kmoddir "$kmod_stage" --force-drivers amdgpu -f "$patched_initramfs" "$kernel" || \
    die "patched initramfs generation from isolated module tree failed"
  [[ "$(sha256sum "$stock_module" | awk '{print $1}')" == "$stock_hash" ]] || die "stock amdgpu changed during isolated dracut generation"
  [[ "$(sha256sum "$stock_initramfs" | awk '{print $1}')" == "$initramfs_hash" ]] || die "stock initramfs changed unexpectedly"
  rm -rf -- "$PREPARE_DIR/kmod"

  verify_root="$(mktemp -d)"
  (cd "$verify_root" && lsinitrd --unpack "$patched_initramfs")
  local -a embedded_modules=()
  mapfile -t embedded_modules < <(find "$verify_root" -type f -name 'amdgpu.ko*' -path "*/${kernel}/*" -print | sort)
  ((${#embedded_modules[@]} == 1)) || {
    rm -rf "$verify_root"
    die "patched initramfs must contain exactly one amdgpu module (found ${#embedded_modules[@]})"
  }
  embedded="${embedded_modules[0]}"
  [[ "$(sha256sum "$embedded" | awk '{print $1}')" == "$payload_hash" ]] || { rm -rf "$verify_root"; die "patched initramfs contains the wrong amdgpu module"; }
  rm -rf "$verify_root"

  staging_entry="$(mktemp)"
  awk -v kernel="$kernel" -v variant="$PROFILE_VARIANT" -v image="$(basename "$patched_initramfs")" '
    /^title / { print "title Fedora Linux (" kernel ", BC-250 GFX1013 V33)"; next }
    /^version / { print "version " kernel "-" variant; next }
    /^initrd / { print "initrd /" image " $tuned_initrd"; next }
    /^options / {
      line=$0
      if (line !~ /amdgpu\.sched_policy=/) line=line " amdgpu.sched_policy=2"
      line=line " bc250.gfx1013_v33=1"
      print line
      next
    }
    { print }
  ' "$stock_bls" > "$staging_entry"
  grep -qw "$PATCH_MARKER" "$staging_entry" || { rm -f "$staging_entry"; die "patched BLS marker generation failed"; }
  if ! install -m 0644 "$staging_entry" "$patched_bls"; then
    rm -f "$staging_entry"
    die "failed to install patched BLS entry"
  fi
  rm -f "$staging_entry"
  command -v restorecon >/dev/null 2>&1 && restorecon "$patched_bls" "$patched_initramfs" >/dev/null 2>&1 || true

  install -d -m 0755 "$(dirname "$private")"
  cp -a "$mesa_stage$private" "$private"
  pin_private_icd_library "$(private_icd)" "$(private_radv_lib)"
  private_icd_library_ok "$(private_icd)" "$(private_radv_lib)" || die "failed to pin private RADV ICD to the package private library"

  printf '%s\n' "$patched_bls" "$patched_id" "$patched_initramfs" "$stock_initramfs" "$saved_before" "$next_before" "$stock_hash" "$initramfs_hash" > "$info_file"
}

restore_previous_next() {
  local value=$1
  if [[ -n "$value" ]]; then
    grub2-editenv - set "next_entry=$value" || return 1
  else
    grub2-editenv - unset next_entry >/dev/null 2>&1 || true
  fi
  [[ "$(grub_value next_entry)" == "$value" ]]
}

select_patched_next_boot() {
  local patched_id=$1 saved_before=$2
  # Rollback becomes authoritative before the first boot-manager mutation.
  PREPARE_BOOT_STATE_CHANGED=1
  grub2-editenv - set "next_entry=$patched_id" || die "failed to select patched entry for one-shot boot"
  [[ "$(grub_value next_entry)" == "$patched_id" ]] || die "failed to verify patched one-shot boot selection"
  [[ "$(grub_value saved_entry)" == "$saved_before" ]] || die "prepare unexpectedly changed the saved/default boot entry"
}

rotate_prepare_failures() {
  local root="$STATE_ROOT/failures" path
  local -a entries=()
  [[ -d "$root" ]] || return 0
  mapfile -t entries < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'failure-*' -print | sort -r)
  if ((${#entries[@]} > 5)); then
    for path in "${entries[@]:5}"; do rm -rf -- "$path"; done
  fi
}

preserve_prepare_failure() {
  local rc=$1 timestamp dest log package_id
  [[ -n "$PREPARE_DIR" && -d "$PREPARE_DIR" ]] || return 0
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dest="$STATE_ROOT/failures/failure-${timestamp}-$$"
  install -d -m 0700 "$dest"
  package_id="$(package_nevra)"
  {
    printf 'stage=%s\n' "$PREPARE_STAGE"
    printf 'exit_rc=%s\n' "$rc"
    printf 'reason=%q\n' "${PREPARE_FAILURE_REASON:-unknown}"
    printf 'package_nevra=%s\n' "${package_id:-unavailable}"
    printf 'kernel=%s\n' "$(kernel_release)"
    printf 'profile=%s\n' "$PACKAGE_PROFILE"
    printf 'upstream_version=%s\n' "$UPSTREAM_VERSION"
    printf 'upstream_commit=%s\n' "$PINNED_COMMIT"
    printf 'mesa_fedora_srpm=%s\n' "$MESA_SRPM_NEVRA"
    printf 'mesa_source0_sha256=%s\n' "$MESA_SOURCE0_SHA256"
  } > "$dest/failure.env"
  chmod 0600 "$dest/failure.env"
  for log in kernel-srpm-members.txt kernel-prep.log kernel-source-provenance.txt kernel-build.log mesa-prep.log mesa-setup.log mesa-build.log; do
    if [[ -f "$PREPARE_DIR/work/$log" && ! -L "$PREPARE_DIR/work/$log" ]]; then
      install -m 0600 "$PREPARE_DIR/work/$log" "$dest/$log"
    fi
  done
  rotate_prepare_failures
  printf 'GFX1013 prepare failure evidence: %s\n' "$dest" >&2
}

set_active_transaction_state() {
  local phase=$1 recovery=${2:-0} reason=${3:-} tmp
  [[ -f "$ACTIVE_STATE" ]] || return 1
  tmp="$ACTIVE_STATE.tmp"
  awk '!/^BC250_GFX1013_TRANSACTION_PHASE=/ && !/^BC250_GFX1013_RECOVERY_REQUIRED=/ && !/^BC250_GFX1013_RECOVERY_REASON=/' "$ACTIVE_STATE" > "$tmp"
  {
    printf 'BC250_GFX1013_TRANSACTION_PHASE=%s\n' "$phase"
    printf 'BC250_GFX1013_RECOVERY_REQUIRED=%s\n' "$recovery"
    [[ -z "$reason" ]] || printf 'BC250_GFX1013_RECOVERY_REASON=%q\n' "$reason"
  } >> "$tmp"
  chmod 0600 "$tmp"
  mv -f "$tmp" "$ACTIVE_STATE"
}

mark_prepare_safety_failure() {
  set_active_transaction_state SAFETY_FAILURE 1 "$1"
}

prepare_cleanup_on_exit() {
  local rc=$1
  trap - EXIT INT TERM
  if [[ "$PREPARE_COMMITTED" != 1 ]]; then
    preserve_prepare_failure "$rc" || true

    # Boot-manager rollback is safety authority.  Never delete the patched BLS,
    # initramfs, lifecycle state or recovery evidence until prior next_entry has
    # been restored and verified.
    if [[ "$PREPARE_BOOT_STATE_CHANGED" == 1 ]]; then
      if ! restore_previous_next "$PREPARE_PREVIOUS_NEXT"; then
        mark_prepare_safety_failure 'failed to restore previous GRUB next_entry during prepare rollback' || true
        echo "ERROR: GFX1013 prepare rollback could not restore boot-manager state; recovery artifacts were preserved" >&2
        exit 5
      fi
      PREPARE_BOOT_STATE_CHANGED=0
    fi

    [[ -z "$PREPARE_PATCHED_BLS" ]] || rm -f -- "$PREPARE_PATCHED_BLS"
    [[ -z "$PREPARE_PATCHED_INITRAMFS" ]] || rm -f -- "$PREPARE_PATCHED_INITRAMFS"
    [[ -z "$PREPARE_PRIVATE_PREFIX" ]] || rm -rf -- "$PREPARE_PRIVATE_PREFIX"
    rm -f -- "$ACTIVE_STATE"
    [[ -z "$PREPARE_FINAL_DIR" ]] || rm -rf -- "$PREPARE_FINAL_DIR"
    [[ -z "$PREPARE_DIR" ]] || rm -rf -- "$PREPARE_DIR"
    rmdir "$STATE_ROOT/prepared" 2>/dev/null || true
  fi
  exit "$rc"
}

prepare_preflight() {
  local failures=0 kernel build build_owner stock_module stock_bls stock_entry_id current_saved
  local secure package_id requirement provider command os_id='' machine_id preflight_bls preflight_initramfs
  local -a missing_commands=()

  echo "GFX1013 prepare preflight (read-only):"
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_id="${ID:-}"
  fi
  if [[ "$os_id" == fedora ]]; then
    echo "  Fedora host: PASS"
  else
    echo "  Fedora host: BLOCKED (${os_id:-unknown})"
    failures=$((failures + 1))
  fi
  if command -v rpm-ostree >/dev/null 2>&1; then
    echo "  Atomic/rpm-ostree host: BLOCKED (unsupported by direct exact-kernel profile)"
    failures=$((failures + 1))
  else
    echo "  Atomic/rpm-ostree host: PASS (not detected)"
  fi

  for command in curl xz zstd gzip bzip2 tar cpio patch gcc g++ make cargo rpm rpm2cpio rpmbuild meson ninja python3 nm \
    sha256sum modinfo modprobe depmod dracut lsinitrd grub2-editenv grub2-set-default awk sed grep find install; do
    command -v "$command" >/dev/null 2>&1 || missing_commands+=("$command")
  done
  if ((${#missing_commands[@]})); then
    printf '  Required commands: BLOCKED (missing: %s)\n' "${missing_commands[*]}"
    failures=$((failures + 1))
  else
    echo "  Required commands: PASS"
  fi
  if command -v dracut >/dev/null 2>&1 && dracut --help 2>&1 | grep -q -- '--kmoddir'; then
    echo "  Isolated dracut module tree: PASS (--kmoddir supported)"
  else
    echo "  Isolated dracut module tree: BLOCKED (--kmoddir unavailable)"
    failures=$((failures + 1))
  fi

  echo "  Optional build requirements/providers:"
  for requirement in "${GFX_BUILD_PACKAGES[@]}"; do
    provider="$(build_requirement_provider "$requirement")"
    if [[ -n "$provider" ]]; then
      printf '    requirement: %-26s provider: %-44s status: satisfied\n' "$requirement" "$provider"
    else
      printf '    requirement: %-26s provider: %-44s status: MISSING\n' "$requirement" '<none>'
      failures=$((failures + 1))
    fi
  done

  secure="$(secure_boot_state)"
  case "$secure" in
    disabled|disabled-non-efi|disabled-unsupported) echo "  Secure Boot: PASS ($secure)" ;;
    enabled) echo "  Secure Boot: BLOCKED (unsigned package-built amdgpu is not enrolled)"; failures=$((failures + 1)) ;;
    *) echo "  Secure Boot: BLOCKED (state unknown)"; failures=$((failures + 1)) ;;
  esac

  if source_identity_ok; then
    echo "  Package source/patch manifests: PASS"
  else
    echo "  Package source/patch manifests: BLOCKED"
    failures=$((failures + 1))
  fi
  if bc250_device_present; then
    echo "  BC-250 PCI 1002:13fe: PASS"
  else
    echo "  BC-250 PCI 1002:13fe: BLOCKED (not found)"
    failures=$((failures + 1))
  fi

  [[ ! -e "$ACTIVE_STATE" ]] || { echo "  Existing lifecycle state: BLOCKED (disable/reset first)"; failures=$((failures + 1)); }
  [[ ! -e "$DROPIN" ]] || { echo "  Ollama private-RADV override: BLOCKED (unexpected pre-existing drop-in)"; failures=$((failures + 1)); }
  [[ ! -e "$UPSTREAM_GENERATOR" && ! -e "$UPSTREAM_STATE/active.env" ]] || {
    echo "  Separate upstream GFX1013 state: BLOCKED (conflict detected)"; failures=$((failures + 1));
  }

  kernel="$(kernel_release)"
  build="/lib/modules/$kernel/build"
  if [[ -e "$build" ]]; then
    build="$(readlink -f "$build")"
    build_owner="$(kernel_build_owner "$kernel" "$build" 2>/dev/null || true)"
    if [[ "$build_owner" == "kernel-devel-${kernel}" ]]; then
      echo "  Exact kernel-devel: PASS ($build_owner)"
    else
      echo "  Exact kernel-devel: BLOCKED (build tree owner ${build_owner:-unknown})"
      failures=$((failures + 1))
    fi
  else
    echo "  Exact kernel-devel: BLOCKED (missing $build)"
    failures=$((failures + 1))
  fi

  stock_module="$(find_stock_module "$kernel" 2>/dev/null || true)"
  [[ -n "$stock_module" ]] && echo "  Stock amdgpu module: PASS ($stock_module)" || {
    echo "  Stock amdgpu module: BLOCKED (not found)"; failures=$((failures + 1));
  }
  stock_bls="$(find_stock_bls "$kernel" 2>/dev/null || true)"
  if [[ -n "$stock_bls" ]]; then
    stock_entry_id="$(basename "$stock_bls" .conf)"
    current_saved="$(grub_value saved_entry)"
    if [[ "$current_saved" == "$stock_entry_id" ]] && stock_entry_file_safe "$stock_bls"; then
      echo "  Stock BLS/default boot: PASS ($stock_entry_id)"
    else
      echo "  Stock BLS/default boot: BLOCKED (saved=${current_saved:-unset}, expected=$stock_entry_id)"
      failures=$((failures + 1))
    fi
  else
    echo "  Stock BLS/default boot: BLOCKED (could not identify exactly one stock entry)"
    failures=$((failures + 1))
  fi

  machine_id="$(cat /etc/machine-id 2>/dev/null || true)"
  if [[ -n "$machine_id" ]]; then
    preflight_bls="/boot/loader/entries/${machine_id}-${kernel}-${PROFILE_VARIANT}.conf"
    preflight_initramfs="/boot/initramfs-${kernel}-${PROFILE_VARIANT}.img"
    if [[ -e "$preflight_bls" || -e "$preflight_initramfs" || -e "$(private_prefix)" ]]; then
      echo "  Stale staged artifacts: BLOCKED (reset required)"
      failures=$((failures + 1))
    else
      echo "  Stale staged artifacts: PASS"
    fi
  else
    echo "  Machine identity: BLOCKED (/etc/machine-id unavailable)"
    failures=$((failures + 1))
  fi

  package_id="$(package_nevra)"
  [[ -n "$package_id" ]] && echo "  Package identity: PASS ($package_id)" || {
    echo "  Package identity: BLOCKED (unavailable)"; failures=$((failures + 1));
  }

  echo "  Patch applicability/buildability: NOT BUILT (validated by prepare and the Fedora source gate)"
  if ((failures)); then
    printf 'GFX1013 prepare check: BLOCKED (%d issue(s))\n' "$failures"
    echo "No files, boot state or services were changed."
    return 2
  fi
  echo "GFX1013 prepare check: PASS"
  echo "No files, boot state or services were changed."
  return 0
}

prepare() {
  local check_only=0
  [[ ${1:-} == --check ]] && check_only=1
  need_root
  if ((check_only)); then
    prepare_preflight
    return $?
  fi
  check_os_and_boot_tools
  source_identity_ok || die "package-pinned GFX1013 patch/full-source identity failed: $SOURCE"
  bc250_device_present || die "AMD BC-250 PCI device 1002:13fe not found"
  [[ ! -e "$ACTIVE_STATE" ]] || die "a GFX1013 preparation is already active; run 'bc250 gfx1013 disable' first"
  [[ ! -e "$DROPIN" ]] || die "Ollama GFX1013 override already exists without active state; repair/disable before prepare"
  [[ ! -e "$UPSTREAM_GENERATOR" && ! -e "$UPSTREAM_STATE/active.env" ]] || \
    die "a separate upstream GFX1013 installation is active; uninstall/disable it before using the package lifecycle"

  local kernel build build_owner prepared transaction work artifact_work artifact stage stock_module stock_bls
  local vermagic srcversion module_sha abi_sha abi_mode package_id kernel_srpm kernel_srpm_nevr patch_sha source_sha kernel_srpm_sha
  local kernel_provenance_file kernel_provenance_sha kernel_provenance_mode kernel_target_manifest_sha
  local mesa_info_file mesa_srpm mesa_source0 mesa_srpm_sha mesa_source_sha private_radv_sha private_icd_sha
  local -a stage_info mesa_info
  local patched_bls patched_id patched_initramfs stock_initramfs saved_before next_before stock_hash initramfs_hash
  kernel="$(kernel_release)"; build="/lib/modules/$kernel/build"
  [[ -e "$build" ]] || die "exact kernel build tree missing: $build"
  build="$(readlink -f "$build")"
  build_owner="$(kernel_build_owner "$kernel" "$build")" || die "exact build tree is not owned by kernel-devel-${kernel}: $build"
  if [[ "$kernel" != "$TESTED_KERNEL" ]]; then
    printf 'WARNING: running %s; package reference qualification was %s. Building exact-kernel artifacts only.\n' "$kernel" "$TESTED_KERNEL" >&2
  fi

  prepared="$(prepared_dir_for "$kernel")"
  transaction="$STATE_ROOT/.prepare-${kernel}-$$"
  work="$transaction/work"
  stage="$transaction/mesa-stage"
  stock_module="$(find_stock_module "$kernel")" || die "stock distro amdgpu module not found; refusing to overwrite a non-stock module path"
  stock_bls="$(find_stock_bls "$kernel")" || die "could not identify exactly one stock BLS entry for $kernel"
  local stock_entry_id current_saved
  stock_entry_id="$(basename "$stock_bls" .conf)"
  current_saved="$(grub_value saved_entry)"
  [[ "$current_saved" == "$stock_entry_id" ]] || \
    die "saved/default boot is not the exact stock entry $stock_entry_id (found ${current_saved:-<unset>}); restore/select stock before prepare"
  stock_entry_file_safe "$stock_bls" || die "identified stock BLS entry is missing or already carries the patched marker"

  local machine_id preflight_patched_bls preflight_patched_initramfs
  machine_id="$(< /etc/machine-id)"
  preflight_patched_bls="/boot/loader/entries/${machine_id}-${kernel}-${PROFILE_VARIANT}.conf"
  preflight_patched_initramfs="/boot/initramfs-${kernel}-${PROFILE_VARIANT}.img"
  [[ ! -e "$preflight_patched_bls" && ! -e "$preflight_patched_initramfs" ]] || \
    die "stale GFX1013 boot artifacts already exist; use 'bc250 gfx1013 reset' before prepare"
  [[ ! -e "$(private_prefix)" ]] || die "private GFX1013 prefix already exists; use 'bc250 gfx1013 reset' before prepare"
  [[ ! -e "$prepared" ]] || die "stale exact-kernel preparation exists; use 'bc250 gfx1013 reset' before prepare"
  package_id="$(package_nevra)"
  [[ -n "$package_id" ]] || die "installed bc250-llm-server RPM identity is unavailable"

  artifact_work="$transaction/amdgpu${stock_module##*amdgpu}"
  artifact="$prepared/amdgpu${stock_module##*amdgpu}"
  PREPARE_DIR="$transaction"
  PREPARE_FINAL_DIR="$prepared"
  PREPARE_PATCHED_BLS="$preflight_patched_bls"
  PREPARE_PATCHED_INITRAMFS="$preflight_patched_initramfs"
  PREPARE_PRIVATE_PREFIX="$(private_prefix)"
  PREPARE_PREVIOUS_NEXT="$(grub_value next_entry)"
  PREPARE_BOOT_STATE_CHANGED=0
  PREPARE_COMMITTED=0
  PREPARE_STAGE='transaction-initialization'
  PREPARE_FAILURE_REASON=''
  trap 'prepare_cleanup_on_exit $?' EXIT
  trap 'exit 130' INT TERM
  rm -rf "$transaction"
  install -d -m 0700 "$work"

  say "Building $PACKAGE_PROFILE for exact kernel $kernel"
  say "Pinned upstream: $UPSTREAM_VERSION @ $PINNED_COMMIT"
  say "Mesa baseline: Fedora $MESA_SRPM_NEVRA; private compute-queue patch only"

  PREPARE_STAGE='kernel-source-and-module-build'
  kernel_srpm="$(build_kernel_module "$kernel" "$build" "$work" "$artifact_work" "$stock_module")"
  kernel_srpm_nevr="$(rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}\n' "$kernel_srpm" 2>/dev/null || true)"
  [[ -n "$kernel_srpm_nevr" ]] || die "kernel source RPM NEVR is unavailable after build"
  kernel_provenance_file="$work/kernel-source-provenance.txt"
  [[ -r "$kernel_provenance_file" ]] || die "kernel source-provenance evidence is missing"
  kernel_provenance_sha="$(sha256sum "$kernel_provenance_file" | awk '{print $1}')"
  kernel_provenance_mode="$(sed -n 's/^mode=//p' "$kernel_provenance_file" | head -1)"
  kernel_target_manifest_sha="$(sed -n 's/^target_manifest_sha256=//p' "$kernel_provenance_file" | head -1)"
  [[ "$kernel_provenance_mode" == fedora-prepared-source ]] || die "kernel source-provenance mode is invalid"
  [[ "$kernel_target_manifest_sha" =~ ^[0-9a-f]{64}$ ]] || die "kernel source target-manifest evidence is invalid"

  PREPARE_STAGE='mesa-fedora-prep-and-build'
  mesa_info_file="$work/mesa-info"
  build_mesa "$work" "$stage" "$mesa_info_file"
  mapfile -t mesa_info < "$mesa_info_file"
  ((${#mesa_info[@]} == 2)) || die "internal Mesa provenance evidence error"
  mesa_srpm="${mesa_info[0]}"; mesa_source0="${mesa_info[1]}"

  PREPARE_STAGE='module-vermagic-and-abi-validation'
  vermagic="$(modinfo -F vermagic "$artifact_work" 2>/dev/null || true)"
  [[ "$vermagic" == "$kernel "* ]] || die "built amdgpu vermagic does not match exact running kernel ($vermagic)"
  srcversion="$(modinfo -F srcversion "$artifact_work" 2>/dev/null || true)"
  abi_sha="$(verify_module_abi "$build" "$artifact_work" "$work" "$kernel")"
  abi_mode="$(sed -n 's/^mode=//p' "$work/abi-required.txt" | head -1)"
  [[ "$abi_mode" =~ ^(modversions|symbol-resolution)$ ]] || die "module compatibility verification mode is invalid"
  module_sha="$(sha256sum "$artifact_work" | awk '{print $1}')"
  patch_sha="$(patch_manifest_sha)"; source_sha="$(source_manifest_sha)"
  kernel_srpm_sha="$(sha256sum "$kernel_srpm" | awk '{print $1}')"
  mesa_srpm_sha="$(sha256sum "$mesa_srpm" | awk '{print $1}')"
  mesa_source_sha="$(sha256sum "$mesa_source0" | awk '{print $1}')"
  [[ "$mesa_source_sha" == "$MESA_SOURCE0_SHA256" ]] || die "Fedora Mesa Source0 SHA changed after build"

  # Commit boundary: all source, module ABI and private Mesa build validation has
  # completed. Only now create package lifecycle artifacts under prepared/, /opt and /boot.
  PREPARE_STAGE='lifecycle-artifact-staging'
  install -d -m 0700 "$prepared" "$prepared/build-evidence"
  install -m 0644 "$artifact_work" "$artifact"
  local log
  for log in kernel-srpm-members.txt kernel-prep.log kernel-source-provenance.txt kernel-build.log mesa-prep.log mesa-setup.log mesa-build.log; do
    [[ -f "$work/$log" ]] && install -m 0600 "$work/$log" "$prepared/build-evidence/$log"
  done

  local stage_info_file="$prepared/stage-info"
  stage_patched_boot "$kernel" "$prepared" "$artifact" "$stage" "$stock_module" "$stock_bls" "$stage_info_file"
  mapfile -t stage_info < "$stage_info_file"
  ((${#stage_info[@]} == 8)) || die "internal staging evidence error"
  [[ -f "$(private_radv_lib)" && -f "$(private_icd)" ]] || die "staged private RADV identity files are missing"
  private_radv_sha="$(sha256sum "$(private_radv_lib)" | awk '{print $1}')"
  private_icd_sha="$(sha256sum "$(private_icd)" | awk '{print $1}')"
  patched_bls=${stage_info[0]}; patched_id=${stage_info[1]}; patched_initramfs=${stage_info[2]}; stock_initramfs=${stage_info[3]}
  saved_before=${stage_info[4]}; next_before=${stage_info[5]}; stock_hash=${stage_info[6]}; initramfs_hash=${stage_info[7]}

  PREPARE_STAGE='lifecycle-state-commit'
  cat > "$ACTIVE_STATE" <<EOF_STATE
BC250_GFX1013_PROFILE=$PACKAGE_PROFILE
BC250_GFX1013_UPSTREAM_VERSION=$UPSTREAM_VERSION
BC250_GFX1013_COMMIT=$PINNED_COMMIT
BC250_GFX1013_PACKAGE_NEVRA=$package_id
BC250_GFX1013_KERNEL=$kernel
BC250_GFX1013_BUILD_TREE=$build
BC250_GFX1013_KERNEL_DEVEL_NEVRA=$build_owner
BC250_GFX1013_KERNEL_SRPM_NEVR=$kernel_srpm_nevr
BC250_GFX1013_KERNEL_SRPM_SHA256=$kernel_srpm_sha
BC250_GFX1013_KERNEL_SOURCE_PROVENANCE_MODE=$kernel_provenance_mode
BC250_GFX1013_KERNEL_SOURCE_PROVENANCE_SHA256=$kernel_provenance_sha
BC250_GFX1013_KERNEL_TARGET_MANIFEST_SHA256=$kernel_target_manifest_sha
BC250_GFX1013_MODULE=$artifact
BC250_GFX1013_MODULE_SHA256=$module_sha
BC250_GFX1013_MODULE_SRCVERSION=$srcversion
BC250_GFX1013_VERMAGIC=$(printf '%q' "$vermagic")
BC250_GFX1013_ABI_MODE=$abi_mode
BC250_GFX1013_ABI_SHA256=$abi_sha
BC250_GFX1013_PATCH_MANIFEST_SHA256=$patch_sha
BC250_GFX1013_SOURCE_MANIFEST_SHA256=$source_sha
BC250_GFX1013_MESA_SRPM_NEVRA=$MESA_SRPM_NEVRA
BC250_GFX1013_MESA_SRPM_SHA256=$mesa_srpm_sha
BC250_GFX1013_MESA_SOURCE_SHA256=$mesa_source_sha
BC250_GFX1013_STOCK_MODULE=$stock_module
BC250_GFX1013_STOCK_MODULE_SHA256=$stock_hash
BC250_GFX1013_STOCK_INITRAMFS=$stock_initramfs
BC250_GFX1013_STOCK_INITRAMFS_SHA256=$initramfs_hash
BC250_GFX1013_STOCK_BLS=$stock_bls
BC250_GFX1013_STOCK_ENTRY_ID=${stock_bls##*/}
BC250_GFX1013_PATCHED_BLS=$patched_bls
BC250_GFX1013_PATCHED_ENTRY_ID=$patched_id
BC250_GFX1013_PATCHED_INITRAMFS=$patched_initramfs
BC250_GFX1013_PRIVATE_PREFIX=$(private_prefix)
BC250_GFX1013_PRIVATE_RADV_LIB=$(private_radv_lib)
BC250_GFX1013_PRIVATE_RADV_SHA256=$private_radv_sha
BC250_GFX1013_ICD=$(private_icd)
BC250_GFX1013_ICD_SHA256=$private_icd_sha
BC250_GFX1013_PREVIOUS_SAVED_ENTRY=$saved_before
BC250_GFX1013_PREVIOUS_NEXT_ENTRY=$next_before
BC250_GFX1013_TRANSACTION_PHASE=BOOT_ENTRY_STAGING
BC250_GFX1013_RECOVERY_REQUIRED=0
BC250_GFX1013_ENABLED=0
EOF_STATE
  sed -i "s#^BC250_GFX1013_STOCK_ENTRY_ID=.*#BC250_GFX1013_STOCK_ENTRY_ID=$(basename "$stock_bls" .conf)#" "$ACTIVE_STATE"
  chmod 0600 "$ACTIVE_STATE"

  PREPARE_STAGE='one-shot-boot-selection'
  select_patched_next_boot "$patched_id" "$saved_before"

  sed -i 's/^BC250_GFX1013_TRANSACTION_PHASE=.*/BC250_GFX1013_TRANSACTION_PHASE=PREPARED/' "$ACTIVE_STATE"
  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$kernel")"
  PREPARE_COMMITTED=1
  rm -rf "$transaction"
  PREPARE_DIR=''
  trap - EXIT INT TERM
  echo "Exact-kernel build, module compatibility verification, Fedora source provenance/patch validation, private RADV staging and patched initramfs: PASS"
  echo "Stock saved/default boot remains unchanged; patched boot is selected for the next boot only."
  echo "Next: reboot once, run 'bc250 gfx1013 status', then: sudo bc250 gfx1013 enable"
}

verify_active_identity() {
  local current_build_owner current_package
  source_identity_ok || die "installed package patch/full-source identity no longer matches the prepared profile"
  [[ "$(patch_manifest_sha)" == "$BC250_GFX1013_PATCH_MANIFEST_SHA256" ]] || die "patch manifest changed since prepare"
  [[ "$(source_manifest_sha)" == "$BC250_GFX1013_SOURCE_MANIFEST_SHA256" ]] || die "full-source manifest changed since prepare"
  current_package="$(package_nevra)"
  [[ -n "${BC250_GFX1013_PACKAGE_NEVRA:-}" && "$current_package" == "$BC250_GFX1013_PACKAGE_NEVRA" ]] || die "package identity changed since prepare; disable/reset and prepare again"
  current_build_owner="$(kernel_build_owner "$BC250_GFX1013_KERNEL" "$BC250_GFX1013_BUILD_TREE")" || die "exact kernel-devel build-tree identity is no longer valid"
  [[ "$current_build_owner" == "$BC250_GFX1013_KERNEL_DEVEL_NEVRA" ]] || die "kernel-devel package identity changed since prepare"
  [[ -f "$BC250_GFX1013_MODULE" ]] || die "prepared exact-kernel module artifact is missing"
  [[ "$(sha256sum "$BC250_GFX1013_MODULE" | awk '{print $1}')" == "$BC250_GFX1013_MODULE_SHA256" ]] || die "prepared module SHA-256 mismatch"
  local abi_tmp current_abi current_abi_mode
  abi_tmp="$(mktemp -d)"
  if ! current_abi="$(verify_module_abi "$BC250_GFX1013_BUILD_TREE" "$BC250_GFX1013_MODULE" "$abi_tmp" "$BC250_GFX1013_KERNEL")"; then
    rm -rf "$abi_tmp"
    die "prepared module ABI revalidation failed"
  fi
  current_abi_mode="$(sed -n 's/^mode=//p' "$abi_tmp/abi-required.txt" | head -1)"
  rm -rf "$abi_tmp"
  [[ "$current_abi_mode" == "$BC250_GFX1013_ABI_MODE" ]] || die "prepared module compatibility mode changed"
  [[ "$current_abi" == "$BC250_GFX1013_ABI_SHA256" ]] || die "prepared module compatibility evidence changed"
  [[ "${BC250_GFX1013_MESA_SRPM_NEVRA:-}" == "$MESA_SRPM_NEVRA" ]] || die "prepared Mesa Fedora source identity differs from package baseline"
  [[ "${BC250_GFX1013_MESA_SOURCE_SHA256:-}" == "$MESA_SOURCE0_SHA256" ]] || die "prepared Mesa Source0 identity differs from package baseline"
  [[ -f "$BC250_GFX1013_STOCK_MODULE" ]] || die "recorded stock amdgpu module is missing"
  [[ "$(sha256sum "$BC250_GFX1013_STOCK_MODULE" | awk '{print $1}')" == "$BC250_GFX1013_STOCK_MODULE_SHA256" ]] || die "stock amdgpu changed since prepare"
  [[ -f "$BC250_GFX1013_STOCK_INITRAMFS" ]] || die "recorded stock initramfs is missing"
  [[ "$(sha256sum "$BC250_GFX1013_STOCK_INITRAMFS" | awk '{print $1}')" == "$BC250_GFX1013_STOCK_INITRAMFS_SHA256" ]] || die "stock initramfs changed since prepare"
  [[ -f "$BC250_GFX1013_PATCHED_BLS" && -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]] || die "prepared patched boot artifacts are missing"
  [[ -f "$BC250_GFX1013_PRIVATE_RADV_LIB" ]] || die "private RADV library is missing"
  [[ "$(sha256sum "$BC250_GFX1013_PRIVATE_RADV_LIB" | awk '{print $1}')" == "$BC250_GFX1013_PRIVATE_RADV_SHA256" ]] || die "private RADV library identity changed"
  [[ -f "$BC250_GFX1013_ICD" ]] || die "private RADV ICD is missing"
  [[ "$(sha256sum "$BC250_GFX1013_ICD" | awk '{print $1}')" == "$BC250_GFX1013_ICD_SHA256" ]] || die "private RADV ICD identity changed"
}

ollama_guard() {
  local current_package loaded_srcversion
  load_active_state || { echo "GFX1013 Ollama guard: lifecycle state is missing/invalid" >&2; return 1; }
  current_package="$(package_nevra)"
  [[ -n "$current_package" && "$current_package" == "${BC250_GFX1013_PACKAGE_NEVRA:-}" ]] || {
    echo "GFX1013 Ollama guard: package identity changed since prepare" >&2
    return 1
  }
  [[ "$(kernel_release)" == "$BC250_GFX1013_KERNEL" ]] || {
    echo "GFX1013 Ollama guard: running kernel differs from prepared kernel" >&2
    return 1
  }
  patched_boot_running || {
    echo "GFX1013 Ollama guard: current boot lacks the patched marker" >&2
    return 1
  }
  [[ -f "$BC250_GFX1013_PRIVATE_RADV_LIB" && -f "$BC250_GFX1013_ICD" ]] || {
    echo "GFX1013 Ollama guard: private RADV payload is incomplete" >&2
    return 1
  }
  [[ "$(sha256sum "$BC250_GFX1013_PRIVATE_RADV_LIB" | awk '{print $1}')" == "$BC250_GFX1013_PRIVATE_RADV_SHA256" ]] || {
    echo "GFX1013 Ollama guard: private RADV library identity changed" >&2
    return 1
  }
  [[ "$(sha256sum "$BC250_GFX1013_ICD" | awk '{print $1}')" == "$BC250_GFX1013_ICD_SHA256" ]] || {
    echo "GFX1013 Ollama guard: private RADV ICD identity changed" >&2
    return 1
  }
  private_icd_library_ok "$BC250_GFX1013_ICD" "$BC250_GFX1013_PRIVATE_RADV_LIB" || {
    echo "GFX1013 Ollama guard: private ICD no longer points at private RADV" >&2
    return 1
  }
  if [[ -n "${BC250_GFX1013_MODULE_SRCVERSION:-}" && -r /sys/module/amdgpu/srcversion ]]; then
    loaded_srcversion="$(tr -d '\n' < /sys/module/amdgpu/srcversion)"
    [[ "$loaded_srcversion" == "$BC250_GFX1013_MODULE_SRCVERSION" ]] || {
      echo "GFX1013 Ollama guard: loaded amdgpu srcversion differs from prepared module" >&2
      return 1
    }
  fi
}

write_ollama_dropin() {
  install -d -m 0755 "$(dirname "$DROPIN")"
  cat > "$DROPIN.tmp" <<EOF_DROPIN
[Unit]
ConditionKernelCommandLine=$PATCH_MARKER

[Service]
ExecCondition=+$INSTALLED_SELF ollama-guard
Environment=VK_DRIVER_FILES=$BC250_GFX1013_ICD
EOF_DROPIN
  install -m 0644 "$DROPIN.tmp" "$DROPIN"
  rm -f "$DROPIN.tmp"
  systemctl daemon-reload
}

ENABLE_COMMITTED=1
ENABLE_WAS_ACTIVE=0
ENABLE_PREVIOUS_SAVED=''
enable_cleanup_on_exit() {
  local rc=$1 rollback_ok=1
  trap - EXIT INT TERM
  if [[ "$ENABLE_COMMITTED" != 1 ]]; then
    rm -f -- "$DROPIN" "$DROPIN.tmp"
    systemctl daemon-reload >/dev/null 2>&1 || rollback_ok=0
    if [[ -n "$ENABLE_PREVIOUS_SAVED" ]]; then
      grub2-set-default "$ENABLE_PREVIOUS_SAVED" >/dev/null 2>&1 || rollback_ok=0
      [[ "$(grub_value saved_entry)" == "$ENABLE_PREVIOUS_SAVED" ]] || rollback_ok=0
    fi
    ((ENABLE_WAS_ACTIVE)) && systemctl restart ollama.service >/dev/null 2>&1 || true
    if ((rollback_ok)); then
      set_active_transaction_state PREPARED 0 || true
    else
      set_active_transaction_state SAFETY_FAILURE 1 'failed to restore saved/default boot during enable rollback' || true
      echo "ERROR: GFX1013 enable rollback could not restore boot-manager state; recovery state was preserved" >&2
      rc=5
    fi
  fi
  exit "$rc"
}

enable() {
  need_root
  load_active_state || die "no valid active GFX1013 preparation"
  [[ "$(kernel_release)" == "$BC250_GFX1013_KERNEL" ]] || die "prepared state belongs to kernel $BC250_GFX1013_KERNEL, not $(kernel_release)"
  verify_active_identity
  bc250_device_present || die "AMD BC-250 PCI device 1002:13fe not found"
  patched_boot_running || die "current boot is not the staged GFX1013 boot; refusing Mesa-only activation"
  [[ "$(modinfo -F vermagic "$BC250_GFX1013_MODULE" 2>/dev/null || true)" == "$BC250_GFX1013_KERNEL "* ]] || die "prepared module vermagic changed/mismatched"
  local vk_identity vk_vendor vk_device vk_driver vk_summary_sha state_tmp
  vk_identity="$(verify_private_radv_device "$BC250_GFX1013_ICD" "$BC250_GFX1013_PRIVATE_RADV_LIB")"
  IFS='|' read -r vk_vendor vk_device vk_driver vk_summary_sha <<< "$vk_identity"
  [[ "$vk_vendor" == 0x1002 && "$vk_device" == 0x13fe && "$vk_driver" == radv && "$vk_summary_sha" =~ ^[0-9a-f]{64}$ ]] || \
    die "private RADV identity evidence is malformed"

  ENABLE_WAS_ACTIVE=0
  systemctl is-active --quiet ollama.service && ENABLE_WAS_ACTIVE=1 || true
  [[ ! -e "$UPSTREAM_GENERATOR" ]] || die "separate upstream environment generator appeared after prepare; refusing activation"
  ENABLE_PREVIOUS_SAVED="$(grub_value saved_entry)"
  [[ "$ENABLE_PREVIOUS_SAVED" == "$BC250_GFX1013_STOCK_ENTRY_ID" ]] || \
    die "stock saved/default boot changed after prepare; refusing promotion"
  set_active_transaction_state ENABLING 0 || die "cannot persist GFX1013 ENABLING transaction state"
  ENABLE_COMMITTED=0
  trap 'enable_cleanup_on_exit $?' EXIT
  trap 'exit 130' INT TERM
  write_ollama_dropin
  if ((ENABLE_WAS_ACTIVE)); then
    systemctl restart ollama.service || die "Ollama restart failed with private RADV; patched boot was not promoted"
    systemctl is-active --quiet ollama.service || die "Ollama is not active after private RADV activation; patched boot was not promoted"
  fi
  grub2-set-default "$BC250_GFX1013_PATCHED_ENTRY_ID" || die "failed to promote the verified patched boot"
  [[ "$(grub_value saved_entry)" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]] || die "patched saved/default boot verification failed"
  state_tmp="$ACTIVE_STATE.tmp"
  awk '!/^BC250_GFX1013_ENABLED=/ && !/^BC250_GFX1013_VULKAN_/ && !/^BC250_GFX1013_TRANSACTION_PHASE=/ && !/^BC250_GFX1013_RECOVERY_REQUIRED=/ && !/^BC250_GFX1013_RECOVERY_REASON=/' "$ACTIVE_STATE" > "$state_tmp"
  cat >> "$state_tmp" <<EOF_VK_STATE
BC250_GFX1013_TRANSACTION_PHASE=ENABLED
BC250_GFX1013_RECOVERY_REQUIRED=0
BC250_GFX1013_ENABLED=1
BC250_GFX1013_VULKAN_VENDOR_ID=$vk_vendor
BC250_GFX1013_VULKAN_DEVICE_ID=$vk_device
BC250_GFX1013_VULKAN_DRIVER_NAME=$vk_driver
BC250_GFX1013_VULKAN_SUMMARY_SHA256=$vk_summary_sha
EOF_VK_STATE
  chmod 0600 "$state_tmp"
  mv -f "$state_tmp" "$ACTIVE_STATE"
  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")"
  ENABLE_COMMITTED=1
  trap - EXIT INT TERM
  echo "GFX1013 enabled: verified patched boot is saved default; private RADV is scoped to ollama.service only."
}

risky_artifacts_without_state() {
  [[ -e "$ACTIVE_STATE" || -e "$DROPIN" || -d "$(private_prefix)" ]] && return 0
  find "$STATE_ROOT/prepared" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q . && return 0
  find /boot/loader/entries -maxdepth 1 -type f -name "*-${PROFILE_VARIANT}.conf" -print -quit 2>/dev/null | grep -q . && return 0
  find /boot -maxdepth 1 -type f -name "initramfs-*-${PROFILE_VARIANT}.img" -print -quit 2>/dev/null | grep -q . && return 0
  return 1
}

resolve_safe_stock_target() {
  local current current_bls
  current="$(kernel_release)"
  current_bls="$(find_stock_bls "$current" 2>/dev/null || true)"
  if [[ -n "$current_bls" ]] && stock_entry_file_safe "$current_bls"; then
    printf '%s|%s\n' "$current_bls" "$(basename "$current_bls" .conf)"
    return 0
  fi
  if load_active_state && stock_entry_file_safe "$BC250_GFX1013_STOCK_BLS"; then
    printf '%s|%s\n' "$BC250_GFX1013_STOCK_BLS" "$BC250_GFX1013_STOCK_ENTRY_ID"
    return 0
  fi
  return 1
}

RESTORED_STOCK_BLS=''
RESTORED_STOCK_ENTRY_ID=''
restore_stock_boot() {
  local target
  target="$(resolve_safe_stock_target)" || die "no verifiable stock BLS entry is available for rollback"
  IFS='|' read -r RESTORED_STOCK_BLS RESTORED_STOCK_ENTRY_ID <<< "$target"
  stock_entry_file_safe "$RESTORED_STOCK_BLS" || die "selected stock BLS entry is not safe: $RESTORED_STOCK_BLS"
  grub2-set-default "$RESTORED_STOCK_ENTRY_ID" || die "could not restore stock saved/default boot"
  grub2-editenv - set "next_entry=$RESTORED_STOCK_ENTRY_ID" || die "could not select stock entry for next boot"
  verify_stock_boot_authority
}

verify_stock_boot_authority() {
  [[ -n "$RESTORED_STOCK_BLS" && -n "$RESTORED_STOCK_ENTRY_ID" ]] || die "internal stock boot authority is empty"
  stock_entry_file_safe "$RESTORED_STOCK_BLS" || die "stock BLS verification failed after rollback"
  [[ "$(grub_value saved_entry)" == "$RESTORED_STOCK_ENTRY_ID" ]] || die "stock saved/default boot verification failed"
  [[ "$(grub_value next_entry)" == "$RESTORED_STOCK_ENTRY_ID" ]] || die "stock next-boot verification failed"
}

rollback_check() {
  local mode=$1 target path entry state
  gfx_lifecycle_state
  state="$GFX_LIFECYCLE_STATE"
  if ! risky_artifacts_without_state && [[ "$state" == DISABLED ]]; then
    echo "GFX1013 rollback check: PASS (already disabled)"
    return 0
  fi
  if [[ "$mode" == disable ]] && ! load_active_state; then
    die "GFX1013 artifacts exist but lifecycle state is missing/invalid; use 'bc250 gfx1013 reset --check' for recovery validation"
  fi
  target="$(resolve_safe_stock_target)" || die "no verifiable stock BLS entry is available for rollback"
  IFS='|' read -r path entry <<< "$target"
  stock_entry_file_safe "$path" || die "candidate stock BLS is not safe: $path"
  echo "GFX1013 rollback check: PASS"
  echo "  current state: $state"
  echo "  stock BLS:     $path"
  echo "  stock entry:   $entry"
  echo "  saved entry:   ${saved:-$(grub_value saved_entry)}"
  echo "  next entry:    ${next:-$(grub_value next_entry)}"
  echo "No boot state, files or services were changed."
}

remove_loaded_state_artifacts() {
  rm -f -- "$BC250_GFX1013_PATCHED_BLS" "$BC250_GFX1013_PATCHED_INITRAMFS"
  rm -rf -- "$BC250_GFX1013_PRIVATE_PREFIX"
  rm -f -- "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")"
  rm -rf -- "$(prepared_dir_for "$BC250_GFX1013_KERNEL")"
}

remove_orphaned_package_artifacts() {
  local path
  rm -f -- "$DROPIN" "$UPSTREAM_GENERATOR"
  rm -rf -- "$(private_prefix)"
  while IFS= read -r path; do rm -f -- "$path"; done < <(
    find /boot/loader/entries -maxdepth 1 -type f -name "*-${PROFILE_VARIANT}.conf" -print 2>/dev/null
  )
  while IFS= read -r path; do rm -f -- "$path"; done < <(
    find /boot -maxdepth 1 -type f -name "initramfs-*-${PROFILE_VARIANT}.img" -print 2>/dev/null
  )
  rm -rf -- "$STATE_ROOT/prepared"
  rm -f -- "$ACTIVE_STATE"
}

disable() {
  local option=${1:-} was_active=0
  need_root
  case "$option" in
    ''|--package-erase|--package-upgrade) ;;
    --check) rollback_check disable; return 0 ;;
    *) die "unsupported disable option: $option" ;;
  esac
  if ! load_active_state; then
    if risky_artifacts_without_state; then
      die "GFX1013 artifacts exist but authoritative lifecycle state is missing/invalid; use 'bc250 gfx1013 reset' after proving the stock boot path"
    fi
    echo "GFX1013 already disabled; no staged profile is present."
    return 0
  fi

  # Fail closed: boot restoration is the first destructive authority. Nothing
  # package-owned is removed until saved + next boot both point to a verified stock BLS.
  set_active_transaction_state DISABLING 0 || die "cannot persist GFX1013 DISABLING transaction state"
  restore_stock_boot

  systemctl is-active --quiet ollama.service && was_active=1 || true
  rm -f "$DROPIN"
  systemctl daemon-reload
  if ((was_active)); then
    systemctl restart ollama.service || echo "WARNING: Ollama restart failed after removing private RADV; boot rollback remains committed." >&2
  fi

  remove_loaded_state_artifacts
  rmdir "$STATE_ROOT/prepared" "$STATE_ROOT" "$PREFIX_ROOT" 2>/dev/null || true
  verify_stock_boot_authority

  if patched_boot_running; then
    echo "GFX1013 disabled and stock boot restored as saved + next path. Reboot to unload the currently running patched amdgpu module."
  else
    echo "GFX1013 disabled; stock boot and normal system Mesa are authoritative."
  fi
}

reset() {
  local option=${1:-} was_active=0
  need_root
  case "$option" in
    '') ;;
    --check) rollback_check reset; return 0 ;;
    *) die "unsupported reset option: $option" ;;
  esac
  if load_active_state; then
    disable
    return 0
  fi
  if ! risky_artifacts_without_state; then
    echo "GFX1013 reset: nothing to do; package profile is disabled."
    return 0
  fi

  # Recovery is deliberately independent of stale lifecycle metadata. It first
  # proves and commits a stock BLS path for the current/recorded kernel, then cleans
  # only package-owned GFX1013 paths.
  restore_stock_boot
  systemctl is-active --quiet ollama.service && was_active=1 || true
  remove_orphaned_package_artifacts
  systemctl daemon-reload
  if ((was_active)); then
    systemctl restart ollama.service || echo "WARNING: Ollama restart failed after GFX1013 reset; stock boot rollback remains committed." >&2
  fi
  rmdir "$STATE_ROOT" "$PREFIX_ROOT" 2>/dev/null || true
  verify_stock_boot_authority
  if patched_boot_running; then
    echo "GFX1013 recovery reset completed; stock saved + next boot is verified. Reboot to unload the currently running patched module."
  else
    echo "GFX1013 recovery reset completed; stock boot and normal system Mesa are authoritative."
  fi
}

if [[ ${BC250_GFX1013_LIBRARY_ONLY:-0} == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

case "${1:-status}" in
  status)
    case "${2:-}" in '' ) status ;; --json) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; status_json ;; *) usage >&2; exit 2 ;; esac ;;
  prepare) [[ $# -le 2 ]] || { usage >&2; exit 2; }; prepare "${2:-}" ;;
  enable) [[ $# -eq 1 ]] || { usage >&2; exit 2; }; enable ;;
  disable) [[ $# -le 2 ]] || { usage >&2; exit 2; }; disable "${2:-}" ;;
  reset) [[ $# -le 2 ]] || { usage >&2; exit 2; }; reset "${2:-}" ;;
  benchmark) benchmark "$@" ;;
  ollama-guard) [[ $# -eq 1 ]] || exit 1; ollama_guard ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac

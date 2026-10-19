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
PACKAGE_PROFILE=v0.2.5-alpha
UPSTREAM_VERSION=0.2.0-alpha
PINNED_COMMIT=d3e6dc062c34d2523db0abe5741d1f5b0dea00d9
PATCH_REFERENCE_KERNEL=7.2.9-200.fc44.x86_64
PACKAGE_QUALIFICATION_KERNEL=7.2.10-200.fc44.x86_64
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
LIFECYCLE_LOCK="${BC250_GFX1013_LIFECYCLE_LOCK:-/run/lock/bc250-gfx1013.lock}"
LIFECYCLE_LOCK_HELD=0
LIFECYCLE_LOCK_FD=''
ACTIVE_PHASE_PID=''
GFX_VERBOSE=0
OS_RELEASE_FILE="${BC250_GFX1013_OS_RELEASE_FILE:-/etc/os-release}"

usage() {
  cat <<'USAGE'
Usage: bc250 gfx1013 {status|prepare|stage-boot|enable|disable|reset|benchmark}

Experimental BC-250 GFX1013 compute profile. Default is OFF.

Typical activation
  sudo bc250 gfx1013 prepare --check
  sudo bc250 gfx1013 prepare
  sudo bc250 gfx1013 stage-boot
  sudo reboot
  sudo bc250 gfx1013 enable

Return to stock
  sudo bc250 gfx1013 disable
  sudo reboot

Inspection
  status [--brief|--verbose|--json]
       Show current GFX lifecycle, kernel, boot and RADV state.
       Default output is operator-focused; --brief is harness-friendly and
       --verbose exposes provenance, boot internals and evidence paths.

Preparation
  prepare [--check|--download-only] [--verbose]
       Check requirements, fetch sources, or build the patched amdgpu module
       and private RADV for the exact running kernel. Preparation does not
       change boot selection or service/runtime state.

Activation
  stage-boot
       Stage the prepared patched environment for the next boot only.
       The verified stock saved/default entry remains unchanged.

  enable
       Verify the patched boot and module identity, activate private RADV
       for Ollama, then make the verified patched boot persistent.

Deactivation
  disable [--check]
       Verify rollback readiness or restore verified stock boot configuration
       and remove the GFX runtime override. When currently running the patched
       kernel, a reboot is required to complete the return to stock runtime.

Recovery only
  reset [--check]
       Validate or remove stale/orphaned package-owned GFX state after proving
       a safe stock boot path. Fails closed if stock boot cannot be proven.

Qualification / performance testing
  benchmark {stock|gfx|restored|status|report} ...
       Run the reboot-aware same-package A1/B/A2 campaign. Benchmarking never
       changes boot state or enables/disables GFX1013 itself.

The package profile is v0.2.5-alpha, based on upstream 0.2.0-alpha commit
 d3e6dc062c34d2523db0abe5741d1f5b0dea00d9. Profile identifiers and exact
provenance are available from status --verbose/--json. Mesh/task, 40-CU, FSR
and tuning changes are outside this profile.
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
terminal_color_enabled() { [[ -t 1 && ${TERM:-dumb} != dumb && -z ${NO_COLOR:-} ]]; }
print_next_action() {
  if terminal_color_enabled; then
    printf '\033[1;33mNext action: %s\033[0m\n' "$*"
  else
    printf 'Next action: %s\n' "$*"
  fi
}
die() {
  local message="$*"
  if [[ -n ${PREPARE_DIR:-} && ${PREPARE_COMMITTED:-1} != 1 ]]; then
    [[ -n ${PREPARE_FAILURE_REASON:-} ]] || PREPARE_FAILURE_REASON="$message"
    exit 2
  fi
  printf 'ERROR: %s\n' "$message" >&2
  exit 2
}
need_root() { [[ ${EUID:-$(id -u)} -eq 0 ]] || die "requires root (run with sudo)"; }

acquire_lifecycle_lock() {
  ((LIFECYCLE_LOCK_HELD)) && return 0
  command -v flock >/dev/null 2>&1 || die "required lifecycle lock tool is unavailable: flock"
  [[ -d "$(dirname "$LIFECYCLE_LOCK")" ]] || install -d -m 0755 "$(dirname "$LIFECYCLE_LOCK")"
  exec {LIFECYCLE_LOCK_FD}>"$LIFECYCLE_LOCK" || die "cannot open GFX1013 lifecycle lock: $LIFECYCLE_LOCK"
  if ! flock -n "$LIFECYCLE_LOCK_FD"; then
    eval "exec ${LIFECYCLE_LOCK_FD}>&-" || true
    LIFECYCLE_LOCK_FD=''
    die "another GFX1013 lifecycle mutation is already in progress"
  fi
  LIFECYCLE_LOCK_HELD=1
}

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
  gcc gcc-c++ make rpm rpm-build redhat-rpm-config kernel-srpm-macros git-core cargo rust cargo-rpm-macros binutils bzip2 cpio dracut patch xz
  elfutils-libelf-devel openssl-devel meson ninja-build
  bison flex python3-mako python3-pycparser python3-pyyaml python3-packaging glslang glslang-devel
  vulkan-headers vulkan-loader-devel systemd-devel libdrm-devel expat-devel pkgconf-pkg-config
  zlib-devel libzstd-devel spirv-tools-devel
)

# Fedora kernel.spec uses this macro during %prep. Keep this as an RPM capability
# rather than a package-name dependency so provider resolution remains authoritative.
GFX_BUILD_CAPABILITIES=(
  'rpm_macro(py3_shebang_fix)'
)

build_requirement_provider() {
  local requirement=$1 provider
  # RPM exit status is authoritative. A failed `rpm -q` may print
  # "package ... is not installed" on stdout; never treat that text as a
  # provider merely because it is non-empty.
  if provider="$(rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' \
      "$requirement" 2>/dev/null)"; then
    provider="${provider%%$'\n'*}"
    [[ -n "$provider" ]] || return 1
    printf '%s\n' "$provider"
    return 0
  fi
  if provider="$(rpm -q --whatprovides --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' \
      "$requirement" 2>/dev/null)"; then
    provider="${provider%%$'\n'*}"
    [[ -n "$provider" ]] || return 1
    printf '%s\n' "$provider"
    return 0
  fi
  return 1
}

all_build_requirements() {
  printf '%s\n' "${GFX_BUILD_PACKAGES[@]}" "${GFX_BUILD_CAPABILITIES[@]}"
}

GFX_MISSING_BUILD_REQUIREMENTS=()
GFX_BUILD_REQUIREMENT_TOTAL=0

check_build_requirements() {
  local verbose=${1:-0} requirement provider satisfied=0
  local -a requirements=()
  mapfile -t requirements < <(all_build_requirements)
  GFX_BUILD_REQUIREMENT_TOTAL=${#requirements[@]}
  GFX_MISSING_BUILD_REQUIREMENTS=()
  for requirement in "${requirements[@]}"; do
    if provider="$(build_requirement_provider "$requirement")"; then
      satisfied=$((satisfied + 1))
      if [[ "$verbose" == 1 ]]; then
        printf '    requirement: %-34s provider: %-54s status: SATISFIED\n' "$requirement" "$provider"
      fi
    else
      GFX_MISSING_BUILD_REQUIREMENTS+=("$requirement")
      if [[ "$verbose" == 1 ]]; then
        printf '    requirement: %-34s provider: %-54s status: NOT INSTALLED\n' "$requirement" '<none>'
      fi
    fi
  done
  if ((${#GFX_MISSING_BUILD_REQUIREMENTS[@]})); then
    printf '  Build dependencies: BLOCKED — %d missing (%d/%d satisfied)\n' \
      "${#GFX_MISSING_BUILD_REQUIREMENTS[@]}" "$satisfied" "$GFX_BUILD_REQUIREMENT_TOTAL"
    if [[ "$verbose" != 1 ]]; then
      for requirement in "${GFX_MISSING_BUILD_REQUIREMENTS[@]}"; do
        printf '    %s — NOT INSTALLED (provider: <none>)\n' "$requirement"
      done
    fi
    return 1
  fi
  printf '  Build dependencies: PASS — %d/%d satisfied\n' "$satisfied" "$GFX_BUILD_REQUIREMENT_TOTAL"
  return 0
}

missing_build_packages() {
  local requirement provider
  local -a missing=() requirements=()
  mapfile -t requirements < <(all_build_requirements)
  for requirement in "${requirements[@]}"; do
    if provider="$(build_requirement_provider "$requirement")"; then
      :
    else
      missing+=("$requirement")
    fi
  done
  ((${#missing[@]})) && printf '%s\n' "${missing[@]}"
  return 0
}

print_requirement_install_command() {
  local requirement
  printf 'sudo dnf install'
  for requirement in "$@"; do
    printf ' %q' "$requirement"
  done
  printf '\n'
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

source_integrity_detail() {
  local manifest expected relative target observed
  for manifest in PATCH-SHA256SUMS SOURCE-SHA256SUMS; do
    [[ -r "$SOURCE/$manifest" ]] || { printf 'missing manifest: %s\n' "$manifest"; return 1; }
    while read -r expected relative; do
      [[ -n "${expected:-}" && -n "${relative:-}" ]] || continue
      relative="${relative#./}"
      target="$SOURCE/$relative"
      [[ -f "$target" ]] || { printf 'missing file: %s\n' "$relative"; return 1; }
      observed="$(sha256sum "$target" | awk '{print $1}')"
      if [[ "$observed" != "$expected" ]]; then
        printf 'checksum mismatch: %s; expected=%s; observed=%s\n' "$relative" "$expected" "$observed"
        return 1
      fi
    done < "$SOURCE/$manifest"
  done
  return 0
}

installed_payload_integrity_detail() {
  local package verification line path first=''
  command -v rpm >/dev/null 2>&1 || { printf 'rpm unavailable'; return 1; }
  package="$(rpm -qf --qf '%{NAME}\n' "$SOURCE/SOURCE-SHA256SUMS" 2>/dev/null | head -1 || true)"
  [[ -n "$package" ]] || { printf 'package owner unavailable for %s' "$SOURCE"; return 1; }
  verification="$(rpm -V "$package" 2>&1 || true)"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    path="${line##* }"
    if [[ "$path" == "$SOURCE/"* || "$path" == "$SOURCE" ]]; then
      first="$line"
      break
    fi
  done <<< "$verification"
  [[ -z "$first" ]] || { printf '%s' "$first"; return 1; }
  return 0
}

operator_state_label() {
  case "$1" in
    DISABLED) printf 'disabled' ;;
    PREPARED) printf 'prepared — boot activation pending' ;;
    PATCHED_BOOT_UNVERIFIED) printf 'patched boot — activation pending' ;;
    ENABLED) printf 'enabled' ;;
    STOCK_REBOOT_REQUIRED) printf 'stock reboot required' ;;
    ROLLBACK_REQUIRED) printf 'action required — recovery/rollback needed' ;;
    NOT_INSPECTED) printf 'not inspected — root inspection required' ;;
    *) printf '%s' "$1" ;;
  esac
}

next_action_for_state() {
  local state=$1 next=''
  case "$state" in
    DISABLED) printf 'sudo bc250 gfx1013 prepare --check\n' ;;
    PREPARED)
      next="$(grub_value next_entry)"
      if load_active_state && [[ "$next" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]]; then
        printf 'sudo reboot\n'
      elif load_active_state && [[ -n "$next" && "$next" != "$BC250_GFX1013_STOCK_ENTRY_ID" ]]; then
        printf 'sudo bc250 gfx1013 status --verbose\n'
      else
        printf 'sudo bc250 gfx1013 stage-boot\n'
      fi
      ;;
    PATCHED_BOOT_UNVERIFIED) printf 'sudo bc250 gfx1013 enable\n' ;;
    ENABLED) printf 'no lifecycle action required; benchmark only when qualifying\n' ;;
    STOCK_REBOOT_REQUIRED) printf 'sudo reboot\n' ;;
    ROLLBACK_REQUIRED) printf 'sudo bc250 gfx1013 reset --check\n' ;;
    NOT_INSPECTED) printf 'sudo bc250 gfx1013 status --brief\n' ;;
    *) printf 'sudo bc250 gfx1013 status\n' ;;
  esac
}

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
  [[ "${BC250_GFX1013_BUILD_EVIDENCE:-}" == "$STATE_ROOT/prepared/$BC250_GFX1013_KERNEL/build-evidence" ]] || return 1
  [[ "${BC250_GFX1013_KERNEL_BUILD_RESULT:-}" == PASS ]] || return 1
  [[ "${BC250_GFX1013_MESA_BUILD_RESULT:-}" == PASS ]] || return 1
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
  [[ "${BC250_GFX1013_MODULE_SRCVERSION:-}" == none || "${BC250_GFX1013_MODULE_SRCVERSION:-}" =~ ^[A-Za-z0-9]+$ ]] || return 1
  for hash_name in BC250_GFX1013_PATCHED_BLS_SHA256 BC250_GFX1013_PATCHED_INITRAMFS_SHA256; do
    [[ -z "${!hash_name:-}" || "${!hash_name}" =~ ^[0-9a-f]{64}$ ]] || return 1
  done
  if [[ -n "${BC250_GFX1013_PACKAGE_NEVRA:-}" ]]; then
    [[ "$BC250_GFX1013_PACKAGE_NEVRA" =~ ^bc250-llm-server-[A-Za-z0-9._+~:-]+\.x86_64$ ]] || return 1
  fi
  if [[ -n "${BC250_GFX1013_VULKAN_COMPUTE_QUEUE_FAMILY:-}" ]]; then
    [[ "$BC250_GFX1013_VULKAN_COMPUTE_QUEUE_FAMILY" =~ ^[0-9]+$ ]] || return 1
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
  if [[ "$kernel" == "$PACKAGE_QUALIFICATION_KERNEL" ]]; then
    printf 'Package qualification: %s — MATCH\n' "$PACKAGE_QUALIFICATION_KERNEL"
  else
    printf 'Package qualification: %s — DIFFERENT\n' "$PACKAGE_QUALIFICATION_KERNEL"
  fi
  printf 'Patch/profile reference: %s\n' "$PATCH_REFERENCE_KERNEL"
}

stock_entry_file_safe() {
  local path=$1 expected_kernel=${2:-} version linux_path token initrd_ok=0
  [[ -f "$path" ]] || return 1
  grep -qw "$PATCH_MARKER" "$path" 2>/dev/null && return 1

  version="$(awk '$1 == "version" {print $2}' "$path")"
  [[ "$version" =~ ^[A-Za-z0-9._+-]+$ ]] || return 1
  [[ -z "$expected_kernel" || "$version" == "$expected_kernel" ]] || return 1
  linux_path="$(awk '$1 == "linux" {print $2}' "$path")"
  [[ "${linux_path##*/}" == "vmlinuz-$version" ]] || return 1
  while read -r token; do
    [[ "${token##*/}" == "initramfs-$version.img" ]] && initrd_ok=1
  done < <(awk '$1 == "initrd" {for (i=2; i<=NF; i++) print $i}' "$path")
  ((initrd_ok)) || return 1
  return 0
}

GFX_STATE_REASON=''
GFX_LIFECYCLE_STATE='ROLLBACK_REQUIRED'
gfx_lifecycle_state() {
  local current_kernel current_package saved next enabled phase
  GFX_STATE_REASON=''
  current_kernel="$(kernel_release)"
  current_package="$(package_nevra)"
  saved="$(grub_value saved_entry)"
  next="$(grub_value next_entry)"

  # The lifecycle state is root-owned on an installed appliance. A non-root
  # status probe must distinguish a genuinely absent state from state that exists
  # but cannot be inspected. Do not infer NOT_INSPECTED merely from EUID: tests,
  # development trees and explicit alternate state roots may be fully readable.
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    if [[ -d "$STATE_ROOT" && ! -x "$STATE_ROOT" ]]; then
      GFX_STATE_REASON='authoritative lifecycle state requires root inspection'
      GFX_LIFECYCLE_STATE=NOT_INSPECTED
      return 0
    fi
    if [[ -e "$ACTIVE_STATE" && ! -r "$ACTIVE_STATE" ]]; then
      GFX_STATE_REASON='authoritative lifecycle state requires root inspection'
      GFX_LIFECYCLE_STATE=NOT_INSPECTED
      return 0
    fi
  fi

  if [[ ! -e "$ACTIVE_STATE" ]]; then
    if patched_boot_running; then
      if stock_reboot_pending; then
        GFX_STATE_REASON='previous patched GFX1013 runtime is still loaded; verified stock saved/default and next boot are already selected; reboot required'
        GFX_LIFECYCLE_STATE=STOCK_REBOOT_REQUIRED
      else
        GFX_STATE_REASON='patched boot marker is running without authoritative package lifecycle state'
        GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
      fi
    elif risky_artifacts_without_state; then
      GFX_STATE_REASON='package GFX1013 artifacts exist without authoritative lifecycle state'
      GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    else
      GFX_STATE_REASON='no prepared or active GFX1013 profile'
      GFX_LIFECYCLE_STATE=DISABLED
    fi
    return 0
  fi
  if ! load_active_state; then
    GFX_STATE_REASON='active lifecycle state exists but failed validation'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  phase="${BC250_GFX1013_TRANSACTION_PHASE:-}"
  enabled="${BC250_GFX1013_ENABLED:-0}"
  if [[ "${BC250_GFX1013_RECOVERY_REQUIRED:-0}" == 1 || "$phase" =~ ^(RECOVERY_REQUIRED|SAFETY_FAILURE|ENABLING|DISABLING|BOOT_ENTRY_STAGING)$ ]]; then
    GFX_STATE_REASON="lifecycle transaction requires recovery (${phase:-unknown})"
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if [[ -z "${BC250_GFX1013_PACKAGE_NEVRA:-}" ]]; then
    GFX_STATE_REASON='pre-greenfield preparation lacks package identity; rollback/reprepare required'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if [[ -z "$current_package" || "$current_package" != "$BC250_GFX1013_PACKAGE_NEVRA" ]]; then
    GFX_STATE_REASON="package identity changed since prepare (${BC250_GFX1013_PACKAGE_NEVRA} -> ${current_package:-unavailable})"
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if ! stock_entry_file_safe "$BC250_GFX1013_STOCK_BLS" "$BC250_GFX1013_KERNEL"; then
    GFX_STATE_REASON='recorded stock BLS entry is missing, patched, or does not match its kernel/initramfs identity'
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi
  if [[ "$current_kernel" != "$BC250_GFX1013_KERNEL" ]]; then
    GFX_STATE_REASON="running kernel $current_kernel differs from prepared kernel $BC250_GFX1013_KERNEL; rollback/reprepare required"
    GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
    return 0
  fi

  case "$phase:$enabled" in
    ENABLED:1)
      if ! patched_boot_running; then
        GFX_STATE_REASON='enabled state requires the marked patched boot'
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
      ;;
    PREPARED:0)
      if [[ -f "$DROPIN" ]]; then
        GFX_STATE_REASON='Ollama private-RADV override exists before enabled commit'
        GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
      elif [[ "$saved" != "$BC250_GFX1013_STOCK_ENTRY_ID" ]]; then
        GFX_STATE_REASON='prepared state requires the recorded stock BLS as saved/default'
        GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
      elif patched_boot_running; then
        if [[ -z "${BC250_GFX1013_PATCHED_BLS:-}" || -z "${BC250_GFX1013_PATCHED_INITRAMFS:-}" || ! -f "$BC250_GFX1013_PATCHED_BLS" || ! -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]]; then
          GFX_STATE_REASON='patched boot is running but recorded patched boot artifacts are missing'
          GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
        elif [[ -n "$next" ]]; then
          GFX_STATE_REASON='patched boot is running but one-shot next_entry was not consumed'
          GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
        else
          GFX_STATE_REASON='running the prepared one-shot patched boot; activation not yet committed'
          GFX_LIFECYCLE_STATE=PATCHED_BOOT_UNVERIFIED
        fi
      elif [[ -z "$next" ]]; then
        GFX_STATE_REASON='exact-kernel profile is prepared; boot activation has not been staged'
        GFX_LIFECYCLE_STATE=PREPARED
      elif [[ "$next" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]]; then
        if [[ -z "${BC250_GFX1013_PATCHED_BLS:-}" || -z "${BC250_GFX1013_PATCHED_INITRAMFS:-}" || ! -f "$BC250_GFX1013_PATCHED_BLS" || ! -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]]; then
          GFX_STATE_REASON='patched next boot is selected but recorded boot artifacts are missing'
          GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
        else
          GFX_STATE_REASON='exact-kernel profile is prepared; patched boot is selected for the next boot only'
          GFX_LIFECYCLE_STATE=PREPARED
        fi
      else
        GFX_STATE_REASON="exact-kernel profile is prepared; another one-shot boot is already selected ($next)"
        GFX_LIFECYCLE_STATE=PREPARED
      fi
      ;;
    *)
      GFX_STATE_REASON="lifecycle phase/enabled mismatch ($phase/$enabled)"
      GFX_LIFECYCLE_STATE=ROLLBACK_REQUIRED
      ;;
  esac
}

status_json() {
  local state reason source_ok device_ok secure saved next current_package prepared_package
  local prepared_kernel enabled icd_present radv_present dropin_present patched_running payload_ok
  local module_sha vermagic kernel_result mesa_result evidence queue stock_target resolved_stock_bls resolved_stock_entry
  gfx_lifecycle_state
  state="$GFX_LIFECYCLE_STATE"; reason="$GFX_STATE_REASON"
  source_ok=false; source_identity_ok && source_ok=true
  device_ok=false; bc250_device_present && device_ok=true
  payload_ok=false; installed_payload_integrity_detail >/dev/null 2>&1 && payload_ok=true
  secure="$(secure_boot_state)"
  saved="$(grub_value saved_entry)"; next="$(grub_value next_entry)"
  current_package="$(package_nevra)"
  prepared_package=''; prepared_kernel=''; enabled='0'; module_sha=''; vermagic=''
  kernel_result=''; mesa_result=''; evidence=''; queue=''
  if load_active_state; then
    prepared_package="${BC250_GFX1013_PACKAGE_NEVRA:-}"
    prepared_kernel="${BC250_GFX1013_KERNEL:-}"
    enabled="${BC250_GFX1013_ENABLED:-0}"
    module_sha="${BC250_GFX1013_MODULE_SHA256:-}"
    vermagic="${BC250_GFX1013_VERMAGIC:-}"
    kernel_result="${BC250_GFX1013_KERNEL_BUILD_RESULT:-}"
    mesa_result="${BC250_GFX1013_MESA_BUILD_RESULT:-}"
    evidence="${BC250_GFX1013_BUILD_EVIDENCE:-}"
    queue="${BC250_GFX1013_VULKAN_COMPUTE_QUEUE_FAMILY:-}"
  fi
  icd_present=false; [[ -f "$(private_icd)" ]] && icd_present=true
  radv_present=false; [[ -f "$(private_radv_lib)" ]] && radv_present=true
  dropin_present=false; [[ -f "$DROPIN" ]] && dropin_present=true
  patched_running=false; patched_boot_running && patched_running=true
  resolved_stock_entry="${BC250_GFX1013_STOCK_ENTRY_ID:-}"
  if stock_target="$(resolve_safe_stock_target 2>/dev/null)"; then
    IFS='|' read -r resolved_stock_bls resolved_stock_entry <<< "$stock_target"
  fi
  python3 - "$state" "$reason" "$PACKAGE_PROFILE" "$UPSTREAM_VERSION" "$PINNED_COMMIT" \
    "$(kernel_release)" "$PACKAGE_QUALIFICATION_KERNEL" "$PATCH_REFERENCE_KERNEL" "$secure" "$source_ok" "$payload_ok" "$device_ok" \
    "$current_package" "$prepared_package" "$prepared_kernel" "$enabled" "$saved" "$next" \
    "$patched_running" "$dropin_present" "$radv_present" "$icd_present" \
    "$resolved_stock_entry" "${BC250_GFX1013_PATCHED_ENTRY_ID:-}" \
    "${BC250_GFX1013_VULKAN_VENDOR_ID:-}" "${BC250_GFX1013_VULKAN_DEVICE_ID:-}" \
    "${BC250_GFX1013_VULKAN_DRIVER_NAME:-}" "${BC250_GFX1013_VULKAN_SUMMARY_SHA256:-}" \
    "$MESA_VERSION" "$MESA_SRPM_NEVRA" "$MESA_SOURCE0" "$MESA_SOURCE0_SHA256" \
    "$module_sha" "$vermagic" "$kernel_result" "$mesa_result" "$evidence" "$queue" <<'PY_JSON'
import json
import sys
(
    state, reason, profile, upstream, commit, running_kernel, qualification_kernel, patch_reference_kernel, secure_boot,
    source_ok, payload_ok, device_ok, package, prepared_package, prepared_kernel, enabled,
    saved, next_entry, patched_running, dropin, radv, icd, stock_entry, patched_entry,
    vk_vendor, vk_device, vk_driver, vk_summary_sha, mesa_version, mesa_srpm_nevra,
    mesa_source0, mesa_source0_sha, module_sha, vermagic, kernel_result, mesa_result,
    evidence, queue,
) = sys.argv[1:]
def b(value: str) -> bool:
    return value == "true"
payload = {
    "schema": "bc250.gfx1013-status.v2",
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
    "kernel": {"running": running_kernel, "prepared": prepared_kernel or None, "qualification": qualification_kernel, "patch_reference": patch_reference_kernel, "qualification_match": running_kernel == qualification_kernel},
    "secure_boot": secure_boot,
    "integrity": {"carried_source": b(source_ok), "installed_rpm_payload": b(payload_ok)},
    "bc250_device_present": b(device_ok),
    "enabled_recorded": enabled == "1",
    "prepared_build": {
        "module_sha256": module_sha or None,
        "module_vermagic": vermagic or None,
        "kernel_build_result": kernel_result or None,
        "mesa_build_result": mesa_result or None,
        "evidence_path": evidence or None,
    },
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
        "compute_queue_family": int(queue) if queue.isdigit() else None,
    },
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY_JSON
}

status_verbose() {
  local icd saved next state reason secure current_package missing_packages payload_detail
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
    echo "Carried source integrity: PASS ($SOURCE)"
  else
    echo "Carried source integrity: FAIL ($SOURCE)"
  fi
  if payload_detail="$(installed_payload_integrity_detail)"; then
    echo "Installed RPM payload integrity: PASS"
  else
    echo "Installed RPM payload integrity: FAIL (${payload_detail:-unknown})"
  fi

  echo "Prepared build:"
  if load_active_state; then
    echo "  Prepared kernel: $BC250_GFX1013_KERNEL"
    echo "  Prepared package: ${BC250_GFX1013_PACKAGE_NEVRA:-unrecorded}"
    echo "  Patched amdgpu SHA256: $BC250_GFX1013_MODULE_SHA256"
    echo "  Module vermagic: $BC250_GFX1013_VERMAGIC"
    echo "  Module srcversion (supplemental): $BC250_GFX1013_MODULE_SRCVERSION"
    echo "  Kernel patch/build result: $BC250_GFX1013_KERNEL_BUILD_RESULT"
    echo "  Mesa/private RADV build result: $BC250_GFX1013_MESA_BUILD_RESULT"
    echo "  Private RADV path: $BC250_GFX1013_PRIVATE_RADV_LIB"
    [[ -f "$BC250_GFX1013_PRIVATE_RADV_LIB" ]] && echo "  Private RADV presence: present" || echo "  Private RADV presence: MISSING"
    [[ -f "$DROPIN" ]] && echo "  Ollama private-RADV override: ENABLED" || echo "  Ollama private-RADV override: disabled"
    echo "  Stock boot entry: $BC250_GFX1013_STOCK_ENTRY_ID"
    echo "  Patched boot entry target: $BC250_GFX1013_PATCHED_ENTRY_ID"
    if [[ -f "$BC250_GFX1013_PATCHED_BLS" && -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]]; then
      echo "  Patched boot artifacts: staged"
    else
      echo "  Patched boot artifacts: not staged"
    fi
    echo "  Build evidence: $BC250_GFX1013_BUILD_EVIDENCE"
    [[ -n "${BC250_GFX1013_VULKAN_COMPUTE_QUEUE_FAMILY:-}" ]] && \
      echo "  Verified BC-250 compute queue family: $BC250_GFX1013_VULKAN_COMPUTE_QUEUE_FAMILY"
  else
    echo "  none (absent or invalid)"
  fi

  patched_boot_running && echo "Running boot: patched GFX1013" || echo "Running boot: stock/unmarked"
  command -v grub2-editenv >/dev/null 2>&1 && {
    saved="$(grub_value saved_entry)"; next="$(grub_value next_entry)"
    echo "GRUB saved entry: ${saved:-<unset>}"
    echo "GRUB next entry: ${next:-<unset>}"
    local stock_target resolved_stock_bls resolved_stock_entry
    if stock_target="$(resolve_safe_stock_target 2>/dev/null)"; then
      IFS='|' read -r resolved_stock_bls resolved_stock_entry <<< "$stock_target"
      echo "Verified stock entry: $resolved_stock_entry"
    fi
  }
  [[ -f "$icd" ]] && echo "Private RADV payload: present ($icd)" || echo "Private RADV payload: absent"
  [[ -f "$DROPIN" ]] && echo "Experimental private-RADV override: ENABLED" || echo "Experimental private-RADV override: disabled"
  [[ -e "$UPSTREAM_GENERATOR" || -e "$UPSTREAM_STATE/active.env" ]] \
    && echo "Separate upstream GFX1013 installation: CONFLICT" \
    || echo "Separate upstream GFX1013 installation: absent"
  missing_packages="$(missing_build_packages)"
  if [[ -n "$missing_packages" ]]; then
    echo "Build dependencies required for GFX1013 prepare: missing"
    while IFS= read -r package; do
      [[ -n "$package" ]] && printf '  requirement: %s; provider: <not installed>; status: NOT INSTALLED\n' "$package"
    done <<< "$missing_packages"
  else
    echo "Build dependencies required for GFX1013 prepare: satisfied"
  fi
  print_next_action "$(next_action_for_state "$state")"
}

status() {
  local state reason kernel current_package missing_requirements payload_detail source_ok=0 payload_ok=0
  local prepared='none' boot='stock' radv='absent / disabled' missing_count=0
  gfx_lifecycle_state
  state="$GFX_LIFECYCLE_STATE"; reason="$GFX_STATE_REASON"
  kernel="$(kernel_release)"; current_package="$(package_nevra)"
  source_identity_ok && source_ok=1
  if payload_detail="$(installed_payload_integrity_detail)"; then payload_ok=1; fi
  if load_active_state; then
    prepared="${BC250_GFX1013_KERNEL:-unknown} / ${BC250_GFX1013_PROFILE:-$PACKAGE_PROFILE}"
  fi
  patched_boot_running && boot='patched GFX1013'
  if [[ -f "$(private_radv_lib)" ]]; then
    [[ -f "$DROPIN" ]] && radv='present / enabled' || radv='present / disabled'
  fi
  missing_requirements="$(missing_build_packages)"
  [[ -z "$missing_requirements" ]] || missing_count="$(printf '%s\n' "$missing_requirements" | sed '/^$/d' | wc -l)"

  echo "GFX1013 state: $(operator_state_label "$state")"
  echo "Kernel: $kernel"
  echo "Prepared build: $prepared"
  echo "Running boot: $boot"
  echo "Private RADV: $radv"
  if ((source_ok && payload_ok)); then
    echo "Integrity: PASS"
  else
    echo "Integrity: FAIL"
  fi
  if [[ -z "$missing_requirements" ]]; then
    echo "Build dependencies: satisfied"
  else
    echo "Build dependencies: BLOCKED — $missing_count missing"
  fi
  [[ "$state" == DISABLED ]] || echo "State detail: $reason"
  echo "Installed package: ${current_package:-unavailable}"
  print_next_action "$(next_action_for_state "$state")"
}

status_brief() {
  local state kernel payload_detail source_ok=0 payload_ok=0 prepared='none' boot='stock' radv='disabled'
  gfx_lifecycle_state
  state="$GFX_LIFECYCLE_STATE"; kernel="$(kernel_release)"
  source_identity_ok && source_ok=1
  if payload_detail="$(installed_payload_integrity_detail)"; then payload_ok=1; fi
  if load_active_state; then
    prepared="${BC250_GFX1013_KERNEL:-unknown}/${BC250_GFX1013_PROFILE:-$PACKAGE_PROFILE}"
  fi
  patched_boot_running && boot='patched'
  [[ -f "$DROPIN" ]] && radv='enabled'
  echo "GFX1013 state: $state"
  echo "Running kernel: $kernel"
  echo "Prepared: $prepared"
  echo "Boot: $boot"
  echo "Private RADV: $radv"
  if ((source_ok && payload_ok)); then echo "Integrity: PASS"; else echo "Integrity: FAIL"; fi
  print_next_action "$(next_action_for_state "$state")"
}

check_os_and_boot_tools() {
  [[ -r "$OS_RELEASE_FILE" ]] || die "$OS_RELEASE_FILE is missing"
  # shellcheck disable=SC1090
  . "$OS_RELEASE_FILE"
  [[ "${ID:-}" == fedora ]] || die "GFX1013 package profile supports Fedora only"
  command -v rpm-ostree >/dev/null 2>&1 && die "image/Atomic Fedora is not supported by this direct exact-kernel profile"
  local cmd missing=()
  for cmd in curl xz zstd gzip bzip2 tar cpio patch gcc g++ make cargo rpm rpm2cpio rpmbuild meson ninja python3 nm readelf vulkaninfo \
    sha256sum modinfo modprobe depmod dracut lsinitrd grub2-editenv grub2-set-default flock setsid awk sed grep find install; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if ((${#missing[@]})); then
    printf 'ERROR: GFX1013 build/install tools missing: %s\n' "${missing[*]}" >&2
    printf 'Install the required GFX1013 prepare dependencies and exact running-kernel headers, for example:\n' >&2
    printf '  sudo dnf install kernel-devel-%s gcc gcc-c++ make rpm-build redhat-rpm-config kernel-srpm-macros git-core cargo rust cargo-rpm-macros binutils bzip2 elfutils-libelf-devel openssl-devel meson ninja-build bison flex python3-mako python3-pycparser python3-pyyaml python3-packaging glslang glslang-devel vulkan-headers vulkan-loader-devel systemd-devel libdrm-devel expat-devel pkgconf-pkg-config zlib-devel libzstd-devel spirv-tools-devel\n' "$(kernel_release | sed 's/\.x86_64$//')" >&2
    exit 2
  fi
  local missing_packages package
  local -a missing_package_list=()
  missing_packages="$(missing_build_packages)"
  if [[ -n "$missing_packages" ]]; then
    mapfile -t missing_package_list <<< "$missing_packages"
    printf 'ERROR: required GFX1013 prepare requirements are not installed/provided:\n' >&2
    for package in "${missing_package_list[@]}"; do [[ -n "$package" ]] && printf '  requirement: %s; installed provider: <none>; status: NOT INSTALLED\n' "$package" >&2; done
    printf 'Install them with: sudo dnf install' >&2
    for package in "${missing_package_list[@]}"; do [[ -n "$package" ]] && printf ' %q' "$package" >&2; done
    printf '\n' >&2
    exit 2
  fi
  secure_boot_prepare_ok
}

human_bytes() {
  local bytes=${1:-0}
  awk -v n="$bytes" 'BEGIN {
    split("B KiB MiB GiB", u, " "); i=1;
    while (n >= 1024 && i < 4) { n/=1024; i++ }
    if (i == 1) printf "%.0f %s", n, u[i]; else printf "%.1f %s", n, u[i]
  }'
}

remote_content_length() {
  local url=$1
  curl --silent --show-error --fail --location --head --retry 1 --connect-timeout 10 --max-time 20 \
    --proto '=https' --tlsv1.2 "$url" 2>/dev/null | \
    awk 'BEGIN{IGNORECASE=1} /^content-length:/ {gsub("\r", "", $2); value=$2} END{if(value ~ /^[0-9]+$/) print value}'
}

validate_source_rpm() {
  local path=$1 expected_nevr=$2 identity source_package verify
  identity="$(rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}\n' "$path" 2>/dev/null || true)"
  source_package="$(rpm -qp --qf '%{SOURCEPACKAGE}\n' "$path" 2>/dev/null || true)"
  [[ "$identity" == "$expected_nevr" && "$source_package" == 1 ]] || return 1
  verify="$(LC_ALL=C rpm -K "$path" 2>&1)" || return 1
  grep -Eqi 'NOKEY|NOT OK' <<<"$verify" && return 1
  return 0
}

cache_readiness() {
  local label=$1 dest=$2 url=$3 expected_nevr=$4 remote='' local_bytes=0
  if [[ -s "$dest" ]] && validate_source_rpm "$dest" "$expected_nevr"; then
    local_bytes="$(stat -c '%s' "$dest")"
    printf '  %s: cache HIT — %s (%s)\n' "$label" "$(human_bytes "$local_bytes")" "$dest"
    return 0
  fi
  remote="$(remote_content_length "$url" || true)"
  if [[ -s "$dest.part" ]]; then
    local_bytes="$(stat -c '%s' "$dest.part")"
    if [[ -n "$remote" ]]; then
      printf '  %s: cache PARTIAL — %s / %s available (%s)\n' "$label" "$(human_bytes "$local_bytes")" "$(human_bytes "$remote")" "$dest.part"
    else
      printf '  %s: cache PARTIAL — %s available; remote size unknown (%s)\n' "$label" "$(human_bytes "$local_bytes")" "$dest.part"
    fi
  elif [[ -n "$remote" ]]; then
    printf '  %s: cache MISS — ~%s download required (%s)\n' "$label" "$(human_bytes "$remote")" "$dest"
  else
    printf '  %s: cache MISS — download required; remote size unavailable (%s)\n' "$label" "$dest"
  fi
  return 1
}

fetch_verified_srpm() {
  local url=$1 dest=$2 expected_nevr=$3 artifact=$4 reason=$5
  local part="$dest.part" remote='' local_bytes=0
  install -d -m 0750 "$(dirname "$dest")"
  if [[ -s "$dest" ]]; then
    if validate_source_rpm "$dest" "$expected_nevr"; then
      printf 'Artifact: %s\nCache: HIT — %s\n' "$artifact" "$dest" >&2
      return 0
    fi
    printf 'Cache: INVALID — discarding failed integrity object %s\n' "$dest" >&2
    rm -f -- "$dest"
  fi
  remote="$(remote_content_length "$url" || true)"
  printf 'Artifact: %s\n' "$artifact" >&2
  if [[ ${GFX_VERBOSE:-0} == 1 ]]; then
    printf 'Expected identity: %s\nSource: %s\n' "$expected_nevr" "$url" >&2
  fi
  [[ -z "$remote" ]] || printf 'Size: ~%s\n' "$(human_bytes "$remote")" >&2
  printf 'Reason: %s\nCache: %s\n' "$reason" "$dest" >&2
  if [[ -s "$part" ]]; then
    local_bytes="$(stat -c '%s' "$part")"
    if [[ -n "$remote" ]]; then
      printf 'Cache status: PARTIAL — %s / %s available\nResuming download...\n' "$(human_bytes "$local_bytes")" "$(human_bytes "$remote")" >&2
    else
      printf 'Cache status: PARTIAL — %s available\nResuming download...\n' "$(human_bytes "$local_bytes")" >&2
    fi
  else
    printf 'Cache status: MISS\nDownloading...\n' >&2
  fi
  local download_rc
  set +e
  curl --fail --location --retry 3 --retry-all-errors --retry-delay 2 \
    --continue-at - --proto '=https' --tlsv1.2 --output "$part" "$url"
  download_rc=$?
  set -e
  if ((download_rc != 0)); then
    printf 'Download incomplete; resumable partial retained: %s\n' "$part" >&2
    ((download_rc == 130)) && return 130
    return 1
  fi
  if ! validate_source_rpm "$part" "$expected_nevr"; then
    rm -f -- "$part"
    printf 'Downloaded source RPM failed identity/signature validation and was discarded: %s\n' "$artifact" >&2
    return 1
  fi
  mv -f -- "$part" "$dest"
  printf 'Cache: VERIFIED — %s\n' "$dest" >&2
}

find_stock_module() {
  local kernel=$1 path
  command -v modinfo >/dev/null 2>&1 || return 1
  path="$(modinfo -k "$kernel" -n amdgpu 2>/dev/null || true)"
  if [[ -z "$path" && "$kernel" == "$(kernel_release)" ]]; then
    path="$(modinfo -n amdgpu 2>/dev/null || true)"
  fi
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
  local amd_root=$1 include_root=$2
  python3 - "$amd_root" "$include_root" <<'PY_TRACE'
import os
import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
include_root = Path(sys.argv[2]).resolve()
if not root.is_dir():
    raise SystemExit(f"AMD source root is missing: {root}")
if include_root == root or root in include_root.parents:
    raise SystemExit("external trace include namespace must be outside the AMD source root")

macro = re.compile(
    r"^(?P<prefix>\s*#\s*define\s+TRACE_INCLUDE_PATH\s+)"
    r"(?P<value>\S+)(?P<suffix>\s*)$"
)
in_tree = re.compile(
    r"^(?:\.\./)+(?P<target>drivers/gpu/drm/amd(?:/[A-Za-z0-9_.+-]+)*)$"
)
adapted: list[str] = []
unresolved: list[str] = []
candidates: list[tuple[Path, int, str, str, str]] = []
parents: set[Path] = set()

for path in sorted(root.rglob("*.h")):
    text = path.read_text(encoding="utf-8", errors="strict")
    for index, line in enumerate(text.splitlines(), 1):
        match = macro.match(line)
        if not match:
            if "TRACE_INCLUDE_PATH" in line and "drivers/gpu/drm/amd" in line and "../" in line:
                unresolved.append(f"{path}:{index}:unexpected TRACE_INCLUDE_PATH syntax: {line.strip()}")
            continue
        value = match.group("value")
        relative = in_tree.match(value)
        if not relative:
            if value.startswith("../") and "drivers/gpu/drm/amd" in value:
                unresolved.append(f"{path}:{index}:{value}")
            continue

        relative_parent = path.parent.relative_to(root)
        expected = "drivers/gpu/drm/amd"
        if relative_parent.parts:
            expected += "/" + relative_parent.as_posix()
        if relative.group("target") != expected:
            unresolved.append(
                f"{path}:{index}:{value} (expected target {expected})"
            )
            continue
        candidates.append((path, index, value, match.group("prefix"), match.group("suffix")))
        parents.add(path.parent.resolve())

if unresolved:
    raise SystemExit(
        "unresolved or unexpected in-tree AMD TRACE_INCLUDE_PATH values: "
        + "; ".join(sorted(set(unresolved)))
    )

# TRACE_INCLUDE_PATH is macro-expanded before being stringified by
# include/trace/define_trace.h.  Never put a real temporary/source path in the
# macro: components such as "linux" can themselves be predefined macros and
# hyphenated version directories are tokenized as operators.  Instead expose
# each source directory through a deterministic identifier-only alias and add
# include_root to the compiler's include search path.
shutil.rmtree(include_root, ignore_errors=True)
include_root.mkdir(parents=True, mode=0o750)
alias_for: dict[Path, str] = {}
for number, parent in enumerate(sorted(parents, key=str), 1):
    alias = f"_bc250_trace_{number:04d}"
    os.symlink(parent, include_root / alias, target_is_directory=True)
    alias_for[parent] = alias

by_path: dict[Path, list[tuple[int, str, str, str]]] = {}
for path, index, value, prefix, suffix in candidates:
    by_path.setdefault(path, []).append((index, value, prefix, suffix))

for path, entries in sorted(by_path.items(), key=lambda item: str(item[0])):
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines(keepends=True)
    for index, value, prefix, suffix in entries:
        original = lines[index - 1]
        newline = "\n" if original.endswith("\n") else ""
        alias = alias_for[path.parent.resolve()]
        lines[index - 1] = prefix + alias + suffix + newline
        adapted.append(f"{path}:{index}:{value}->{alias}")
    path.write_text("".join(lines), encoding="utf-8")

# Fail closed if any relative in-tree AMD trace path remains after the explicit
# transformations above.  The only accepted rewritten values are aliases that
# this invocation created beneath include_root.
valid_aliases = set(alias_for.values())
for path in sorted(root.rglob("*.h")):
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
        match = macro.match(line)
        if not match:
            if "TRACE_INCLUDE_PATH" in line and "drivers/gpu/drm/amd" in line and "../" in line:
                unresolved.append(f"{path}:{index}:unexpected TRACE_INCLUDE_PATH syntax: {line.strip()}")
            continue
        value = match.group("value")
        if value.startswith("../") and "drivers/gpu/drm/amd" in value:
            unresolved.append(f"{path}:{index}:{value}")
        if value.startswith("_bc250_trace_") and value not in valid_aliases:
            unresolved.append(f"{path}:{index}:unowned trace include alias: {value}")

if unresolved:
    raise SystemExit(
        "unresolved or unexpected in-tree AMD TRACE_INCLUDE_PATH values: "
        + "; ".join(sorted(set(unresolved)))
    )
if adapted:
    for item in adapted:
        print(f"adapted external TRACE_INCLUDE_PATH: {item}")
    print(f"external TRACE_INCLUDE_PATH namespace: {include_root}")
else:
    print("no relative in-tree AMD TRACE_INCLUDE_PATH values required adaptation")
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
  local build=$1 module=$2 work=$3 kernel=$4
  local symvers="$build/Module.symvers"
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

validate_built_module_identity() {
  local build=$1 module=$2 work=$3 kernel=$4 evidence=${5:-}
  local vermagic srcversion abi_sha abi_mode module_sha srcversion_state
  install -d -m 0700 "$work"
  vermagic="$(modinfo -F vermagic "$module" 2>/dev/null || true)"
  [[ "$vermagic" == "$kernel "* ]] || die "built amdgpu vermagic does not match exact target kernel ($vermagic)"
  abi_sha="$(verify_module_abi "$build" "$module" "$work" "$kernel")"
  [[ "$abi_sha" =~ ^[0-9a-f]{64}$ ]] || die "module ABI evidence digest is invalid"
  abi_mode="$(sed -n 's/^mode=//p' "$work/abi-required.txt" | head -1)"
  [[ "$abi_mode" =~ ^(modversions|symbol-resolution)$ ]] || die "module compatibility verification mode is invalid"
  module_sha="$(sha256sum "$module" | awk '{print $1}')"
  [[ "$module_sha" =~ ^[0-9a-f]{64}$ ]] || die "built amdgpu SHA-256 is invalid"
  srcversion="$(modinfo -F srcversion "$module" 2>/dev/null || true)"
  if [[ -n "$srcversion" ]]; then
    [[ "$srcversion" =~ ^[A-Za-z0-9]+$ ]] || die "built amdgpu srcversion metadata is malformed"
    srcversion_state="$srcversion"
  else
    srcversion_state=none
  fi
  if [[ -n "$evidence" ]]; then
    {
      printf 'target_kernel=%s\n' "$kernel"
      printf 'module_sha256=%s\n' "$module_sha"
      printf 'vermagic=%s\n' "$vermagic"
      printf 'abi_mode=%s\n' "$abi_mode"
      printf 'abi_sha256=%s\n' "$abi_sha"
      printf 'srcversion=%s\n' "$srcversion_state"
      printf 'srcversion_policy=supplemental\n'
    } > "$evidence"
    chmod 0600 "$evidence"
  fi
  printf '%s\n%s\n%s\n%s\n%s\n' "$module_sha" "$vermagic" "$abi_mode" "$abi_sha" "$srcversion_state"
}

first_meaningful_error_line() {
  local log=$1
  [[ -r "$log" ]] || return 1
  awk '
    BEGIN { IGNORECASE=1 }
    /fg: no job control/ || /command not found/ || /No such file or directory/ || /(^|[[:space:]])error:/ || /(^|[[:space:]])fatal:/ {
      line=$0
      sub(/^[+][[:space:]]*/, "", line)
      print line
      exit
    }
  ' "$log"
}

classify_prepare_log_failure() {
  local stage=$1 log=$2 first=''
  if [[ "$stage" == *'Fedora kernel %prep'* ]] && \
     grep -Fq '%py3_shebang_fix' "$log" 2>/dev/null && \
     grep -Fq 'fg: no job control' "$log" 2>/dev/null; then
    printf 'required RPM macro unavailable: py3_shebang_fix\n'
    return 0
  fi
  first="$(first_meaningful_error_line "$log" 2>/dev/null || true)"
  if [[ -n "$first" ]]; then
    printf 'unclassified — %s\n' "$first"
  else
    printf 'unclassified — see evidence\n'
  fi
}

prepare_stage_display() {
  local stage=${1:-unclassified}
  stage="$(sed -E 's/^\[[0-9]+\/7\][[:space:]]+//' <<<"$stage")"
  stage="${stage#Run }"
  printf '%s\n' "$stage"
}

format_elapsed() {
  local total=$1
  printf '%02d:%02d' "$((total / 60))" "$((total % 60))"
}

prepare_stage() {
  local index=$1 label=$2
  local marker="[$index/7] $label"
  PREPARE_STAGE="$marker"
  if [[ ${PREPARE_LAST_STAGE_PRINTED:-} != "$marker" ]]; then
    printf '%s\n' "$marker" >&2
    PREPARE_LAST_STAGE_PRINTED="$marker"
  fi
}

gfx_build_progress() {
  [[ ${BC250_GFX1013_BUILD_PROGRESS:-1} == 1 ]] || return 0
  local prefix="${PREPARE_STAGE:-[GFX1013 build]}"
  printf '%s — %s\n' "$prefix" "$*" >&2
}

stop_active_phase() {
  local pid=${ACTIVE_PHASE_PID:-}
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 0
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    local deadline=$((SECONDS + 5))
    while kill -0 "$pid" 2>/dev/null && ((SECONDS < deadline)); do sleep 1; done
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
  ACTIVE_PHASE_PID=''
}

run_kernel_logged_phase() {
  local label=$1 log=$2 mode=$3
  shift 3
  local interval="${BC250_GFX1013_HEARTBEAT_SECONDS:-60}" pid rc=0 started=$SECONDS next_heartbeat elapsed
  [[ "$interval" =~ ^[1-9][0-9]*$ ]] || die "BC250_GFX1013_HEARTBEAT_SECONDS must be a positive integer"
  gfx_build_progress "$label started"
  if [[ "$mode" == append ]]; then
    setsid --wait "$@" >>"$log" 2>&1 &
  elif [[ "$mode" == truncate ]]; then
    setsid --wait "$@" >"$log" 2>&1 &
  else
    die "invalid logged phase mode: $mode"
  fi
  pid=$!
  ACTIVE_PHASE_PID=$pid
  next_heartbeat=$((SECONDS + interval))
  while kill -0 "$pid" 2>/dev/null; do
    sleep 2
    if (( SECONDS >= next_heartbeat )) && kill -0 "$pid" 2>/dev/null; then
      elapsed="$(format_elapsed "$((SECONDS - started))")"
      gfx_build_progress "$label — still running, $elapsed elapsed"
      next_heartbeat=$((SECONDS + interval))
    fi
  done
  if wait "$pid"; then rc=0; else rc=$?; fi
  ACTIVE_PHASE_PID=''
  elapsed="$(format_elapsed "$((SECONDS - started))")"
  if ((rc == 0)); then
    gfx_build_progress "$label completed, $elapsed elapsed"
  else
    gfx_build_progress "$label failed after $elapsed (rc=$rc)"
  fi
  return "$rc"
}

kernel_build_jobs() {
  local detected requested
  detected="$(nproc)"
  requested="${BC250_GFX1013_BUILD_JOBS:-}"
  if [[ -n "$requested" ]]; then
    [[ "$requested" =~ ^[1-9][0-9]*$ ]] || die "BC250_GFX1013_BUILD_JOBS must be a positive integer"
    ((requested <= 64)) || die "BC250_GFX1013_BUILD_JOBS must not exceed 64"
    printf '%s\n' "$requested"
    return 0
  fi
  ((detected < 1)) && detected=1
  printf '%s\n' "$detected"
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
  prepare_stage 2 'Run Fedora kernel %prep'
  if ! run_kernel_logged_phase "Fedora kernel %prep" "$work/kernel-prep.log" truncate \
      rpmbuild -bp --nodeps --define "_topdir $rpm_top" "$rpm_top/SPECS/kernel.spec"; then
    PREPARE_FAILURE_REASON="$(classify_prepare_log_failure "$PREPARE_STAGE" "$work/kernel-prep.log")"
    die "Fedora kernel %prep failed; see $work/kernel-prep.log"
  fi

  PREPARE_STAGE='[2/7] Run Fedora kernel %prep / source provenance'
  run_kernel_logged_phase "kernel source provenance" "$work/kernel-build.log" append \
    python3 "$SOURCE/check-kernel-provenance.py" \
      --prepared-build-root "$rpm_top/BUILD" \
      --patch-dir "$SOURCE/patches/kernel/v33" \
      --root-output "$prepared_out" \
      --output "$work/kernel-source-provenance.txt" || \
    die "Fedora-prepared kernel source-provenance check failed; see $work/kernel-build.log"
}

build_kernel_module() {
  local kernel=$1 build=$2 work=$3 artifact=$4 stock_module=$5
  local version release srpm_url srpm expected_vr actual_vr source_package source_root prepared_file linux_root patch_file raw trace_include_root jobs
  version="${kernel%%-*}"
  release="${kernel#*-}"; release="${release%.*}"
  srpm_url="${BC250_GFX1013_KERNEL_SRPM_URL:-https://kojipkgs.fedoraproject.org/packages/kernel/${version}/${release}/src/kernel-${version}-${release}.src.rpm}"
  srpm="$CACHE_ROOT/kernel-${version}-${release}.src.rpm"
  expected_vr="${kernel%.*}"
  prepare_stage 1 'Acquire Fedora kernel source'
  fetch_verified_srpm "$srpm_url" "$srpm" "kernel-$expected_vr" \
    "kernel-${version}-${release}.src.rpm" "exact-kernel GFX1013 amdgpu build" || {
      local fetch_rc=$?; ((fetch_rc == 130)) && exit 130
      die "exact Fedora kernel source download/validation failed; rerun prepare to resume"
    }
  actual_vr="$(rpm -qp --qf '%{VERSION}-%{RELEASE}\n' "$srpm" 2>/dev/null || true)"
  source_package="$(rpm -qp --qf '%{SOURCEPACKAGE}\n' "$srpm" 2>/dev/null || true)"
  [[ "$actual_vr" == "$expected_vr" ]] || die "kernel source RPM identity mismatch: expected $expected_vr, got ${actual_vr:-unreadable}"
  [[ "$source_package" == 1 ]] || die "kernel package is not marked as a source RPM"

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

  prepare_stage 3 'Apply GFX1013 kernel patches'
  trace_include_root="$work/trace-include"
  gfx_build_progress "external trace adaptation started"
  adapt_external_amd_trace_paths "$linux_root/drivers/gpu/drm/amd" "$trace_include_root" >>"$work/kernel-build.log" 2>&1 || \
    die "AMD external-module trace-path adaptation failed; see $work/kernel-build.log"
  gfx_build_progress "external trace adaptation completed"
  gfx_build_progress "GFX1013 kernel patch application started"
  for patch_file in "$SOURCE"/patches/kernel/v33/*.patch; do
    apply_patch_checked "$linux_root" "$patch_file"
  done
  gfx_build_progress "GFX1013 kernel patch application completed"
  prepare_stage 4 'Build and validate patched amdgpu'
  jobs="$(kernel_build_jobs)"
  gfx_build_progress "amdgpu external-module build configured with jobs=$jobs"
  run_kernel_logged_phase "amdgpu external-module build" "$work/kernel-build.log" append \
    make -C "$build" "M=$linux_root/drivers/gpu/drm/amd/amdgpu" "KCFLAGS=-I$trace_include_root" modules "-j$jobs" || \
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
  (cd "$rpm_top/SOURCES" && rpm2cpio "$srpm" | cpio -id --quiet) || \
    die "cannot extract exact Fedora Mesa source RPM"
  local -a specs=()
  if [[ -f "$rpm_top/SOURCES/mesa.spec" ]]; then
    spec="$rpm_top/SOURCES/mesa.spec"
  else
    mapfile -t specs < <(find "$rpm_top/SOURCES" -maxdepth 1 -type f -name 'mesa*.spec' -print | sort)
    ((${#specs[@]} == 1)) || die "Mesa source RPM must contain mesa.spec or exactly one mesa*.spec candidate"
    spec="${specs[0]}"
  fi
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
  run_kernel_logged_phase "Fedora Mesa %prep" "$work/mesa-prep.log" truncate \
    rpmbuild -bp --nodeps --define "_topdir $rpm_top" "$rpm_top/SPECS/mesa.spec" || \
    die "Fedora Mesa %prep failed; see $work/mesa-prep.log"
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
  prepare_stage 5 'Acquire/prepare Fedora Mesa source'
  fetch_verified_srpm "$MESA_SRPM_URL" "$srpm" "${MESA_SRPM_NEVRA%.src}" \
    "mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm" "private headless RADV build" || {
      local fetch_rc=$?; ((fetch_rc == 130)) && exit 130
      die "exact Fedora Mesa source download/validation failed; rerun prepare to resume"
    }
  prepare_fedora_mesa_source "$work" "$srpm" "$prepared_file" "$source0_file"
  mesa_src="$(<"$prepared_file")"; source0="$(<"$source0_file")"
  [[ -d "$mesa_src" ]] || die "Fedora-prepared Mesa source root is missing"
  rm -rf "$stage"; install -d -m 0750 "$stage"
  while IFS= read -r patch_name; do
    [[ -z "$patch_name" || "$patch_name" == \#* ]] && continue
    apply_patch_checked "$mesa_src" "$SOURCE/patches/mesa/$patch_name"
  done < "$SOURCE/patches/mesa/series"
  prepare_stage 6 'Build and validate private RADV'
  run_kernel_logged_phase "Mesa headless setup" "$work/mesa-setup.log" truncate \
    meson setup "$work/mesa-build" "$mesa_src" \
      --wrap-mode=nodownload \
      -Dvulkan-drivers=amd -Dgallium-drivers=[] -Dplatforms=[] \
      -Dglx=disabled -Degl=disabled -Dgbm=disabled \
      -Dgles1=disabled -Dgles2=disabled -Dopengl=false \
      -Dllvm=disabled -Dvideo-codecs=[] -Ddisplay-info=disabled \
      -Dvulkan-layers=[] -Dtools=[] \
      -Dprefix="$(private_prefix)" -Dlibdir=lib64 -Dbuildtype=release || \
    die "Mesa headless setup failed; see $work/mesa-setup.log"
  run_kernel_logged_phase "Mesa headless RADV build" "$work/mesa-build.log" truncate \
    ninja -C "$work/mesa-build" || die "Mesa headless RADV build failed; see $work/mesa-build.log"

  local install_stage="$work/mesa-install" installed_prefix
  rm -rf "$install_stage"
  install -d -m 0750 "$install_stage"
  run_kernel_logged_phase "Mesa staging install" "$work/mesa-build.log" append \
    env DESTDIR="$install_stage" ninja -C "$work/mesa-build" install || die "Mesa staging install failed"
  installed_prefix="$install_stage$(private_prefix)"
  [[ -f "$installed_prefix/lib64/libvulkan_radeon.so" ]] || die "private RADV library missing from staged Mesa"
  [[ -f "$installed_prefix/share/vulkan/icd.d/radeon_icd.x86_64.json" ]] || die "private RADV ICD missing from staged Mesa"

  # Keep the deployed private runtime intentionally tiny: RADV plus its ICD only.
  # Internal Mesa build products are statically linked into RADV; any unexpected
  # GUI/window-system linkage is rejected below before lifecycle commit.
  rm -rf "$stage"
  install -D -m 0755 "$installed_prefix/lib64/libvulkan_radeon.so" "$stage$(private_radv_lib)"
  install -D -m 0644 "$installed_prefix/share/vulkan/icd.d/radeon_icd.x86_64.json" "$stage$(private_icd)"
  # Make staging identical to the deployable runtime before CI/audit. The ICD
  # must point at the final package-private RADV path, never at a system driver.
  pin_private_icd_library "$stage$(private_icd)" "$(private_radv_lib)"
  verify_headless_radv_stage "$stage" "$work/mesa-radv-needed.txt"
  printf '%s\n%s\n' "$srpm" "$source0" > "$info_file"
}

verify_headless_radv_stage() {
  local stage=$1 evidence=$2 root library relative dynamic
  local -a payload=() needed=() forbidden=()
  root="$stage$(private_prefix)"
  library="$stage$(private_radv_lib)"
  [[ -d "$root" && -f "$library" && -f "$stage$(private_icd)" ]] || \
    die "headless private RADV stage is incomplete"
  private_icd_library_ok "$stage$(private_icd)" "$(private_radv_lib)" || \
    die "headless private RADV ICD does not point at the final package-private library"

  mapfile -t payload < <(find "$root" \( -type f -o -type l \) -printf '%P\n' | sort)
  ((${#payload[@]} == 2)) || die "headless private RADV stage contains unexpected files: ${payload[*]:-<none>}"
  [[ "${payload[0]}" == lib64/libvulkan_radeon.so ]] || die "headless private RADV payload is missing the canonical RADV library"
  [[ "${payload[1]}" == share/vulkan/icd.d/radeon_icd.x86_64.json ]] || die "headless private RADV payload is missing the canonical ICD manifest"

  dynamic="${evidence%.txt}-dynamic.txt"
  readelf -d "$library" > "$dynamic" || die "cannot inspect private RADV ELF dependencies"
  mapfile -t needed < <(sed -n 's/.*Shared library: \[\([^]]*\)\].*/\1/p' "$dynamic" | sort -u)
  ((${#needed[@]})) || die "private RADV dependency audit found no ELF NEEDED entries"
  printf '%s\n' "${needed[@]}" > "$evidence"
  for relative in "${needed[@]}"; do
    case "$relative" in
      libX11.so*|libX11-xcb.so*|libXext.so*|libXfixes.so*|libXrandr.so*|libxcb.so*|libxcb-*.so*|libwayland-client.so*|libwayland-egl.so*|libxshmfence.so*|libdisplay-info.so*|libEGL.so*|libGL.so*|libGLES*.so*|libgbm.so*)
        forbidden+=("$relative")
        ;;
    esac
  done
  ((${#forbidden[@]} == 0)) || die "headless private RADV unexpectedly links GUI/WSI libraries: ${forbidden[*]}"
  if grep -Eq '\((RPATH|RUNPATH)\)' "$dynamic"; then
    die "headless private RADV must not carry RPATH/RUNPATH"
  fi
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
  if ! (
    unset DISPLAY WAYLAND_DISPLAY XDG_SESSION_TYPE
    VK_DRIVER_FILES="$icd" vulkaninfo --summary
  ) >"$summary" 2>&1; then
    rm -f "$summary"
    die "private headless RADV failed Vulkan loader smoke check without X11/Wayland session variables"
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


verify_private_radv_compute_queue() {
  local icd=$1 output queue
  output="$(mktemp)"
  if ! (
    unset DISPLAY WAYLAND_DISPLAY XDG_SESSION_TYPE
    VK_DRIVER_FILES="$icd" vulkaninfo
  ) >"$output" 2>&1; then
    rm -f "$output"
    die "private RADV full Vulkan capability query failed"
  fi
  queue="$(python3 - "$output" <<'PY_QUEUE'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
blocks = re.split(r"(?m)(?=^GPU\d+:)", text)
for block in blocks:
    vendor = re.search(r"vendorID\s*=\s*(0x[0-9a-fA-F]+)", block)
    device = re.search(r"deviceID\s*=\s*(0x[0-9a-fA-F]+)", block)
    if not vendor or not device:
        continue
    if vendor.group(1).lower() != "0x1002" or device.group(1).lower() != "0x13fe":
        continue
    current = None
    flags = ""
    for line in block.splitlines():
        match = re.search(r"queueProperties\[(\d+)\]", line)
        if match:
            if current is not None and "QUEUE_COMPUTE_BIT" in flags and "QUEUE_GRAPHICS_BIT" not in flags:
                print(current)
                raise SystemExit(0)
            current = match.group(1)
            flags = ""
            continue
        if current is not None and "queueFlags" in line:
            flags = line
    if current is not None and "QUEUE_COMPUTE_BIT" in flags and "QUEUE_GRAPHICS_BIT" not in flags:
        print(current)
        raise SystemExit(0)
raise SystemExit(1)
PY_QUEUE
  )" || { rm -f "$output"; die "private RADV exposes BC-250 but no dedicated compute-only Vulkan queue family"; }
  rm -f "$output"
  [[ "$queue" =~ ^[0-9]+$ ]] || die "private RADV compute queue evidence is malformed"
  printf '%s\n' "$queue"
}

GFX_MODULE_ATTESTATION_REASON=''
loaded_amdgpu_identity_ok() {
  local loaded=''
  GFX_MODULE_ATTESTATION_REASON=''
  patched_boot_running || { GFX_MODULE_ATTESTATION_REASON='current boot lacks the package-owned patched marker'; return 1; }
  [[ -f "${BC250_GFX1013_PATCHED_BLS:-}" && -f "${BC250_GFX1013_PATCHED_INITRAMFS:-}" ]] || {
    GFX_MODULE_ATTESTATION_REASON='patched boot artifacts are missing'; return 1;
  }
  [[ "${BC250_GFX1013_PATCHED_BLS_SHA256:-}" =~ ^[0-9a-f]{64}$ && "${BC250_GFX1013_PATCHED_INITRAMFS_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || {
    GFX_MODULE_ATTESTATION_REASON='patched boot-chain hashes are unavailable'; return 1;
  }
  [[ "$(sha256sum "$BC250_GFX1013_PATCHED_BLS" | awk '{print $1}')" == "$BC250_GFX1013_PATCHED_BLS_SHA256" ]] || {
    GFX_MODULE_ATTESTATION_REASON='patched BLS identity changed after staging'; return 1;
  }
  [[ "$(sha256sum "$BC250_GFX1013_PATCHED_INITRAMFS" | awk '{print $1}')" == "$BC250_GFX1013_PATCHED_INITRAMFS_SHA256" ]] || {
    GFX_MODULE_ATTESTATION_REASON='patched initramfs identity changed after staging'; return 1;
  }
  if [[ "${BC250_GFX1013_MODULE_SRCVERSION:-none}" != none ]]; then
    [[ -r /sys/module/amdgpu/srcversion ]] || {
      GFX_MODULE_ATTESTATION_REASON='built module carried srcversion but loaded amdgpu srcversion is unavailable'; return 1;
    }
    loaded="$(tr -d '\n' < /sys/module/amdgpu/srcversion)"
    [[ "$loaded" == "$BC250_GFX1013_MODULE_SRCVERSION" ]] || {
      GFX_MODULE_ATTESTATION_REASON='loaded amdgpu srcversion differs from prepared module'; return 1;
    }
  fi
  return 0
}

verify_loaded_amdgpu_identity() {
  loaded_amdgpu_identity_ok || die "loaded patched amdgpu attestation failed: $GFX_MODULE_ATTESTATION_REASON"
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
PREPARE_LAST_STAGE_PRINTED=''
PREPARE_FAILURE_REASON=''

stage_patched_boot() {
  local kernel=$1 prepared=$2 module_payload=$3 stock_module=$4 stock_bls=$5 work=$6 info_file=$7
  local evidence stock_initramfs machine patched_bls patched_id patched_initramfs verify_root embedded
  local stock_hash initramfs_hash payload_hash saved_before next_before staging_entry patched_bls_hash patched_initramfs_hash
  local stock_modules_root stock_module_real stock_rel kmod_stage_root kmod_stage staged_module
  evidence="$prepared/boot-evidence"
  stock_initramfs="${BC250_GFX1013_BOOT_ROOT:-/boot}/initramfs-${kernel}.img"
  [[ -f "$stock_initramfs" ]] || die "stock initramfs missing: $stock_initramfs"
  machine="$(< "${BC250_GFX1013_MACHINE_ID_FILE:-/etc/machine-id}")"
  patched_id="${machine}-${kernel}-${PROFILE_VARIANT}"
  patched_bls="${BC250_GFX1013_BOOT_ROOT:-/boot}/loader/entries/${patched_id}.conf"
  patched_initramfs="${BC250_GFX1013_BOOT_ROOT:-/boot}/initramfs-${kernel}-${PROFILE_VARIANT}.img"
  [[ ! -e "$patched_bls" && ! -e "$patched_initramfs" ]] || die "stale GFX1013 boot artifacts exist; run disable/reset before stage-boot"

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
  # dracut --kmoddir validates that the exact kernel module directory lives
  # below a literal lib/modules parent. Keep the whole tree private while
  # conforming to that filesystem contract.
  kmod_stage_root="$work/kmod"
  kmod_stage="$kmod_stage_root/lib/modules/$kernel"
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
  rm -rf -- "$work/kmod"

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
  patched_bls_hash="$(sha256sum "$patched_bls" | awk '{print $1}')"
  patched_initramfs_hash="$(sha256sum "$patched_initramfs" | awk '{print $1}')"

  printf '%s\n' "$patched_bls" "$patched_id" "$patched_initramfs" "$stock_initramfs" "$saved_before" "$next_before" "$stock_hash" "$initramfs_hash" "$patched_bls_hash" "$patched_initramfs_hash" > "$info_file"
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
  local patched_id=$1 saved_before=$2 previous_next=${3:-}
  if ! grub2-editenv - set "next_entry=$patched_id"; then
    return 1
  fi
  if [[ "$(grub_value next_entry)" != "$patched_id" || "$(grub_value saved_entry)" != "$saved_before" ]]; then
    restore_previous_next "$previous_next" >/dev/null 2>&1 || true
    return 1
  fi
  return 0
}

rotate_prepare_evidence() {
  local root="$STATE_ROOT/prepare-evidence" path
  local -a entries=()
  [[ -d "$root" ]] || return 0
  mapfile -t entries < <(find "$root" -mindepth 1 -maxdepth 1 -type d \( -name 'failure-*' -o -name 'interruption-*' \) -print | sort -r)
  if ((${#entries[@]} > 5)); then
    for path in "${entries[@]:5}"; do
      rm -rf -- "$path" "$path.tar.gz"
    done
  fi
}

capture_module_identity_evidence() {
  local module=$1 label=$2 output=$3 raw
  raw="$output.${label}.ko"
  [[ -f "$module" && ! -L "$module" ]] || return 0
  {
    printf 'label=%s\n' "$label"
    printf 'path=%s\n' "$module"
    sha256sum "$module" 2>/dev/null || true
    echo '--- modinfo ---'
    modinfo "$module" 2>&1 || true
    echo '--- readelf -n ---'
  } > "$output"
  case "$module" in
    *.ko) cp -p "$module" "$raw" 2>/dev/null || true ;;
    *.ko.xz) xz -dc "$module" > "$raw" 2>/dev/null || true ;;
    *.ko.zst) zstd -q -dc "$module" > "$raw" 2>/dev/null || true ;;
    *.ko.gz) gzip -dc "$module" > "$raw" 2>/dev/null || true ;;
  esac
  if [[ -s "$raw" ]]; then
    readelf -n "$raw" >> "$output" 2>&1 || true
    rm -f -- "$raw"
  else
    echo 'readelf unavailable: module could not be materialized' >> "$output"
  fi
  chmod 0600 "$output" 2>/dev/null || true
}

PREPARE_EVIDENCE_PATH=''
PREPARE_EVIDENCE_DIR=''
preserve_prepare_evidence() {
  local rc=$1 kind=$2 timestamp dest archive log package_id reason
  [[ -n "$PREPARE_DIR" && -d "$PREPARE_DIR" ]] || return 0
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dest="$STATE_ROOT/prepare-evidence/${kind}-${timestamp}-$$"
  archive="$dest.tar.gz"
  install -d -m 0700 "$dest"
  package_id="$(package_nevra)"
  reason="${PREPARE_FAILURE_REASON:-unclassified — see evidence}"
  [[ "$kind" == interruption ]] && reason='operator interruption'
  {
    printf 'classification=%s\n' "$kind"
    printf 'stage=%s\n' "$(prepare_stage_display "$PREPARE_STAGE")"
    printf 'stage_raw=%q\n' "$PREPARE_STAGE"
    printf 'exit_rc=%s\n' "$rc"
    printf 'reason=%q\n' "$reason"
    printf 'package_nevra=%s\n' "${package_id:-unavailable}"
    printf 'kernel=%s\n' "$(kernel_release)"
    printf 'profile=%s\n' "$PACKAGE_PROFILE"
    printf 'upstream_version=%s\n' "$UPSTREAM_VERSION"
    printf 'upstream_commit=%s\n' "$PINNED_COMMIT"
    printf 'mesa_fedora_srpm=%s\n' "$MESA_SRPM_NEVRA"
    printf 'mesa_source0_sha256=%s\n' "$MESA_SOURCE0_SHA256"
    printf 'cache_root=%s\n' "$CACHE_ROOT"
  } > "$dest/result.env"
  chmod 0600 "$dest/result.env"
  for log in kernel-srpm-members.txt kernel-prep.log kernel-source-provenance.txt kernel-build.log module-identity.txt mesa-prep.log mesa-setup.log mesa-build.log mesa-radv-needed.txt mesa-radv-needed-dynamic.txt; do
    if [[ -f "$PREPARE_DIR/work/$log" && ! -L "$PREPARE_DIR/work/$log" ]]; then
      install -m 0600 "$PREPARE_DIR/work/$log" "$dest/$log"
    fi
  done
  local built_module stock_module
  built_module="$(find "$PREPARE_DIR" -maxdepth 1 -type f -name 'amdgpu.ko*' -print -quit 2>/dev/null || true)"
  stock_module="$(find_stock_module "$(kernel_release)" 2>/dev/null || true)"
  [[ -z "$built_module" ]] || capture_module_identity_evidence "$built_module" built "$dest/module-identity-built.txt"
  [[ -z "$stock_module" ]] || capture_module_identity_evidence "$stock_module" stock "$dest/module-identity-stock.txt"
  if [[ -r "/boot/config-$(kernel_release)" ]]; then
    grep -E '^(CONFIG_MODULE_SRCVERSION_ALL=|# CONFIG_MODULE_SRCVERSION_ALL is not set)' "/boot/config-$(kernel_release)" > "$dest/kernel-srcversion-config.txt" || true
    chmod 0600 "$dest/kernel-srcversion-config.txt" 2>/dev/null || true
  fi
  tar -C "$(dirname "$dest")" -czf "$archive.tmp" "$(basename "$dest")"
  gzip -t "$archive.tmp"
  tar -tzf "$archive.tmp" >/dev/null
  chmod 0600 "$archive.tmp"
  mv -f -- "$archive.tmp" "$archive"
  PREPARE_EVIDENCE_DIR="$dest"
  PREPARE_EVIDENCE_PATH="$archive"
  rotate_prepare_evidence
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

set_staged_boot_identity() {
  local bls_sha=$1 initramfs_sha=$2 tmp="$ACTIVE_STATE.tmp"
  [[ "$bls_sha" =~ ^[0-9a-f]{64}$ && "$initramfs_sha" =~ ^[0-9a-f]{64}$ ]] || return 1
  awk '!/^BC250_GFX1013_PATCHED_BLS_SHA256=/ && !/^BC250_GFX1013_PATCHED_INITRAMFS_SHA256=/' "$ACTIVE_STATE" > "$tmp" || return 1
  {
    printf 'BC250_GFX1013_PATCHED_BLS_SHA256=%s\n' "$bls_sha"
    printf 'BC250_GFX1013_PATCHED_INITRAMFS_SHA256=%s\n' "$initramfs_sha"
  } >> "$tmp"
  chmod 0600 "$tmp" || return 1
  mv -f "$tmp" "$ACTIVE_STATE"
}

mark_prepare_safety_failure() {
  set_active_transaction_state SAFETY_FAILURE 1 "$1"
}

prepare_cleanup_on_exit() {
  local rc=$1 kind=failure
  trap - EXIT INT TERM
  stop_active_phase
  if [[ "$PREPARE_COMMITTED" != 1 ]]; then
    ((rc == 130)) && kind=interruption
    preserve_prepare_evidence "$rc" "$kind" || true

    [[ -z "$PREPARE_PATCHED_BLS" ]] || rm -f -- "$PREPARE_PATCHED_BLS"
    [[ -z "$PREPARE_PATCHED_INITRAMFS" ]] || rm -f -- "$PREPARE_PATCHED_INITRAMFS"
    [[ -z "$PREPARE_PRIVATE_PREFIX" ]] || rm -rf -- "$PREPARE_PRIVATE_PREFIX"
    rm -f -- "$ACTIVE_STATE"
    [[ -z "$PREPARE_FINAL_DIR" ]] || rm -rf -- "$PREPARE_FINAL_DIR"
    [[ -z "$PREPARE_DIR" ]] || rm -rf -- "$PREPARE_DIR"
    rmdir "$STATE_ROOT/prepared" 2>/dev/null || true

    if ((rc == 130)); then
      echo "GFX1013 prepare interrupted by operator." >&2
      echo "Exit status: 130" >&2
      [[ -z "$PREPARE_EVIDENCE_PATH" ]] || echo "Partial download/build evidence preserved: $PREPARE_EVIDENCE_PATH" >&2
      echo "No prepared profile was committed." >&2
      echo "Boot state changed: no" >&2
      echo "Runtime/service state changed: no" >&2
      echo "Reusable source cache preserved: $CACHE_ROOT" >&2
      echo "Rerun 'sudo bc250 gfx1013 prepare' to resume." >&2
    else
      echo >&2
      echo "Result: FAILED" >&2
      echo "Stage: $(prepare_stage_display "$PREPARE_STAGE")" >&2
      echo "Cause: ${PREPARE_FAILURE_REASON:-unclassified — see evidence}" >&2
      [[ -z "$PREPARE_EVIDENCE_PATH" ]] || echo "Evidence: $PREPARE_EVIDENCE_PATH" >&2
      echo "Boot state changed: no" >&2
      echo "Runtime/service state changed: no" >&2
      echo "Source cache preserved: yes ($CACHE_ROOT)" >&2
    fi
  fi
  exit "$rc"
}

prepare_preflight() {
  local verbose=${1:-0}
  local failures=0 host_tooling_blocked=0 kernel build build_owner stock_module stock_bls stock_entry_id current_saved
  local secure package_id command os_id='' machine_id preflight_bls preflight_initramfs
  local source_detail='' payload_detail='' dependency_blocked=0 source_prefetch_recommended=0 preflight_primary_action=''
  local version release kernel_srpm_url kernel_srpm
  local -a missing_commands=() missing_requirements=() remediation=()

  echo "GFX1013 prepare preflight (read-only):"
  if [[ -r "$OS_RELEASE_FILE" ]]; then
    # shellcheck disable=SC1090
    . "$OS_RELEASE_FILE"
    os_id="${ID:-}"
  fi
  if [[ "$os_id" == fedora ]]; then
    ((verbose)) && echo "  Fedora host: PASS"
  else
    echo "  Fedora host: BLOCKED (${os_id:-unknown})"
    host_tooling_blocked=1
    failures=$((failures + 1))
    remediation+=("Host: use a supported Fedora 44 installation")
  fi
  if command -v rpm-ostree >/dev/null 2>&1; then
    echo "  Atomic/rpm-ostree host: BLOCKED (unsupported by direct exact-kernel profile)"
    host_tooling_blocked=1
    failures=$((failures + 1))
    remediation+=("Host mode: use a traditional RPM-managed Fedora installation for GFX1013 prepare")
  else
    ((verbose)) && echo "  Atomic/rpm-ostree host: PASS (not detected)"
  fi

  for command in curl xz zstd gzip bzip2 tar cpio patch gcc g++ make cargo rpm rpm2cpio rpmbuild meson ninja python3 nm readelf vulkaninfo \
    sha256sum modinfo modprobe depmod dracut lsinitrd grub2-editenv grub2-set-default flock setsid awk sed grep find install; do
    command -v "$command" >/dev/null 2>&1 || missing_commands+=("$command")
  done
  if ((${#missing_commands[@]})); then
    printf '  Required commands: BLOCKED (missing: %s)\n' "${missing_commands[*]}"
    host_tooling_blocked=1
    dependency_blocked=1
    failures=$((failures + 1))
    remediation+=("Tooling: install packages providing the missing required commands: ${missing_commands[*]}")
  else
    ((verbose)) && echo "  Required commands: PASS"
  fi
  if ! command -v dracut >/dev/null 2>&1; then
    echo "  Isolated dracut module tree: NOT CHECKED — required command dracut unavailable"
  elif dracut --help 2>&1 | grep -q -- '--kmoddir'; then
    ((verbose)) && echo "  Isolated dracut module tree: PASS (--kmoddir supported)"
  else
    echo "  Isolated dracut module tree: BLOCKED (--kmoddir unavailable)"
    host_tooling_blocked=1
    failures=$((failures + 1))
    remediation+=("Dracut: install/use a dracut build with --kmoddir support")
  fi
  if (( ! verbose )); then
    if ((host_tooling_blocked)); then
      echo "  Host / tooling: BLOCKED"
    else
      echo "  Host / tooling: PASS"
    fi
  fi

  if ! check_build_requirements "$verbose"; then
    missing_requirements=("${GFX_MISSING_BUILD_REQUIREMENTS[@]}")
    dependency_blocked=1
    failures=$((failures + 1))
    if ((${#missing_requirements[@]})); then
      remediation+=("Build dependencies: $(print_requirement_install_command "${missing_requirements[@]}")")
    else
      remediation+=("Build dependencies: install the packages that provide the missing requirements")
    fi
  fi

  secure="$(secure_boot_state)"
  case "$secure" in
    disabled|disabled-non-efi|disabled-unsupported) ((verbose)) && echo "  Secure Boot: PASS ($secure)" ;;
    enabled)
      echo "  Secure Boot: BLOCKED (unsigned package-built amdgpu is not enrolled)"
      failures=$((failures + 1))
      remediation+=("Secure Boot: use the supported disabled-Secure-Boot GFX1013 path; this profile does not enroll or synthesize module signatures")
      ;;
    *)
      echo "  Secure Boot: BLOCKED (state unknown)"
      failures=$((failures + 1))
      remediation+=("Secure Boot: establish a readable disabled Secure Boot state before continuing")
      ;;
  esac

  if source_identity_ok; then
    echo "  Carried source integrity: PASS"
  else
    source_detail="$(source_integrity_detail 2>/dev/null || true)"
    echo "  Carried source integrity: BLOCKED"
    [[ -z "$source_detail" ]] || echo "    $source_detail"
    echo "    action: reinstall/rebuild the matching package"
    failures=$((failures + 1))
    remediation+=("Carried source: reinstall/rebuild the matching bc250-llm-server package")
  fi
  if ! command -v rpm >/dev/null 2>&1; then
    echo "  Installed RPM payload integrity: NOT CHECKED — required command rpm unavailable"
  elif payload_detail="$(installed_payload_integrity_detail)"; then
    echo "  Installed RPM payload integrity: PASS"
  else
    echo "  Installed RPM payload integrity: BLOCKED"
    echo "    ${payload_detail:-RPM verification failed}"
    echo "    action: reinstall/rebuild the matching package"
    failures=$((failures + 1))
    remediation+=("Installed RPM payload: reinstall/rebuild the matching bc250-llm-server package")
  fi
  if bc250_device_present; then
    ((verbose)) && echo "  BC-250 PCI 1002:13fe: PASS"
  else
    echo "  BC-250 PCI 1002:13fe: BLOCKED (not found)"
    failures=$((failures + 1))
    remediation+=("Device: run experimental GFX1013 preparation on a BC-250 device exposing PCI 1002:13fe")
  fi

  if ! prepare_runtime_ready; then
    echo "  Running boot prerequisite: BLOCKED ($PREPARE_RUNTIME_BLOCK_REASON)"
    failures=$((failures + 1))
    remediation+=("Running boot: $PREPARE_RUNTIME_BLOCK_REASON; $PREPARE_RUNTIME_NEXT_ACTION")
    preflight_primary_action="$PREPARE_RUNTIME_NEXT_ACTION"
  elif [[ -e "$ACTIVE_STATE" ]]; then
    echo "  Existing lifecycle state: BLOCKED (disable/reset first)"
    failures=$((failures + 1))
    remediation+=("Lifecycle state: run sudo bc250 gfx1013 disable or sudo bc250 gfx1013 reset --check as appropriate, then restore stock state")
  fi
  if [[ -e "$DROPIN" ]]; then
    echo "  Ollama private-RADV override: BLOCKED (unexpected pre-existing drop-in)"
    failures=$((failures + 1))
    remediation+=("Ollama override: restore package stock/default-off state with the GFX1013 disable/reset workflow")
  fi
  if [[ -e "$UPSTREAM_GENERATOR" || -e "$UPSTREAM_STATE/active.env" ]]; then
    echo "  Separate upstream GFX1013 state: BLOCKED (conflict detected)"
    failures=$((failures + 1))
    remediation+=("Upstream conflict: disable/remove the separate upstream GFX1013 lifecycle before using the package-owned profile")
  fi

  kernel="$(kernel_release)"
  build="/lib/modules/$kernel/build"
  if ! command -v rpm >/dev/null 2>&1; then
    echo "  Exact kernel-devel: NOT CHECKED — required command rpm unavailable"
  elif [[ -e "$build" ]]; then
    build="$(readlink -f "$build")"
    build_owner="$(kernel_build_owner "$kernel" "$build" 2>/dev/null || true)"
    if [[ "$build_owner" == "kernel-devel-${kernel}" ]]; then
      ((verbose)) && echo "  Exact kernel-devel: PASS ($build_owner)"
    else
      echo "  Exact kernel-devel: BLOCKED (build tree owner ${build_owner:-unknown})"
      failures=$((failures + 1))
      remediation+=("Kernel development files: install the exact kernel-devel package matching $kernel")
    fi
  else
    echo "  Exact kernel-devel: BLOCKED (missing $build)"
    failures=$((failures + 1))
    remediation+=("Kernel development files: install kernel-devel-$kernel")
  fi

  version="${kernel%%-*}"
  release="${kernel#*-}"; release="${release%.*}"
  kernel_srpm_url="${BC250_GFX1013_KERNEL_SRPM_URL:-https://kojipkgs.fedoraproject.org/packages/kernel/${version}/${release}/src/kernel-${version}-${release}.src.rpm}"
  kernel_srpm="$CACHE_ROOT/kernel-${version}-${release}.src.rpm"
  echo "  Source/cache readiness:"
  if ! cache_readiness "Kernel source" "$kernel_srpm" "$kernel_srpm_url" "kernel-${kernel%.*}"; then
    source_prefetch_recommended=1
  fi
  if ! cache_readiness "Mesa source" "$CACHE_ROOT/mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm" "$MESA_SRPM_URL" "${MESA_SRPM_NEVRA%.src}"; then
    source_prefetch_recommended=1
  fi
  echo "  Running kernel: $kernel"
  if [[ "$kernel" == "$PACKAGE_QUALIFICATION_KERNEL" ]]; then
    echo "  Package qualification: $PACKAGE_QUALIFICATION_KERNEL — MATCH"
  else
    echo "  Package qualification: $PACKAGE_QUALIFICATION_KERNEL — DIFFERENT"
  fi
  echo "  Patch/profile reference: $PATCH_REFERENCE_KERNEL"
  echo "  Device-local artifacts: target $kernel"

  if ! command -v modinfo >/dev/null 2>&1; then
    echo "  Stock amdgpu module: NOT CHECKED — required command modinfo unavailable"
  else
    stock_module="$(find_stock_module "$kernel" 2>/dev/null || true)"
    if [[ -n "$stock_module" ]]; then
      ((verbose)) && echo "  Stock amdgpu module: PASS ($stock_module)"
    else
      echo "  Stock amdgpu module: BLOCKED (not found for exact running kernel)"
      failures=$((failures + 1))
      remediation+=("Stock amdgpu: restore the Fedora stock amdgpu module for exact running kernel $kernel")
    fi
  fi

  machine_id="$(cat /etc/machine-id 2>/dev/null || true)"
  if [[ -z "$machine_id" ]]; then
    echo "  Machine identity: BLOCKED (/etc/machine-id unavailable)"
    failures=$((failures + 1))
    remediation+=("Machine identity: restore a valid /etc/machine-id before staging boot artifacts")
    echo "  Stock BLS/default boot: NOT CHECKED — machine identity unavailable"
  elif ! command -v grub2-editenv >/dev/null 2>&1; then
    echo "  Stock BLS/default boot: NOT CHECKED — required command grub2-editenv unavailable"
  else
    stock_bls="$(find_stock_bls "$kernel" 2>/dev/null || true)"
    if [[ -n "$stock_bls" ]]; then
      stock_entry_id="$(basename "$stock_bls" .conf)"
      current_saved="$(grub_value saved_entry)"
      if [[ "$current_saved" == "$stock_entry_id" ]] && stock_entry_file_safe "$stock_bls"; then
        ((verbose)) && echo "  Stock BLS/default boot: PASS ($stock_entry_id)"
      else
        echo "  Stock BLS/default boot: BLOCKED (saved=${current_saved:-unset}, expected=$stock_entry_id)"
        failures=$((failures + 1))
        remediation+=("Stock boot: restore/select the exact Fedora stock BLS entry for $kernel as saved/default")
      fi
    else
      echo "  Stock BLS/default boot: BLOCKED (could not identify exactly one stock entry)"
      failures=$((failures + 1))
      remediation+=("Stock boot: restore exactly one unpatched Fedora stock BLS entry for $kernel")
    fi
  fi

  if [[ -n "$machine_id" ]]; then
    preflight_bls="/boot/loader/entries/${machine_id}-${kernel}-${PROFILE_VARIANT}.conf"
    preflight_initramfs="/boot/initramfs-${kernel}-${PROFILE_VARIANT}.img"
    if [[ -e "$preflight_bls" || -e "$preflight_initramfs" || -e "$(private_prefix)" ]]; then
      echo "  Stale staged artifacts: BLOCKED (reset required)"
      failures=$((failures + 1))
      remediation+=("Stale GFX1013 artifacts: run sudo bc250 gfx1013 reset --check, then reset only after reviewing the plan")
    else
      ((verbose)) && echo "  Stale staged artifacts: PASS"
    fi
  fi

  if ! command -v rpm >/dev/null 2>&1; then
    echo "  Package identity: NOT CHECKED — required command rpm unavailable"
  else
    package_id="$(package_nevra)"
    if [[ -n "$package_id" ]]; then
      ((verbose)) && echo "  Package identity: PASS ($package_id)"
    else
      echo "  Package identity: BLOCKED (bc250-llm-server package identity unavailable)"
      failures=$((failures + 1))
      remediation+=("Package identity: reinstall the matching bc250-llm-server RPM before preparing GFX1013")
    fi
  fi

  ((verbose)) && echo "  Build validation: DEFERRED — performed by 'bc250 gfx1013 prepare'"
  if ((source_prefetch_recommended)); then
    echo "Optional source prefetch: sudo bc250 gfx1013 prepare --download-only"
  fi
  if ((failures)); then
    if ((failures != ${#remediation[@]})); then
      die "internal prepare preflight accounting error: blockers=$failures remediations=${#remediation[@]}"
    fi
    printf 'GFX1013 prepare check: BLOCKED — %d remediation required\n' "$failures"
    echo "Fix before continuing:"
    printf '  %s\n' "${remediation[@]}"
    if [[ -n "$preflight_primary_action" ]]; then
      print_next_action "$preflight_primary_action"
    else
      echo "Then rerun:"
      echo "  sudo bc250 gfx1013 prepare --check"
    fi
    echo "No files, boot state or services were changed."
    return 2
  fi
  echo "GFX1013 prepare check: PASS"
  print_next_action "sudo bc250 gfx1013 prepare"
  echo "No files, boot state or services were changed."
  return 0
}

prefetch_sources() {
  local kernel version release kernel_srpm_url kernel_srpm
  need_root
  acquire_lifecycle_lock
  command -v curl >/dev/null 2>&1 || die "curl is required for source prefetch"
  command -v rpm >/dev/null 2>&1 || die "rpm is required for source prefetch"
  source_identity_ok || die "package-pinned GFX1013 source identity failed: $SOURCE"
  kernel="$(kernel_release)"
  version="${kernel%%-*}"
  release="${kernel#*-}"; release="${release%.*}"
  kernel_srpm_url="${BC250_GFX1013_KERNEL_SRPM_URL:-https://kojipkgs.fedoraproject.org/packages/kernel/${version}/${release}/src/kernel-${version}-${release}.src.rpm}"
  kernel_srpm="$CACHE_ROOT/kernel-${version}-${release}.src.rpm"
  PREPARE_LAST_STAGE_PRINTED=''
  prepare_stage 1 'Acquire Fedora kernel source'
  fetch_verified_srpm "$kernel_srpm_url" "$kernel_srpm" "kernel-${kernel%.*}" \
    "kernel-${version}-${release}.src.rpm" "exact-kernel GFX1013 amdgpu build" || {
      local fetch_rc=$?; ((fetch_rc == 130)) && { echo "GFX1013 source prefetch interrupted by operator; partial download retained." >&2; return 130; }
      die "kernel source prefetch failed; rerun to resume"
    }
  prepare_stage 5 'Acquire/prepare Fedora Mesa source'
  fetch_verified_srpm "$MESA_SRPM_URL" "$CACHE_ROOT/mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm" \
    "${MESA_SRPM_NEVRA%.src}" "mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm" "private headless RADV build" || {
      local fetch_rc=$?; ((fetch_rc == 130)) && { echo "GFX1013 source prefetch interrupted by operator; partial download retained." >&2; return 130; }
      die "Mesa source prefetch failed; rerun to resume"
    }
  echo "Source prefetch: PASS"
  echo "Kernel source: $kernel_srpm"
  echo "Mesa source: $CACHE_ROOT/mesa-${MESA_VERSION}-${MESA_FEDORA_RELEASE}.src.rpm"
  echo "Boot state changed: no"
  echo "Runtime/service state changed: no"
  print_next_action "sudo bc250 gfx1013 prepare --check"
}

prepare() {
  local option='' arg
  GFX_VERBOSE=0
  for arg in "$@"; do
    case "$arg" in
      --check|--download-only)
        [[ -z "$option" ]] || die "prepare accepts only one mode: --check or --download-only"
        option="$arg"
        ;;
      --verbose) GFX_VERBOSE=1 ;;
      *) die "unsupported prepare option: $arg" ;;
    esac
  done
  need_root
  case "$option" in
    --check) prepare_preflight "$GFX_VERBOSE"; return $? ;;
    --download-only) prefetch_sources; return $? ;;
    '') ;;
  esac
  acquire_lifecycle_lock
  if ! prepare_runtime_ready; then
    echo "ERROR: $PREPARE_RUNTIME_BLOCK_REASON" >&2
    print_next_action "$PREPARE_RUNTIME_NEXT_ACTION" >&2
    return 2
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
  if [[ "$kernel" == "$PACKAGE_QUALIFICATION_KERNEL" ]]; then
    printf 'Package qualification kernel: MATCH (%s). Preparing device-local GFX1013 artifacts.\n' "$kernel" >&2
  else
    printf 'Package qualification kernel: DIFFERENT (qualified %s; running %s). Preparing device-local exact-kernel GFX1013 artifacts.\n' "$PACKAGE_QUALIFICATION_KERNEL" "$kernel" >&2
  fi
  printf 'Patch/profile reference kernel: %s.\n' "$PATCH_REFERENCE_KERNEL" >&2

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
  stock_entry_file_safe "$stock_bls" "$kernel" || die "identified stock BLS entry does not match the expected stock kernel/initramfs identity"

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
  local -a module_identity=()
  mapfile -t module_identity < <(validate_built_module_identity "$build" "$artifact_work" "$work" "$kernel" "$work/module-identity.txt")
  ((${#module_identity[@]} == 5)) || die "module identity validation returned incomplete evidence"
  module_sha="${module_identity[0]}"
  vermagic="${module_identity[1]}"
  abi_mode="${module_identity[2]}"
  abi_sha="${module_identity[3]}"
  srcversion="${module_identity[4]}"
  patch_sha="$(patch_manifest_sha)"; source_sha="$(source_manifest_sha)"
  kernel_srpm_sha="$(sha256sum "$kernel_srpm" | awk '{print $1}')"
  mesa_srpm_sha="$(sha256sum "$mesa_srpm" | awk '{print $1}')"
  mesa_source_sha="$(sha256sum "$mesa_source0" | awk '{print $1}')"
  [[ "$mesa_source_sha" == "$MESA_SOURCE0_SHA256" ]] || die "Fedora Mesa Source0 SHA changed after build"

  # Commit boundary: all source, module ABI and private Mesa build validation has
  # completed. Only now commit prepared build artifacts and package lifecycle state.
  prepare_stage 7 'Commit prepared artifacts and lifecycle state'
  install -d -m 0700 "$prepared" "$prepared/build-evidence"
  install -m 0644 "$artifact_work" "$artifact"
  local log
  for log in kernel-srpm-members.txt kernel-prep.log kernel-source-provenance.txt kernel-build.log module-identity.txt mesa-prep.log mesa-setup.log mesa-build.log mesa-radv-needed.txt mesa-radv-needed-dynamic.txt; do
    [[ -f "$work/$log" ]] && install -m 0600 "$work/$log" "$prepared/build-evidence/$log"
  done

  # Preparation commits build artifacts only. It deliberately does not write
  # /boot or select a boot entry; stage-boot owns that separate activation step.
  install -d -m 0755 "$(dirname "$(private_prefix)")"
  cp -a "$stage$(private_prefix)" "$(private_prefix)"
  private_icd_library_ok "$(private_icd)" "$(private_radv_lib)" ||     die "deployed private RADV ICD does not retain the package-private library identity"
  [[ -f "$(private_radv_lib)" && -f "$(private_icd)" ]] || die "staged private RADV identity files are missing"
  private_radv_sha="$(sha256sum "$(private_radv_lib)" | awk '{print $1}')"
  private_icd_sha="$(sha256sum "$(private_icd)" | awk '{print $1}')"

  stock_initramfs="${BC250_GFX1013_BOOT_ROOT:-/boot}/initramfs-${kernel}.img"
  [[ -f "$stock_initramfs" ]] || die "stock initramfs missing: $stock_initramfs"
  stock_hash="$(sha256sum "$stock_module" | awk '{print $1}')"
  initramfs_hash="$(sha256sum "$stock_initramfs" | awk '{print $1}')"
  saved_before="$(grub_value saved_entry)"
  next_before="$(grub_value next_entry)"
  patched_id="${machine_id}-${kernel}-${PROFILE_VARIANT}"
  patched_bls="${BC250_GFX1013_BOOT_ROOT:-/boot}/loader/entries/${patched_id}.conf"
  patched_initramfs="${BC250_GFX1013_BOOT_ROOT:-/boot}/initramfs-${kernel}-${PROFILE_VARIANT}.img"

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
BC250_GFX1013_BUILD_EVIDENCE=$prepared/build-evidence
BC250_GFX1013_KERNEL_BUILD_RESULT=PASS
BC250_GFX1013_MESA_BUILD_RESULT=PASS
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
BC250_GFX1013_PATCHED_BLS_SHA256=
BC250_GFX1013_PATCHED_INITRAMFS_SHA256=
BC250_GFX1013_PRIVATE_PREFIX=$(private_prefix)
BC250_GFX1013_PRIVATE_RADV_LIB=$(private_radv_lib)
BC250_GFX1013_PRIVATE_RADV_SHA256=$private_radv_sha
BC250_GFX1013_ICD=$(private_icd)
BC250_GFX1013_ICD_SHA256=$private_icd_sha
BC250_GFX1013_PREVIOUS_SAVED_ENTRY=$saved_before
BC250_GFX1013_PREVIOUS_NEXT_ENTRY=$next_before
BC250_GFX1013_TRANSACTION_PHASE=PREPARED
BC250_GFX1013_RECOVERY_REQUIRED=0
BC250_GFX1013_ENABLED=0
EOF_STATE
  sed -i "s#^BC250_GFX1013_STOCK_ENTRY_ID=.*#BC250_GFX1013_STOCK_ENTRY_ID=$(basename "$stock_bls" .conf)#" "$ACTIVE_STATE"
  chmod 0600 "$ACTIVE_STATE"

  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$kernel")"
  PREPARE_COMMITTED=1
  rm -rf "$transaction"
  PREPARE_DIR=''
  trap - EXIT INT TERM
  echo "Preparation: PASS"
  echo "Prepared kernel: $kernel"
  echo "Patched module: validated ($module_sha)"
  echo "Private RADV: built and staged"
  echo "Build evidence: $prepared/build-evidence"
  echo "Boot state changed: no"
  echo "Runtime/service state changed: no"
  print_next_action "sudo bc250 gfx1013 stage-boot"
}

STAGE_BOOT_COMMITTED=1
STAGE_BOOT_WORK=''
STAGE_BOOT_PREVIOUS_NEXT=''

stage_boot_cleanup_on_exit() {
  local rc=$1 rollback_ok=1
  trap - EXIT INT TERM
  if [[ "$STAGE_BOOT_COMMITTED" != 1 ]]; then
    set +e
    [[ -z "${BC250_GFX1013_PATCHED_BLS:-}" ]] || rm -f -- "$BC250_GFX1013_PATCHED_BLS" || rollback_ok=0
    [[ -z "${BC250_GFX1013_PATCHED_INITRAMFS:-}" ]] || rm -f -- "$BC250_GFX1013_PATCHED_INITRAMFS" || rollback_ok=0
    [[ -z "${BC250_GFX1013_BUILD_EVIDENCE:-}" ]] || rm -rf -- "$(dirname "$BC250_GFX1013_BUILD_EVIDENCE")/boot-evidence" || rollback_ok=0
    [[ -z "$STAGE_BOOT_WORK" ]] || rm -rf -- "$STAGE_BOOT_WORK" || rollback_ok=0
    restore_previous_next "$STAGE_BOOT_PREVIOUS_NEXT" >/dev/null 2>&1 || rollback_ok=0
    set_active_transaction_state PREPARED 0 >/dev/null 2>&1 || rollback_ok=0
    if ((rollback_ok)) && [[ -n "${BC250_GFX1013_KERNEL:-}" ]]; then
      cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")" >/dev/null 2>&1 || rollback_ok=0
    fi
    if ((!rollback_ok)); then
      set_active_transaction_state SAFETY_FAILURE 1 'stage-boot rollback could not fully restore lifecycle/boot state' >/dev/null 2>&1 || true
      rc=5
    fi
    set -e
    if ((rc == 130)); then
      echo "GFX1013 stage-boot interrupted by operator." >&2
    else
      echo "GFX1013 stage-boot: FAILED" >&2
    fi
    echo "Prepared build retained: yes" >&2
    echo "Partial boot artifacts removed: $([[ $rollback_ok -eq 1 ]] && echo yes || echo incomplete)" >&2
    echo "Boot selection restored: $([[ $rollback_ok -eq 1 ]] && echo yes || echo incomplete)" >&2
    echo "Runtime/service state changed: no" >&2
    ((rollback_ok)) || echo "Recovery required: sudo bc250 gfx1013 reset --check" >&2
  fi
  exit "$rc"
}

stage_boot() {
  local saved next prepared info_file
  local -a stage_info=()
  need_root
  acquire_lifecycle_lock
  gfx_lifecycle_state
  [[ "$GFX_LIFECYCLE_STATE" == PREPARED ]] || \
    die "stage-boot requires PREPARED, found $GFX_LIFECYCLE_STATE: $GFX_STATE_REASON"
  load_active_state || die "no valid active GFX1013 preparation"
  verify_active_identity
  patched_boot_running && die "patched GFX1013 boot is already running"
  saved="$(grub_value saved_entry)"; next="$(grub_value next_entry)"
  [[ "$saved" == "$BC250_GFX1013_STOCK_ENTRY_ID" ]] || die "stock saved/default boot changed after prepare"
  if [[ "$next" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]]; then
    [[ -f "$BC250_GFX1013_PATCHED_BLS" && -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]] || \
      die "patched next_entry is selected but its boot artifacts are missing"
    echo "Boot activation: already staged"
    echo "Boot state changed: no"
    echo "Runtime/service state changed: no"
    print_next_action "sudo reboot"
    return 0
  fi
  if [[ -n "$next" && "$next" != "$BC250_GFX1013_STOCK_ENTRY_ID" ]]; then
    echo "GFX1013 stage-boot: BLOCKED" >&2
    echo "Another one-shot boot is already selected:" >&2
    echo "  $next" >&2
    echo "The existing boot selection was not changed." >&2
    print_next_action "sudo bc250 gfx1013 status --verbose" >&2
    return 2
  fi
  if [[ "$next" == "$BC250_GFX1013_STOCK_ENTRY_ID" ]]; then
    echo "Existing one-shot boot: verified stock entry — safe to replace for this staged boot."
  fi
  [[ ! -e "$BC250_GFX1013_PATCHED_BLS" && ! -e "$BC250_GFX1013_PATCHED_INITRAMFS" ]] || \
    die "stale patched boot artifacts exist without a matching next_entry; run reset before continuing"

  prepared="$(prepared_dir_for "$BC250_GFX1013_KERNEL")"
  STAGE_BOOT_WORK="$STATE_ROOT/.stage-boot-${BC250_GFX1013_KERNEL}-$$"
  STAGE_BOOT_PREVIOUS_NEXT="$next"
  STAGE_BOOT_COMMITTED=0
  set_active_transaction_state BOOT_ENTRY_STAGING 0 || die "cannot persist GFX1013 boot-staging transaction state"
  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")"
  trap 'stage_boot_cleanup_on_exit $?' EXIT
  trap 'exit 130' INT TERM
  install -d -m 0700 "$STAGE_BOOT_WORK"
  info_file="$STAGE_BOOT_WORK/stage-info"

  stage_patched_boot "$BC250_GFX1013_KERNEL" "$prepared" "$BC250_GFX1013_MODULE" \
    "$BC250_GFX1013_STOCK_MODULE" "$BC250_GFX1013_STOCK_BLS" "$STAGE_BOOT_WORK" "$info_file"
  mapfile -t stage_info < "$info_file"
  ((${#stage_info[@]} == 10)) || die "internal boot staging evidence error"
  [[ "${stage_info[0]}" == "$BC250_GFX1013_PATCHED_BLS" ]] || die "staged BLS path differs from prepared identity"
  [[ "${stage_info[1]}" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]] || die "staged BLS entry differs from prepared identity"
  [[ "${stage_info[2]}" == "$BC250_GFX1013_PATCHED_INITRAMFS" ]] || die "staged initramfs path differs from prepared identity"
  [[ "${stage_info[3]}" == "$BC250_GFX1013_STOCK_INITRAMFS" ]] || die "stock initramfs identity changed since prepare"
  [[ "${stage_info[6]}" == "$BC250_GFX1013_STOCK_MODULE_SHA256" ]] || die "stock module changed since prepare"
  [[ "${stage_info[7]}" == "$BC250_GFX1013_STOCK_INITRAMFS_SHA256" ]] || die "stock initramfs changed since prepare"
  set_staged_boot_identity "${stage_info[8]}" "${stage_info[9]}" || die "failed to persist staged boot artifact identity"

  select_patched_next_boot "$BC250_GFX1013_PATCHED_ENTRY_ID" "$saved" "$next" || \
    die "failed to select and verify the patched entry for one-shot boot"
  set_active_transaction_state PREPARED 0 || die "failed to commit GFX1013 boot-staging lifecycle state"
  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")"

  rm -rf -- "$STAGE_BOOT_WORK"
  STAGE_BOOT_WORK=''
  STAGE_BOOT_COMMITTED=1
  trap - EXIT INT TERM
  echo "Boot activation: PASS"
  echo "Patched next boot: $BC250_GFX1013_PATCHED_ENTRY_ID"
  echo "Saved/default boot: $BC250_GFX1013_STOCK_ENTRY_ID (unchanged)"
  echo "Boot evidence: $prepared/boot-evidence"
  echo "Boot state changed: yes (patched artifacts staged + next boot selected)"
  echo "Runtime/service state changed: no"
  print_next_action "sudo reboot"
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
  if [[ -f "$BC250_GFX1013_PATCHED_BLS" || -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]]; then
    [[ -f "$BC250_GFX1013_PATCHED_BLS" && -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]] || die "patched boot artifact set is incomplete"
    [[ "${BC250_GFX1013_PATCHED_BLS_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || die "patched BLS identity is unavailable"
    [[ "${BC250_GFX1013_PATCHED_INITRAMFS_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || die "patched initramfs identity is unavailable"
    [[ "$(sha256sum "$BC250_GFX1013_PATCHED_BLS" | awk '{print $1}')" == "$BC250_GFX1013_PATCHED_BLS_SHA256" ]] || die "patched BLS identity changed after staging"
    [[ "$(sha256sum "$BC250_GFX1013_PATCHED_INITRAMFS" | awk '{print $1}')" == "$BC250_GFX1013_PATCHED_INITRAMFS_SHA256" ]] || die "patched initramfs identity changed after staging"
  fi
  [[ "${BC250_GFX1013_MESA_SRPM_NEVRA:-}" == "$MESA_SRPM_NEVRA" ]] || die "prepared Mesa Fedora source identity differs from package baseline"
  [[ "${BC250_GFX1013_MESA_SOURCE_SHA256:-}" == "$MESA_SOURCE0_SHA256" ]] || die "prepared Mesa Source0 identity differs from package baseline"
  [[ -f "$BC250_GFX1013_STOCK_MODULE" ]] || die "recorded stock amdgpu module is missing"
  [[ "$(sha256sum "$BC250_GFX1013_STOCK_MODULE" | awk '{print $1}')" == "$BC250_GFX1013_STOCK_MODULE_SHA256" ]] || die "stock amdgpu changed since prepare"
  [[ -f "$BC250_GFX1013_STOCK_INITRAMFS" ]] || die "recorded stock initramfs is missing"
  [[ "$(sha256sum "$BC250_GFX1013_STOCK_INITRAMFS" | awk '{print $1}')" == "$BC250_GFX1013_STOCK_INITRAMFS_SHA256" ]] || die "stock initramfs changed since prepare"
  [[ -f "$BC250_GFX1013_PRIVATE_RADV_LIB" ]] || die "private RADV library is missing"
  [[ "$(sha256sum "$BC250_GFX1013_PRIVATE_RADV_LIB" | awk '{print $1}')" == "$BC250_GFX1013_PRIVATE_RADV_SHA256" ]] || die "private RADV library identity changed"
  [[ -f "$BC250_GFX1013_ICD" ]] || die "private RADV ICD is missing"
  [[ "$(sha256sum "$BC250_GFX1013_ICD" | awk '{print $1}')" == "$BC250_GFX1013_ICD_SHA256" ]] || die "private RADV ICD identity changed"
}

ollama_guard() {
  local current_package phase enabled
  load_active_state || { echo "GFX1013 Ollama guard: lifecycle state is missing/invalid" >&2; return 1; }
  phase="${BC250_GFX1013_TRANSACTION_PHASE:-}"
  enabled="${BC250_GFX1013_ENABLED:-0}"
  case "$phase:$enabled" in
    ENABLING:0|ENABLED:1) ;;
    *) echo "GFX1013 Ollama guard: lifecycle phase is not allowed for private RADV ($phase/$enabled)" >&2; return 1 ;;
  esac
  [[ "${BC250_GFX1013_RECOVERY_REQUIRED:-1}" == 0 ]] || {
    echo "GFX1013 Ollama guard: lifecycle requires recovery" >&2; return 1;
  }
  current_package="$(package_nevra)"
  [[ -n "$current_package" && "$current_package" == "${BC250_GFX1013_PACKAGE_NEVRA:-}" ]] || {
    echo "GFX1013 Ollama guard: package identity changed since prepare" >&2; return 1;
  }
  [[ "$(kernel_release)" == "$BC250_GFX1013_KERNEL" ]] || {
    echo "GFX1013 Ollama guard: running kernel differs from prepared kernel" >&2; return 1;
  }
  patched_boot_running || {
    echo "GFX1013 Ollama guard: current boot lacks the patched marker" >&2; return 1;
  }
  [[ -f "$BC250_GFX1013_PRIVATE_RADV_LIB" && -f "$BC250_GFX1013_ICD" ]] || {
    echo "GFX1013 Ollama guard: private RADV payload is incomplete" >&2; return 1;
  }
  [[ "$(sha256sum "$BC250_GFX1013_PRIVATE_RADV_LIB" | awk '{print $1}')" == "$BC250_GFX1013_PRIVATE_RADV_SHA256" ]] || {
    echo "GFX1013 Ollama guard: private RADV library identity changed" >&2; return 1;
  }
  [[ "$(sha256sum "$BC250_GFX1013_ICD" | awk '{print $1}')" == "$BC250_GFX1013_ICD_SHA256" ]] || {
    echo "GFX1013 Ollama guard: private RADV ICD identity changed" >&2; return 1;
  }
  private_icd_library_ok "$BC250_GFX1013_ICD" "$BC250_GFX1013_PRIVATE_RADV_LIB" || {
    echo "GFX1013 Ollama guard: private ICD no longer points at private RADV" >&2; return 1;
  }
  loaded_amdgpu_identity_ok || {
    echo "GFX1013 Ollama guard: loaded patched amdgpu attestation failed: $GFX_MODULE_ATTESTATION_REASON" >&2; return 1;
  }
  if [[ "$phase" == ENABLED ]]; then
    [[ "$(grub_value saved_entry)" == "$BC250_GFX1013_PATCHED_ENTRY_ID" ]] || {
      echo "GFX1013 Ollama guard: enabled state lost patched saved/default boot authority" >&2; return 1;
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
ENABLE_PREVIOUS_NEXT=''

ollama_enable_smoke() {
  local attempt
  for attempt in {1..20}; do
    curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

restore_prepared_state_after_enable_failure() {
  local tmp="$ACTIVE_STATE.rollback.tmp"
  [[ -r "$ACTIVE_STATE" ]] || return 1
  awk '!/^BC250_GFX1013_ENABLED=/ && !/^BC250_GFX1013_VULKAN_/ && !/^BC250_GFX1013_TRANSACTION_PHASE=/ && !/^BC250_GFX1013_RECOVERY_REQUIRED=/ && !/^BC250_GFX1013_RECOVERY_REASON=/' "$ACTIVE_STATE" > "$tmp" || return 1
  cat >> "$tmp" <<'EOF_PREPARED_STATE'
BC250_GFX1013_TRANSACTION_PHASE=PREPARED
BC250_GFX1013_RECOVERY_REQUIRED=0
BC250_GFX1013_ENABLED=0
EOF_PREPARED_STATE
  chmod 0600 "$tmp" || return 1
  mv -f "$tmp" "$ACTIVE_STATE" || return 1
  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")" || return 1
}

enable_cleanup_on_exit() {
  local rc=$1 rollback_ok=1
  trap - EXIT INT TERM
  if [[ "$ENABLE_COMMITTED" != 1 ]]; then
    set +e
    rm -f -- "$DROPIN" "$DROPIN.tmp" || rollback_ok=0
    systemctl daemon-reload >/dev/null 2>&1 || rollback_ok=0
    if [[ -n "$ENABLE_PREVIOUS_SAVED" ]]; then
      grub2-set-default "$ENABLE_PREVIOUS_SAVED" >/dev/null 2>&1 || rollback_ok=0
      [[ "$(grub_value saved_entry)" == "$ENABLE_PREVIOUS_SAVED" ]] || rollback_ok=0
    fi
    restore_previous_next "$ENABLE_PREVIOUS_NEXT" >/dev/null 2>&1 || rollback_ok=0
    restore_prepared_state_after_enable_failure >/dev/null 2>&1 || rollback_ok=0
    if ((ENABLE_WAS_ACTIVE)); then
      systemctl restart ollama.service >/dev/null 2>&1 || true
    fi
    if ((rollback_ok)); then
      :
    else
      set_active_transaction_state SAFETY_FAILURE 1 'failed to restore boot/lifecycle state during enable rollback' >/dev/null 2>&1 || true
      echo "ERROR: GFX1013 enable rollback could not fully restore boot/lifecycle state; recovery state was preserved" >&2
      rc=5
    fi
    set -e
  fi
  exit "$rc"
}

enable() {
  need_root
  acquire_lifecycle_lock
  gfx_lifecycle_state
  [[ "$GFX_LIFECYCLE_STATE" == PATCHED_BOOT_UNVERIFIED ]] || \
    die "enable requires PATCHED_BOOT_UNVERIFIED, found $GFX_LIFECYCLE_STATE: $GFX_STATE_REASON"
  load_active_state || die "no valid active GFX1013 preparation"
  [[ "${BC250_GFX1013_TRANSACTION_PHASE:-}" == PREPARED && "${BC250_GFX1013_RECOVERY_REQUIRED:-1}" == 0 && "${BC250_GFX1013_ENABLED:-0}" == 0 ]] || \
    die "prepared lifecycle flags are incoherent; recovery is required"
  [[ "$(kernel_release)" == "$BC250_GFX1013_KERNEL" ]] || die "prepared state belongs to kernel $BC250_GFX1013_KERNEL, not $(kernel_release)"
  verify_active_identity
  [[ -f "$BC250_GFX1013_PATCHED_BLS" && -f "$BC250_GFX1013_PATCHED_INITRAMFS" ]] ||     die "patched boot artifacts are missing after staged one-shot boot"
  verify_loaded_amdgpu_identity
  bc250_device_present || die "AMD BC-250 PCI device 1002:13fe not found"
  [[ "$(modinfo -F vermagic "$BC250_GFX1013_MODULE" 2>/dev/null || true)" == "$BC250_GFX1013_KERNEL "* ]] || die "prepared module vermagic changed/mismatched"
  local vk_identity vk_vendor vk_device vk_driver vk_summary_sha vk_queue state_tmp
  vk_identity="$(verify_private_radv_device "$BC250_GFX1013_ICD" "$BC250_GFX1013_PRIVATE_RADV_LIB")"
  IFS='|' read -r vk_vendor vk_device vk_driver vk_summary_sha <<< "$vk_identity"
  [[ "$vk_vendor" == 0x1002 && "$vk_device" == 0x13fe && "$vk_driver" == radv && "$vk_summary_sha" =~ ^[0-9a-f]{64}$ ]] || \
    die "private RADV identity evidence is malformed"
  vk_queue="$(verify_private_radv_compute_queue "$BC250_GFX1013_ICD")"

  ENABLE_WAS_ACTIVE=0
  systemctl is-active --quiet ollama.service && ENABLE_WAS_ACTIVE=1 || true
  ((ENABLE_WAS_ACTIVE)) || die "ollama.service must be active so private-RADV activation can be smoke-tested before boot promotion"
  [[ ! -e "$UPSTREAM_GENERATOR" && ! -e "$UPSTREAM_STATE/active.env" ]] || die "separate upstream GFX1013 installation appeared after prepare; refusing activation"
  ENABLE_PREVIOUS_SAVED="$(grub_value saved_entry)"
  ENABLE_PREVIOUS_NEXT="$(grub_value next_entry)"
  [[ "$ENABLE_PREVIOUS_SAVED" == "$BC250_GFX1013_STOCK_ENTRY_ID" ]] || \
    die "stock saved/default boot changed after prepare; refusing promotion"
  [[ -z "$ENABLE_PREVIOUS_NEXT" ]] || die "patched one-shot next_entry was not consumed; refusing activation"

  set_active_transaction_state ENABLING 0 || die "cannot persist GFX1013 ENABLING transaction state"
  ENABLE_COMMITTED=0
  trap 'enable_cleanup_on_exit $?' EXIT
  trap 'exit 130' INT TERM

  # First prove that the running one-shot patched boot can actually restart the
  # appliance's Ollama service with the private driver. The saved/default boot
  # remains stock during this potentially hard-hang-prone step.
  write_ollama_dropin
  systemctl restart ollama.service || die "Ollama restart failed during private-RADV activation smoke"
  systemctl is-active --quiet ollama.service || die "Ollama is not active during private-RADV activation smoke"
  ollama_enable_smoke || die "Ollama API smoke check failed during private-RADV activation"

  # Only after the live workload path survives do we promote the patched boot.
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
BC250_GFX1013_VULKAN_COMPUTE_QUEUE_FAMILY=$vk_queue
EOF_VK_STATE
  chmod 0600 "$state_tmp"
  mv -f "$state_tmp" "$ACTIVE_STATE"
  cp -p "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")"

  ENABLE_COMMITTED=1
  trap - EXIT INT TERM
  echo "Enable: PASS"
  echo "Loaded patched amdgpu: attested (boot-chain + exact module identity; srcversion supplemental=$BC250_GFX1013_MODULE_SRCVERSION)"
  echo "Private RADV: enabled for ollama.service"
  echo "BC-250 compute queue family: $vk_queue"
  echo "Patched saved/default boot: $BC250_GFX1013_PATCHED_ENTRY_ID"
  echo "Boot state changed: yes"
  echo "Runtime/service state changed: yes"
  echo "GFX1013 is enabled."
  print_next_action "none — GFX1013 is ready"
  echo "Qualification only: sudo bc250 gfx1013 status"
}

risky_artifacts_without_state() {
  [[ -e "$ACTIVE_STATE" || -e "$DROPIN" || -d "$(private_prefix)" ]] && return 0
  find "$STATE_ROOT/prepared" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q . && return 0
  find "$STATE_ROOT" -mindepth 1 -maxdepth 1 -type d -name '.prepare-*' -print -quit 2>/dev/null | grep -q . && return 0
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
  if load_active_state && stock_entry_file_safe "$BC250_GFX1013_STOCK_BLS" "$BC250_GFX1013_KERNEL"; then
    printf '%s|%s\n' "$BC250_GFX1013_STOCK_BLS" "$BC250_GFX1013_STOCK_ENTRY_ID"
    return 0
  fi
  return 1
}

stock_reboot_pending() {
  local target stock_bls stock_entry saved next
  [[ ! -e "$ACTIVE_STATE" ]] || return 1
  patched_boot_running || return 1
  [[ ! -e "$DROPIN" ]] || return 1
  risky_artifacts_without_state && return 1
  target="$(resolve_safe_stock_target)" || return 1
  IFS='|' read -r stock_bls stock_entry <<< "$target"
  stock_entry_file_safe "$stock_bls" || return 1
  saved="$(grub_value saved_entry)"
  next="$(grub_value next_entry)"
  [[ "$saved" == "$stock_entry" && "$next" == "$stock_entry" ]]
}

PREPARE_RUNTIME_BLOCK_REASON=''
PREPARE_RUNTIME_NEXT_ACTION=''
prepare_runtime_ready() {
  PREPARE_RUNTIME_BLOCK_REASON=''
  PREPARE_RUNTIME_NEXT_ACTION=''
  if patched_boot_running; then
    if stock_reboot_pending; then
      PREPARE_RUNTIME_BLOCK_REASON='current runtime is patched GFX1013 while verified stock is already selected for the next boot; preparation requires a stock running boot'
      PREPARE_RUNTIME_NEXT_ACTION='sudo reboot'
    else
      PREPARE_RUNTIME_BLOCK_REASON='current runtime is patched GFX1013; restore verified stock boot authority and reboot before preparation'
      PREPARE_RUNTIME_NEXT_ACTION='sudo bc250 gfx1013 reset --check'
    fi
    return 1
  fi
  return 0
}

print_stock_reboot_pending() {
  local command_name=$1 target stock_bls stock_entry
  target="$(resolve_safe_stock_target)" || die "verified stock boot authority disappeared while reporting reboot-pending state"
  IFS='|' read -r stock_bls stock_entry <<< "$target"
  echo "$command_name: PASS (stock rollback prepared; reboot pending)"
  echo "Current runtime: patched GFX1013"
  echo "Verified next boot: stock ($stock_entry)"
  echo "Boot configuration: already restored"
  echo "Runtime override: disabled"
  echo "Boot state changed: no"
  echo "Runtime/service state changed: no"
  echo "A reboot is required to complete the return to stock."
  print_next_action "sudo reboot"
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
  if [[ "$state" == STOCK_REBOOT_REQUIRED ]]; then
    print_next_action "sudo reboot"
  fi
}

remove_loaded_state_artifacts() {
  rm -f -- "$BC250_GFX1013_PATCHED_BLS" "$BC250_GFX1013_PATCHED_INITRAMFS"
  rm -rf -- "$BC250_GFX1013_PRIVATE_PREFIX"
  rm -f -- "$ACTIVE_STATE" "$(prepared_stamp_for "$BC250_GFX1013_KERNEL")"
  rm -rf -- "$(prepared_dir_for "$BC250_GFX1013_KERNEL")"
}

remove_orphaned_package_artifacts() {
  local path
  [[ ! -e "$UPSTREAM_GENERATOR" && ! -e "$UPSTREAM_STATE/active.env" ]] || \
    die "separate upstream GFX1013 installation is present; refusing package orphan cleanup"
  rm -f -- "$DROPIN"
  rm -rf -- "$(private_prefix)"
  while IFS= read -r path; do rm -f -- "$path"; done < <(
    find /boot/loader/entries -maxdepth 1 -type f -name "*-${PROFILE_VARIANT}.conf" -print 2>/dev/null
  )
  while IFS= read -r path; do rm -f -- "$path"; done < <(
    find /boot -maxdepth 1 -type f -name "initramfs-*-${PROFILE_VARIANT}.img" -print 2>/dev/null
  )
  rm -rf -- "$STATE_ROOT/prepared"
  while IFS= read -r path; do rm -rf -- "$path"; done < <(
    find "$STATE_ROOT" -mindepth 1 -maxdepth 1 -type d -name '.prepare-*' -print 2>/dev/null
  )
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
  acquire_lifecycle_lock
  if ! load_active_state; then
    if stock_reboot_pending; then
      if [[ "$option" == --package-upgrade || "$option" == --package-erase ]]; then
        echo "Disable: PASS (stock rollback already prepared; reboot pending)"
        echo "Boot state changed: no"
        echo "Runtime/service state changed: no"
      else
        print_stock_reboot_pending "Disable"
      fi
      return 0
    fi
    if risky_artifacts_without_state; then
      die "GFX1013 artifacts exist but authoritative lifecycle state is missing/invalid; use 'bc250 gfx1013 reset' after proving the stock boot path"
    fi
    echo "Disable: PASS (already disabled)"
    echo "Boot state changed: no"
    echo "Runtime/service state changed: no"
    if [[ "$option" != --package-upgrade && "$option" != --package-erase ]]; then
      print_next_action "sudo bc250 gfx1013 status"
    fi
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

  echo "Disable: PASS"
  echo "Boot state changed: yes — verified stock saved + next path restored"
  echo "Runtime/service state changed: $([[ $was_active -eq 1 ]] && printf yes || printf no)"
  if [[ "$option" != --package-upgrade && "$option" != --package-erase ]]; then
    if patched_boot_running; then
      print_next_action "sudo reboot"
    else
      print_next_action "none — GFX1013 is disabled and the stock runtime is active"
    fi
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
  acquire_lifecycle_lock
  if load_active_state; then
    disable
    return 0
  fi
  if stock_reboot_pending; then
    print_stock_reboot_pending "Reset"
    return 0
  fi
  if ! risky_artifacts_without_state; then
    echo "Reset: PASS (nothing to do; already disabled)"
    echo "Boot state changed: no"
    echo "Runtime/service state changed: no"
    print_next_action "sudo bc250 gfx1013 status"
    return 0
  fi

  # Recovery is deliberately independent of stale lifecycle metadata, but never
  # claims ownership of a separate upstream installation. Refuse before any boot
  # mutation when such state is present.
  [[ ! -e "$UPSTREAM_GENERATOR" && ! -e "$UPSTREAM_STATE/active.env" ]] || \
    die "separate upstream GFX1013 installation is present; refusing package recovery cleanup"
  # Prove and commit a stock BLS path for the current/recorded kernel, then clean
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
  echo "Reset: PASS"
  echo "Boot state changed: yes — verified stock saved + next path restored"
  echo "Runtime/service state changed: $([[ $was_active -eq 1 ]] && printf yes || printf no)"
  if patched_boot_running; then
    print_next_action "sudo reboot"
  else
    print_next_action "none — GFX1013 recovery is complete and the stock runtime is active"
  fi
}

if [[ ${BC250_GFX1013_LIBRARY_ONLY:-0} == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

case "${1:-status}" in
  status)
    case "${2:-}" in '' ) status ;; --brief) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; status_brief ;; --verbose) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; status_verbose ;; --json) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; status_json ;; *) usage >&2; exit 2 ;; esac ;;
  prepare) shift; [[ $# -le 2 ]] || { usage >&2; exit 2; }; prepare "$@" ;;
  stage-boot) [[ $# -eq 1 ]] || { usage >&2; exit 2; }; stage_boot ;;
  enable) [[ $# -eq 1 ]] || { usage >&2; exit 2; }; enable ;;
  disable) [[ $# -le 2 ]] || { usage >&2; exit 2; }; disable "${2:-}" ;;
  reset) [[ $# -le 2 ]] || { usage >&2; exit 2; }; reset "${2:-}" ;;
  benchmark) benchmark "$@" ;;
  ollama-guard) [[ $# -eq 1 ]] || exit 1; ollama_guard ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac

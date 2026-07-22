#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Fedora integration for duggasco/fduraibi bc250-40cu-unlock.
# The register patch and build method are derived from the pinned upstream tool.
set -Eeuo pipefail
umask 0022

readonly KVER="$(uname -r)"
readonly KVER_BASE="${KVER%%-*}"
readonly MODDIR="/usr/lib/modules/${KVER}"
readonly MODPATH="${MODDIR}/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
readonly CACHE_ROOT="${BC250_40CU_CACHE:-/var/cache/bc250-llm-server/40cu}"
readonly WORK_ROOT="${CACHE_ROOT}/${KVER}"
readonly SOURCE_DIR="${WORK_ROOT}/source"
readonly SOURCE_ARCHIVE="${CACHE_ROOT}/linux-${KVER_BASE}.tar.xz"
readonly BUILD_LOG="${WORK_ROOT}/build.log"
readonly STATE_DIR="/var/lib/bc250-llm-server/40cu"
readonly CONF40="/etc/modprobe.d/bc250-40cu.conf"
readonly DRACUT_CONF="/etc/dracut.conf.d/90-bc250-40cu.conf"
readonly BC250_PCI_ID="1002:13fe"

info() { printf '\033[0;32m[+]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[0;33m[!]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[0;31m[E]\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ ${EUID} -eq 0 ]] || die "run this command with sudo"
}

check_bc250() {
  lspci -Dnn 2>/dev/null | grep -Fi "[$BC250_PCI_ID]" >/dev/null && return
  [[ "${BC250_40CU_FORCE:-0}" == 1 ]] || \
    die "BC-250 PCI device $BC250_PCI_ID was not detected"
  warn "BC250_40CU_FORCE=1: continuing without a detected BC-250"
}

ensure_dependencies() {
  if [[ ! -d "${MODDIR}/build" ]]; then
    command -v dnf >/dev/null 2>&1 || \
      die "kernel-devel-$KVER is missing and dnf is unavailable"
    info "Installing development files for the running kernel $KVER..."
    dnf install -y "kernel-devel-$KVER"
  fi

  local command missing=()
  for command in curl dracut gcc grep lsinitrd make modinfo tar xz zstd; do
    command -v "$command" >/dev/null 2>&1 || missing+=("$command")
  done
  ((${#missing[@]} == 0)) || die "missing required commands: ${missing[*]}"
  [[ -d "${MODDIR}/build" ]] || die "kernel-devel-$KVER is not installed"
}

module_target() {
  local resolved candidate
  resolved="$(modinfo -k "$KVER" -n amdgpu 2>/dev/null || true)"
  case "$resolved" in
    "$MODPATH"|"${MODPATH}.xz"|"${MODPATH}.zst")
      printf '%s\n' "$resolved"
      return
      ;;
  esac
  for candidate in "${MODPATH}.xz" "${MODPATH}.zst" "$MODPATH"; do
    [[ ! -f "$candidate" ]] || { printf '%s\n' "$candidate"; return; }
  done
  printf '%s\n' "${MODPATH}.xz"
}

module_has_parameter() {
  local metadata
  metadata="$(modinfo "$1" 2>/dev/null)" || return 1
  grep '^parm:.*bc250_cc_write_mode' <<< "$metadata" >/dev/null
}

module_vermagic_matches() {
  local vermagic
  vermagic="$(modinfo -F vermagic "$1" 2>/dev/null || true)"
  [[ "$vermagic" == "$KVER "* || "$vermagic" == "$KVER" ]]
}

module_blob_has_parameter() {
  local format="$1" file="$2"
  case "$format" in
    *.xz) xz --decompress --stdout "$file" | grep -a 'bc250_cc_write_mode' >/dev/null ;;
    *.zst) zstd --decompress --stdout --quiet "$file" | grep -a 'bc250_cc_write_mode' >/dev/null ;;
    *) grep -a 'bc250_cc_write_mode' "$file" >/dev/null ;;
  esac
}

module_blob_valid() {
  local format="$1" file="$2"
  case "$format" in
    *.xz) xz --test "$file" >/dev/null 2>&1 ;;
    *.zst) zstd --test --quiet "$file" >/dev/null 2>&1 ;;
    *) [[ -s "$file" ]] ;;
  esac
}

signature_enforcement_active() {
  grep -qw 'module.sig_enforce=1' /proc/cmdline 2>/dev/null && return 0
  [[ -r /sys/kernel/security/lockdown ]] && \
    grep -Eq '\[(integrity|confidentiality)\]' /sys/kernel/security/lockdown
}

check_module_authentication() {
  local module="${1:-}" signer=""
  [[ -z "$module" ]] || signer="$(modinfo -F signer "$module" 2>/dev/null || true)"
  if signature_enforcement_active && [[ -z "$signer" ]]; then
    die "kernel module signature enforcement is active. The package cannot
automatically enroll a trusted key, so an unsigned replacement AMDGPU module
would not load. Disable Secure Boot/signature enforcement or enroll and use a
module-signing key before preparing 40-CU support. No module was replaced."
  fi
}

download_source() {
  local major url partial
  major="${KVER_BASE%%.*}"
  url="https://cdn.kernel.org/pub/linux/kernel/v${major}.x/linux-${KVER_BASE}.tar.xz"
  partial="${SOURCE_ARCHIVE}.partial"
  install -d -m0750 "$CACHE_ROOT"

  if [[ -s "$SOURCE_ARCHIVE" ]] && tar -tJf "$SOURCE_ARCHIVE" >/dev/null 2>&1; then
    info "Using cached kernel source archive $SOURCE_ARCHIVE"
    return
  fi

  info "Downloading the matching kernel source once (~120 MB):"
  info "  $url"
  if [[ -s "$partial" ]]; then
    curl --fail --location --retry 3 --retry-all-errors --progress-bar \
      --continue-at - --output "$partial" "$url" || {
        rm -f -- "$partial"
        curl --fail --location --retry 3 --retry-all-errors --progress-bar \
          --output "$partial" "$url"
      }
  else
    curl --fail --location --retry 3 --retry-all-errors --progress-bar \
      --output "$partial" "$url"
  fi
  tar -tJf "$partial" >/dev/null || die "downloaded kernel source archive is invalid"
  mv -f -- "$partial" "$SOURCE_ARCHIVE"
}

find_source() {
  local candidate
  for candidate in \
      "/usr/src/linux-${KVER}" \
      "/usr/src/linux-${KVER_BASE}" \
      "/usr/src/linux"; do
    if [[ -f "$candidate/drivers/gpu/drm/amd/amdgpu/gfx_v10_0.c" ]]; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  if [[ -f "$SOURCE_DIR/drivers/gpu/drm/amd/amdgpu/gfx_v10_0.c" ]]; then
    printf '%s\n' "$SOURCE_DIR"
    return
  fi

  download_source
  rm -rf -- "$SOURCE_DIR"
  install -d -m0750 "$SOURCE_DIR"
  info "Extracting the AMDGPU build subtree into the persistent cache..."
  tar -xJf "$SOURCE_ARCHIVE" -C "$SOURCE_DIR" --strip-components=1 \
    --wildcards \
    '*/drivers/gpu/drm/amd/' \
    '*/include/drm/' \
    '*/include/uapi/drm/'
  [[ -f "$SOURCE_DIR/drivers/gpu/drm/amd/amdgpu/gfx_v10_0.c" ]] || \
    die "matching AMDGPU source was not found in $SOURCE_ARCHIVE"
  printf '%s\n' "$SOURCE_DIR"
}

write_param_patch() {
  cat > "$1" <<'EOF_PARAM'

/* BC-250 40 CU unlock: clears harvest mask + enables SPI dispatch to all WGPs */
static int bc250_cc_write_mode;
module_param(bc250_cc_write_mode, int, 0444);
MODULE_PARM_DESC(bc250_cc_write_mode,
	"BC-250: 0=off 1=probe-SE0SH0 2=clear-SE0SH0 3=clear-all-SAs 4=probe-all-SAs");
#define BC250_PCI_DEVICE_ID 0x13FE

EOF_PARAM
}

write_register_patch() {
  cat > "$1" <<'EOF_REGISTER'

	/* BC-250: unlock harvested CUs -- CC enumeration + SPI dispatch + RLC power */
	if (bc250_cc_write_mode > 0 && adev->pdev->device == BC250_PCI_DEVICE_ID) {
		int bc_se, bc_sh;
		for (bc_se = 0; bc_se < adev->gfx.config.max_shader_engines; bc_se++) {
			for (bc_sh = 0; bc_sh < adev->gfx.config.max_sh_per_se; bc_sh++) {
				u32 bc_cc_orig, bc_cc_after, bc_spi_orig, bc_spi_after;
				if (bc250_cc_write_mode == 2 && (bc_se > 0 || bc_sh > 0))
					continue;
				gfx_v10_0_select_se_sh(adev, bc_se, bc_sh, 0xffffffff, 0);
				bc_cc_orig = RREG32_SOC15(GC, 0, mmCC_GC_SHADER_ARRAY_CONFIG);
				WREG32_SOC15(GC, 0, mmCC_GC_SHADER_ARRAY_CONFIG, 0);
				bc_cc_after = RREG32_SOC15(GC, 0, mmCC_GC_SHADER_ARRAY_CONFIG);
				bc_spi_orig = RREG32_SOC15(GC, 0, mmSPI_PG_ENABLE_STATIC_WGP_MASK);
				WREG32_SOC15(GC, 0, mmSPI_PG_ENABLE_STATIC_WGP_MASK, 0x1f);
				bc_spi_after = RREG32_SOC15(GC, 0, mmSPI_PG_ENABLE_STATIC_WGP_MASK);
				WREG32_SOC15(GC, 0, mmRLC_PG_ALWAYS_ON_WGP_MASK, 0x1f);
				if (bc250_cc_write_mode == 1 || bc250_cc_write_mode == 4) {
					WREG32_SOC15(GC, 0, mmCC_GC_SHADER_ARRAY_CONFIG, bc_cc_orig);
					WREG32_SOC15(GC, 0, mmSPI_PG_ENABLE_STATIC_WGP_MASK, bc_spi_orig);
					dev_info(adev->dev,
						"bc250-40cu-probe: se=%d sh=%d CC=0x%08x->0x%08x SPI=0x%08x->0x%08x (restored)",
						bc_se, bc_sh, bc_cc_orig, bc_cc_after, bc_spi_orig, bc_spi_after);
				} else {
					dev_info(adev->dev,
						"bc250-40cu-enable: mode=%d se=%d sh=%d CC=0x%08x->0x%08x SPI=0x%08x->0x%08x",
						bc250_cc_write_mode, bc_se, bc_sh,
						bc_cc_orig, bc_cc_after, bc_spi_orig, bc_spi_after);
				}
			}
		}
		gfx_v10_0_select_se_sh(adev, 0xffffffff, 0xffffffff, 0xffffffff, 0);
	}

EOF_REGISTER
}

patch_source() {
  local source="$1" gfx param_file register_file
  gfx="$source/drivers/gpu/drm/amd/amdgpu/gfx_v10_0.c"
  grep -q 'bc250_cc_write_mode' "$gfx" && { info "Cached source is already patched."; return; }
  grep -q '#include "amdgpu.h"' "$gfx" || die "AMDGPU include anchor changed in kernel $KVER_BASE"

  info "Applying the pinned BC-250 register patch..."
  cp -- "$gfx" "${gfx}.orig"
  param_file="$(mktemp)"
  register_file="$(mktemp)"
  write_param_patch "$param_file"
  write_register_patch "$register_file"
  sed -i "/#include \"amdgpu.h\"/r ${param_file}" "$gfx"
  awk -v insertfile="$register_file" '
    /static.*gfx_v10_0_get_cu_info/ { maybe_func = 1 }
    maybe_func && /;/ { maybe_func = 0 }
    maybe_func && /^\{/ { in_cu_info = 1; maybe_func = 0 }
    in_cu_info && /mutex_lock/ && !inserted {
      print
      while ((getline line < insertfile) > 0) print line
      close(insertfile)
      inserted = 1
      next
    }
    { print }
  ' "$gfx" > "${gfx}.new"
  rm -f -- "$param_file" "$register_file"
  if grep -q 'bc250-40cu-enable' "${gfx}.new"; then
    mv -f -- "${gfx}.new" "$gfx"
    info "Patch applied."
  else
    mv -f -- "${gfx}.orig" "$gfx"
    rm -f -- "${gfx}.new"
    die "AMDGPU CU-info layout changed in kernel $KVER_BASE; source was restored"
  fi
}

build_module() {
  local source="$1" amdgpu_dir kbuild trace_dst trace_copied=0 built
  amdgpu_dir="$source/drivers/gpu/drm/amd/amdgpu"
  kbuild="${MODDIR}/build"
  trace_dst="${kbuild}/drivers/gpu/drm/amd/amdgpu/amdgpu_trace.h"
  install -d -m0750 "$WORK_ROOT"
  if [[ ! -f "$trace_dst" ]]; then
    install -D -m0644 "$amdgpu_dir/amdgpu_trace.h" "$trace_dst"
    trace_copied=1
  fi

  info "Building AMDGPU for $KVER (first preparation normally takes 2-5 minutes)..."
  if ! make -C "$kbuild" M="$amdgpu_dir" -j"$(nproc)" modules 2>&1 | \
      tee "$BUILD_LOG" >&2; then
    ((trace_copied == 0)) || rm -f -- "$trace_dst"
    die "AMDGPU build failed; full log: $BUILD_LOG"
  fi
  ((trace_copied == 0)) || rm -f -- "$trace_dst"
  built="$amdgpu_dir/amdgpu.ko"
  [[ -f "$built" ]] || die "AMDGPU build did not produce $built"
  module_has_parameter "$built" || die "built module is missing bc250_cc_write_mode"
  module_vermagic_matches "$built" || \
    die "built module vermagic does not match the running kernel $KVER"
  info "Build completed: $(du -h "$built" | awk '{print $1}') before compression"
  printf '%s\n' "$built"
}

stock_backup_for() {
  local target="$1" backup
  shopt -s nullglob
  local backups=("${target}.bc250-backup-"*)
  shopt -u nullglob
  for backup in "${backups[@]}"; do
    module_blob_valid "$target" "$backup" || {
      warn "Ignoring unreadable AMDGPU backup: $backup"
      continue
    }
    if ! module_blob_has_parameter "$target" "$backup"; then
      printf '%s\n' "$backup"
      return
    fi
  done
  return 1
}

install_module() {
  local built="$1" target backup staged alternate
  target="$(module_target)"
  if module_has_parameter "$target"; then
    info "A patched module is already installed at $target"
    printf '%s\n' "$target"
    return
  fi

  backup="$(stock_backup_for "$target" 2>/dev/null || true)"
  if [[ -z "$backup" && -f "$target" ]]; then
    backup="${target}.bc250-backup-$(date +%Y%m%d-%H%M%S)"
    info "Saving the original Fedora module as $backup"
    cp --preserve=mode,timestamps -- "$target" "$backup"
  fi
  [[ -n "$backup" ]] || die "cannot install a replacement without a stock module backup"

  staged="${target}.bc250-new"
  rm -f -- "$staged"
  case "$target" in
    *.xz)
      info "Compressing the replacement module with parallel XZ..."
      xz --threads=0 -3 --check=crc32 --compress --stdout "$built" > "$staged"
      ;;
    *.zst)
      info "Compressing the replacement module with Zstandard..."
      zstd --threads=0 --force --quiet "$built" -o "$staged"
      ;;
    *) cp -- "$built" "$staged" ;;
  esac
  chmod --reference="$backup" "$staged" 2>/dev/null || chmod 0644 "$staged"
  mv -f -- "$staged" "$target"
  restorecon "$target" 2>/dev/null || true

  for alternate in "${MODPATH}.xz" "${MODPATH}.zst" "$MODPATH"; do
    [[ "$alternate" == "$target" || ! -f "$alternate" ]] || \
      { module_has_parameter "$alternate" && rm -f -- "$alternate" || true; }
  done
  module_has_parameter "$target" || die "installed module verification failed"
  info "Installed prepared module at $target"
  printf '%s\n' "$target"
}

refresh_initramfs() {
  install -d -m0755 "$(dirname -- "$DRACUT_CONF")"
  cat > "$DRACUT_CONF" <<'EOF_DRACUT'
# Ensure the prepared AMDGPU module, not a stale copy, is present in initramfs.
add_drivers+=" amdgpu "
EOF_DRACUT
  depmod -a "$KVER"
  info "Rebuilding the initramfs for $KVER..."
  dracut --force --kver "$KVER"
}

verify_initramfs() {
  local target="$1" temporary relative
  temporary="$(mktemp)"
  for relative in "${target#/}" "${target#/usr/}"; do
    : > "$temporary"
    if lsinitrd -k "$KVER" -f "$relative" > "$temporary" 2>/dev/null && \
        [[ -s "$temporary" ]] && module_blob_has_parameter "$target" "$temporary"; then
      rm -f -- "$temporary"
      info "Verified the patched module inside the $KVER initramfs."
      return
    fi
  done
  rm -f -- "$temporary"
  die "the rebuilt initramfs does not contain the prepared AMDGPU module; not ready to enable"
}

clean_build_objects() {
  local source="$1"
  make -s -C "${MODDIR}/build" \
    M="$source/drivers/gpu/drm/amd/amdgpu" clean >/dev/null 2>&1 || true
}

record_prepared() {
  local target="$1"
  install -d -m0750 "$STATE_DIR"
  printf 'kernel=%s\nmodule=%s\n' "$KVER" "$target" > "$STATE_DIR/prepared"
  chmod 0600 "$STATE_DIR/prepared"
}

prepared_module_ready() {
  local target="$1"
  [[ -f "$DRACUT_CONF" ]] &&
    module_has_parameter "$target" &&
    module_vermagic_matches "$target" &&
    (verify_initramfs "$target") >/dev/null 2>&1
}

do_prepare() {
  require_root
  check_bc250
  ensure_dependencies
  local target source built
  target="$(module_target)"

  if module_has_parameter "$target"; then
    module_vermagic_matches "$target" || \
      die "installed patched module does not match running kernel $KVER"
    check_module_authentication "$target"
    if [[ -f "$DRACUT_CONF" ]] && \
        (verify_initramfs "$target") >/dev/null 2>&1; then
      record_prepared "$target"
      info "AMDGPU and its initramfs copy are already prepared for $KVER."
      info "40-CU support remains disabled until: sudo bc250-40cu enable"
      return
    fi
    info "AMDGPU is already patched for $KVER; skipping download and compilation."
  else
    check_module_authentication
    source="$(find_source)"
    patch_source "$source"
    built="$(build_module "$source")"
    target="$(install_module "$built")"
    clean_build_objects "$source"
  fi

  refresh_initramfs
  module_has_parameter "$target" || die "prepared module verification failed"
  module_vermagic_matches "$target" || die "prepared module vermagic changed unexpectedly"
  verify_initramfs "$target"
  record_prepared "$target"
  info "40-CU support is prepared but remains disabled."
  info "Operator action when ready: sudo bc250-40cu enable"
}

do_enable() {
  require_root
  check_bc250
  local target
  target="$(module_target)"

  if ! prepared_module_ready "$target"; then
    info "The module is not prepared yet; preparing it now."
    do_prepare
    target="$(module_target)"
  fi
  check_module_authentication "$target"

  cat > "$CONF40" <<'EOF_CONF'
# Experimental BC-250 harvested-CU re-enablement.
options amdgpu bc250_cc_write_mode=3
EOF_CONF
  refresh_initramfs
  verify_initramfs "$target"
  info "40-CU mode is configured. Rebooting to load the prepared module..."
  sleep 2
  systemctl reboot
}

do_disable() {
  require_root
  rm -f -- "$CONF40"
  refresh_initramfs
  info "40-CU mode is disabled. Rebooting with patched module mode 0..."
  sleep 2
  systemctl reboot
}

do_restore() {
  require_root
  ensure_dependencies
  local target backup
  target="$(module_target)"
  backup="$(stock_backup_for "$target" 2>/dev/null || true)"
  [[ -n "$backup" ]] || die "no verifiable stock AMDGPU backup exists for $target"
  cp --preserve=mode,timestamps -- "$backup" "$target"
  rm -f -- "$CONF40" "$DRACUT_CONF"
  depmod -a "$KVER"
  dracut --force --kver "$KVER"
  info "Restored the Fedora AMDGPU module. Reboot to load it."
}

active_cus() {
  local line
  line="$(journalctl -k -b --no-pager 2>/dev/null | grep 'active_cu_number' | tail -1 || true)"
  grep -oE 'active_cu_number[ =]+[0-9]+' <<< "$line" | grep -oE '[0-9]+$' || true
}

show_load_failure_hint() {
  [[ -f "$CONF40" ]] || return
  [[ -d /sys/module/amdgpu ]] && \
    [[ -r /sys/module/amdgpu/parameters/bc250_cc_write_mode ]] && return
  echo
  warn "40-CU mode is configured, but the prepared module is not running."
  warn "Relevant kernel messages:"
  journalctl -k -b --no-pager 2>/dev/null | \
    grep -Ei 'amdgpu|module verification|lockdown|signature' | tail -20 | sed 's/^/    /' >&2 || true
}

do_status() {
  require_root
  local target installed running mode cus temporary_status initramfs="not checked"
  target="$(module_target)"
  module_has_parameter "$target" && installed="patched" || installed="stock"
  if [[ ! -d /sys/module/amdgpu ]]; then
    running="not loaded"
    mode="N/A"
  elif [[ -r /sys/module/amdgpu/parameters/bc250_cc_write_mode ]]; then
    running="patched"
    mode="$(cat /sys/module/amdgpu/parameters/bc250_cc_write_mode)"
  else
    running="stock"
    mode="N/A"
  fi
  if [[ "$installed" == patched ]]; then
    temporary_status=0
    (verify_initramfs "$target") >/dev/null 2>&1 || temporary_status=$?
    ((temporary_status == 0)) && initramfs="patched" || initramfs="missing/stale"
  fi
  cus="$(active_cus)"

  printf '=== BC-250 CU Status ===\n\n'
  lspci -Dnn 2>/dev/null | grep -Fi "[$BC250_PCI_ID]" >/dev/null && \
    printf '  PCI device:       BC-250 detected\n' || printf '  PCI device:       BC-250 not found\n'
  printf '  Installed module: %s (%s)\n' "$installed" "$target"
  printf '  Initramfs module: %s\n' "$initramfs"
  printf '  Running driver:   %s\n' "$running"
  printf '  write_mode:       %s\n' "$mode"
  [[ -n "$cus" ]] && printf '  Active CUs:       %s\n' "$cus" || \
    printf '  Active CUs:       not reported by this boot\n'
  [[ -f "$CONF40" ]] && printf '  Persistent mode:  enabled\n' || \
    printf '  Persistent mode:  disabled\n'
  show_load_failure_hint
}

do_verify() {
  do_status
  [[ -f "$CONF40" ]] || { info "Module preparation can be verified now; 40-CU activation is disabled."; return; }
  [[ -r /sys/module/amdgpu/parameters/bc250_cc_write_mode ]] || \
    die "configured replacement module is not running"
  [[ "$(cat /sys/module/amdgpu/parameters/bc250_cc_write_mode)" == 3 ]] || \
    die "replacement module is running without bc250_cc_write_mode=3"
  info "The prepared replacement module is active in mode 3."
}

usage() {
  cat <<EOF_USAGE
BC-250 40-CU replacement-module helper

Normal setup:
  sudo bc250-40cu enable     Explicitly enable 40-CU mode and reboot

Inspection and recovery:
  sudo bc250-40cu status     Distinguish installed, initramfs and running module
  sudo bc250-40cu verify     Verify the running mode after reboot
  sudo bc250-40cu disable    Return to mode 0 and reboot
  sudo bc250-40cu restore    Restore the original Fedora AMDGPU module

The guided appliance installer runs 'prepare' automatically. Repeated prepare
runs reuse ${SOURCE_ARCHIVE} and skip compilation when $KVER is ready.
EOF_USAGE
}

case "${1:-}" in
  prepare|build) do_prepare ;;
  enable) do_enable ;;
  disable) do_disable ;;
  restore) do_restore ;;
  status) do_status ;;
  verify) do_verify ;;
  -h|--help|help|"") usage ;;
  *) usage >&2; exit 2 ;;
esac

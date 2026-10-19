#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: kernel build-dependency provisioning must run as root (the build check itself remains non-root)." >&2
  exit 2
fi

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: GFX1013 kernel build-dependency provisioning requires Fedora." >&2
  exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ ${ID:-} != fedora ]]; then
  echo "ERROR: GFX1013 kernel build-dependency provisioning requires Fedora (found ${ID:-unknown})." >&2
  exit 2
fi

for command in dnf curl rpm mktemp; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "ERROR: required provisioning command is missing: $command" >&2
    exit 2
  }
done

if ! dnf builddep --help >/dev/null 2>&1; then
  echo "ERROR: dnf builddep is unavailable; install dnf5-plugins first." >&2
  exit 2
fi

mapfile -t builds < <(find /usr/src/kernels -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort)
requested_kernel="${BC250_GFX1013_KERNEL:-}"
running_kernel="$(uname -r)"

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

version="${kernel%%-*}"
release="${kernel#*-}"
release="${release%.*}"
expected_vr="${kernel%.*}"
srpm_url="${BC250_GFX1013_KERNEL_SRPM_URL:-https://kojipkgs.fedoraproject.org/packages/kernel/${version}/${release}/src/kernel-${version}-${release}.src.rpm}"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cache_root="${BC250_GFX1013_CACHE_ROOT:-$root/sources/gfx1013}"
mkdir -p "$cache_root"
srpm="$cache_root/kernel-${version}-${release}.src.rpm"
partial="${srpm}.part"

SRPM_VALIDATION_ERROR=''
validate_srpm() {
  local path=$1 actual_vr source_package rpm_verify
  SRPM_VALIDATION_ERROR=''
  actual_vr="$(rpm -qp --qf '%{VERSION}-%{RELEASE}\n' "$path" 2>/dev/null || true)"
  source_package="$(rpm -qp --qf '%{SOURCEPACKAGE}\n' "$path" 2>/dev/null || true)"
  if [[ "$actual_vr" != "$expected_vr" ]]; then
    SRPM_VALIDATION_ERROR="kernel source RPM identity mismatch: expected $expected_vr, got ${actual_vr:-unreadable}"
    return 1
  fi
  if [[ "$source_package" != 1 ]]; then
    SRPM_VALIDATION_ERROR='kernel package is not marked as a source RPM'
    return 1
  fi
  rpm_verify="$(LC_ALL=C rpm -K "$path" 2>&1)" || {
    SRPM_VALIDATION_ERROR="kernel source RPM failed RPM digest/signature verification: $rpm_verify"
    return 1
  }
  if grep -Eqi 'NOKEY|NOT OK' <<<"$rpm_verify"; then
    SRPM_VALIDATION_ERROR="kernel source RPM signature is not trusted: $rpm_verify"
    return 1
  fi
}

if [[ -f "$srpm" ]] && validate_srpm "$srpm"; then
  printf 'Using verified kernel SRPM cache: %s\n' "$srpm"
else
  [[ ! -e "$srpm" ]] || rm -f -- "$srpm"
  printf 'Acquiring exact kernel SRPM into build cache: %s\n' "$srpm"
  if ! curl --fail --location --retry 3 --retry-all-errors --retry-delay 2 --continue-at - --output "$partial" "$srpm_url"; then
    echo "ERROR: kernel SRPM download failed; resumable partial retained at $partial" >&2
    exit 2
  fi
  if ! validate_srpm "$partial"; then
    rm -f -- "$partial"
    echo "ERROR: $SRPM_VALIDATION_ERROR" >&2
    exit 2
  fi
  mv -f -- "$partial" "$srpm"
fi

# Use the exact source RPM's recorded BuildRequires rather than maintaining a
# partial hand-written dependency list.  DNF5 requires --srpm before the SRPM
# argument; this transaction is the only privileged part of the kernel gate.
dnf_log="$(mktemp)"
if ! dnf --disable-repo=fedora-cisco-openh264 -y builddep --srpm "$srpm" >"$dnf_log" 2>&1; then
  echo "ERROR: Fedora kernel build dependencies provisioning failed; DNF output follows:" >&2
  cat "$dnf_log" >&2
  rm -f -- "$dnf_log"
  exit 2
fi
rm -f -- "$dnf_log"

if [[ "$(rpm --eval '%{defined py3_shebang_fix}' 2>/dev/null || true)" != 1 ]]; then
  echo "ERROR: Fedora kernel build dependencies did not provide the %py3_shebang_fix RPM macro." >&2
  exit 2
fi

printf 'Fedora kernel build dependencies provisioned for %s from %s.\n' "$kernel" "$(basename "$srpm")"

#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: Mesa build-dependency provisioning must run as root (the build checks themselves remain non-root)." >&2
  exit 2
fi

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: GFX1013 Mesa build-dependency provisioning requires Fedora." >&2
  exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ ${ID:-} != fedora || ${VERSION_ID%%.*} != 44 ]]; then
  echo "ERROR: GFX1013 Mesa build-dependency provisioning requires Fedora 44 (found ${ID:-unknown} ${VERSION_ID:-unknown})." >&2
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

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
metadata="$root/gfx1013/upstream/MESA-SOURCE"
[[ -r "$metadata" ]] || { echo "ERROR: Mesa source metadata is missing: $metadata" >&2; exit 2; }
mesa_nevra="$(sed -n 's/^srpm_nevra=//p' "$metadata")"
mesa_url="$(sed -n 's/^srpm_url=//p' "$metadata")"
[[ -n "$mesa_nevra" && -n "$mesa_url" ]] || { echo "ERROR: Mesa source metadata is incomplete." >&2; exit 2; }
mesa_nevr="${mesa_nevra%.src}"
cache_root="${BC250_GFX1013_CACHE_ROOT:-$root/sources/gfx1013}"
mkdir -p "$cache_root"
srpm="$cache_root/${mesa_nevr}.src.rpm"
partial="${srpm}.part"
expected="$mesa_nevr"$'\n1'

SRPM_VALIDATION_ERROR=''
validate_srpm() {
  local path=$1 identity verify
  SRPM_VALIDATION_ERROR=''
  identity="$(rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}\n%{SOURCEPACKAGE}\n' "$path" 2>/dev/null || true)"
  if [[ "$identity" != "$expected" ]]; then
    SRPM_VALIDATION_ERROR="Fedora Mesa SRPM identity mismatch: expected $(printf %q "$expected"), got $(printf %q "$identity")"
    return 1
  fi
  verify="$(rpm -K "$path" 2>&1)" || {
    SRPM_VALIDATION_ERROR="Fedora Mesa SRPM signature verification failed: $verify"
    return 1
  }
  if [[ "$verify" == *"NOKEY"* || "$verify" == *"NOT OK"* ]]; then
    SRPM_VALIDATION_ERROR="Fedora Mesa SRPM signature verification failed: $verify"
    return 1
  fi
}

if [[ -f "$srpm" ]] && validate_srpm "$srpm"; then
  printf 'Using verified Mesa SRPM cache: %s\n' "$srpm"
else
  [[ ! -e "$srpm" ]] || rm -f -- "$srpm"
  printf 'Acquiring Fedora Mesa SRPM into build cache: %s\n' "$srpm"
  if ! curl --fail --location --retry 3 --retry-all-errors --retry-delay 2 --continue-at - \
    --proto '=https' --tlsv1.2 --output "$partial" "$mesa_url"; then
    echo "ERROR: Mesa SRPM download failed; resumable partial retained at $partial" >&2
    exit 2
  fi
  if ! validate_srpm "$partial"; then
    rm -f -- "$partial"
    echo "ERROR: $SRPM_VALIDATION_ERROR" >&2
    exit 2
  fi
  mv -f -- "$partial" "$srpm"
fi

dnf_log="$(mktemp)"
if ! dnf --disable-repo=fedora-cisco-openh264 -y builddep --srpm "$srpm" >"$dnf_log" 2>&1; then
  echo "ERROR: Fedora Mesa build dependencies provisioning failed; DNF output follows:" >&2
  cat "$dnf_log" >&2
  rm -f -- "$dnf_log"
  exit 2
fi
rm -f -- "$dnf_log"
echo "Fedora Mesa build dependencies provisioned from ${mesa_nevr}.src.rpm."

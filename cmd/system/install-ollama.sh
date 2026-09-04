#!/usr/bin/env bash
# Install the pinned official Ollama binary and restore the package-owned main service.
set -Eeuo pipefail
umask 0022

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo." >&2
  exit 1
}

runtime_env="${BC250_RUNTIME_ENV:-/usr/share/bc250-llm-server/runtime.env}"
if [[ ! -r "$runtime_env" ]]; then
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  runtime_env="$script_dir/../../config/runtime.env"
fi
[[ -r "$runtime_env" ]] || { echo "ERROR: runtime metadata missing: $runtime_env" >&2; exit 1; }
# shellcheck disable=SC1090
source "$runtime_env"
VERSION="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"
INSTALLER_COMMIT="${BC250_OLLAMA_INSTALLER_COMMIT:-}"
INSTALLER_SHA256="${BC250_OLLAMA_INSTALLER_SHA256:-}"
[[ "$INSTALLER_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: BC250_OLLAMA_INSTALLER_COMMIT must be a full lowercase Git commit." >&2
  exit 1
}
[[ "$INSTALLER_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "ERROR: BC250_OLLAMA_INSTALLER_SHA256 must be a lowercase SHA-256." >&2
  exit 1
}
URL="https://raw.githubusercontent.com/ollama/ollama/$INSTALLER_COMMIT/scripts/install.sh"

is_upstream_generated_unit() {
  local unit="$1"
  [[ -f "$unit" && ! -L "$unit" ]] || return 1
  awk '
    /^[[:space:]]*$/ || /^[[:space:]]*[#;]/ {next}
    $0 == "[Unit]" ||
    $0 == "Description=Ollama Service" ||
    $0 == "After=network-online.target" ||
    $0 == "[Service]" ||
    $0 == "ExecStart=/usr/local/bin/ollama serve" ||
    $0 == "ExecStart=/usr/bin/ollama serve" ||
    $0 == "User=ollama" ||
    $0 == "Group=ollama" ||
    $0 == "Restart=always" ||
    $0 == "RestartSec=3" ||
    $0 ~ /^Environment="PATH=[^"]*"$/ ||
    $0 == "[Install]" ||
    $0 == "WantedBy=default.target" ||
    $0 == "WantedBy=multi-user.target" {next}
    {bad=1}
    END {exit bad}
  ' "$unit" || return 1
  grep -Fxq 'Description=Ollama Service' "$unit" &&
    grep -Eq '^ExecStart=/(usr/local|usr)/bin/ollama serve$' "$unit" &&
    grep -Fxq 'User=ollama' "$unit" &&
    grep -Fxq 'Group=ollama' "$unit"
}

etc_unit=/etc/systemd/system/ollama.service
package_unit=/usr/lib/systemd/system/ollama.service
if [[ -e "$etc_unit" || -L "$etc_unit" ]]; then
  is_upstream_generated_unit "$etc_unit" || {
    echo "ERROR: refusing to run the upstream Ollama installer while a custom service override exists: $etc_unit" >&2
    exit 1
  }
fi

confirm_install() {
  local action="$1" answer
  [[ "${BC250_ASSUME_YES:-0}" == 1 ]] && return 0
  [[ -t 0 ]] || {
    echo "ERROR: confirmation requires a terminal; set BC250_ASSUME_YES=1 for unattended use." >&2
    return 1
  }
  read -r -p "$action Ollama ${VERSION}? [y/N]: " answer
  case "${answer,,}" in
    y|yes) return 0 ;;
    *) return 1 ;;
  esac
}

run_installer=0
if command -v ollama >/dev/null 2>&1; then
  installed_version="$(ollama --version 2>/dev/null | awk '{print $NF}' || true)"
  installed_version="${installed_version#v}"
  if [[ "$VERSION" != latest && "$installed_version" == "${VERSION#v}" && \
        "${OLLAMA_REINSTALL:-0}" != 1 ]]; then
    echo "Requested Ollama version is already installed: $installed_version"
  elif confirm_install "Install or update to"; then
    run_installer=1
  else
    echo "Keeping installed Ollama: ${installed_version:-unknown version}"
  fi
elif confirm_install "Install"; then
  run_installer=1
else
  echo "Cancelled."
  exit 0
fi

if ((run_installer)); then
  printf 'Downloading the commit-pinned official Ollama installer from %s\n' "$URL"
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  curl --fail --silent --show-error --location --retry 3 "$URL" -o "$tmp"
  actual_sha256="$(sha256sum "$tmp" | awk '{print $1}')"
  if [[ "$actual_sha256" != "$INSTALLER_SHA256" ]]; then
    echo "ERROR: Ollama installer SHA-256 mismatch." >&2
    echo "  expected: $INSTALLER_SHA256" >&2
    echo "  actual:   $actual_sha256" >&2
    exit 1
  fi
  echo "Verified Ollama installer SHA-256: $actual_sha256"
  chmod 0700 "$tmp"

  if [[ "$VERSION" == "latest" ]]; then
    # Upstream treats every non-empty OLLAMA_VERSION as a URL query. Passing
    # the literal value "latest" therefore requests a nonexistent asset.
    env -u OLLAMA_VERSION sh "$tmp"
  else
    OLLAMA_VERSION="$VERSION" sh "$tmp"
  fi
fi

command -v ollama >/dev/null 2>&1 || {
  echo "ERROR: no ollama command was found." >&2
  exit 1
}
getent group ollama >/dev/null || groupadd -r ollama
id ollama >/dev/null 2>&1 || \
  useradd -r -g ollama -d /var/lib/ollama -s /usr/sbin/nologin -M ollama

for group in render video; do
  getent group "$group" >/dev/null && usermod -a -G "$group" ollama
done

install -d -o root -g ollama -m 0750 \
  /var/lib/bc250-llm-server /var/cache/bc250-llm-server
install -d -o ollama -g ollama -m 0750 \
  /var/lib/ollama \
  /var/lib/bc250-llm-server/ollama/{main,task,embedding,agent} \
  /var/lib/bc250-llm-server/gguf/{production,experiments,task,embedding,agent} \
  /var/cache/bc250-llm-server/huggingface
restorecon -RF /var/lib/ollama /var/lib/bc250-llm-server \
  /var/cache/bc250-llm-server 2>/dev/null || true

# The upstream installer owns binary installation only. Normalize the service
# back to the RPM-owned unit and refuse any unexpected /etc override.
[[ -r "$package_unit" ]] || {
  echo "ERROR: package-owned Ollama service is missing: $package_unit" >&2
  exit 1
}
if [[ -e "$etc_unit" || -L "$etc_unit" ]]; then
  is_upstream_generated_unit "$etc_unit" || {
    echo "ERROR: upstream Ollama installation left an unexpected service override: $etc_unit" >&2
    exit 1
  }
  rm -f -- "$etc_unit"
fi

systemctl daemon-reload
fragment="$(systemctl show -p FragmentPath --value ollama.service 2>/dev/null || true)"
[[ "$fragment" == "$package_unit" ]] || {
  echo "ERROR: ollama.service is not using the package-owned unit: ${fragment:-unknown}" >&2
  exit 1
}
systemctl reenable ollama.service >/dev/null
systemctl restart ollama.service

for _ in {1..30}; do
  if curl --fail --silent \
      --connect-timeout 2 http://127.0.0.1:11434/api/tags >/dev/null; then
    ollama --version
    echo "Ollama API is ready at http://127.0.0.1:11434."
    exit 0
  fi
  sleep 1
done

systemctl status ollama.service --no-pager -l || true
journalctl -u ollama.service -b --no-pager -n 80 || true
echo "ERROR: Ollama did not become reachable on 127.0.0.1:11434." >&2
exit 1

#!/usr/bin/env bash
# Optional helper for installing or normalizing the official Ollama service.
set -Eeuo pipefail
umask 0022

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo." >&2
  exit 1
}

VERSION="${OLLAMA_VERSION:-latest}"
URL="https://ollama.com/install.sh"

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
  printf 'Downloading the official Ollama installer from %s\n' "$URL"
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  curl --fail --silent --show-error --location --retry 3 "$URL" -o "$tmp"
  echo "Installer SHA-256: $(sha256sum "$tmp" | awk '{print $1}')"
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
  /var/lib/bc250-llm-server/ollama/main \
  /var/lib/bc250-llm-server/gguf/production \
  /var/cache/bc250-llm-server/huggingface
restorecon -RF /var/lib/ollama /var/lib/bc250-llm-server \
  /var/cache/bc250-llm-server 2>/dev/null || true

systemctl daemon-reload
systemctl enable ollama.service
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

#!/usr/bin/env bash
# Optional helper for installing or normalizing the official Ollama service.
set -Eeuo pipefail
umask 0022

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo." >&2
  exit 1
}

VERSION="${OLLAMA_VERSION:-0.32.1}"
URL="https://ollama.com/install.sh"

if ! command -v ollama >/dev/null 2>&1; then
  printf 'This downloads and runs the official Ollama installer from %s\n' "$URL"
  read -r -p "Install Ollama ${VERSION}? [y/N]: " answer
  case "${answer,,}" in
    y|yes) ;;
    *) echo "Cancelled."; exit 0 ;;
  esac

  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  curl --fail --silent --show-error --location --retry 3 "$URL" -o "$tmp"
  echo "Installer SHA-256: $(sha256sum "$tmp" | awk '{print $1}')"
  chmod 0700 "$tmp"

  if [[ "$VERSION" == "latest" ]]; then
    sh "$tmp"
  else
    OLLAMA_VERSION="$VERSION" sh "$tmp"
  fi
else
  echo "Ollama is already installed: $(ollama --version 2>/dev/null || command -v ollama)"
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

install -d -o root -g ollama -m 0750 /var/llm
install -d -o ollama -g ollama -m 0750 \
  /var/lib/ollama /var/llm/ollama /var/llm/gguf /var/llm/hf-cache
restorecon -RF /var/lib/ollama /var/llm 2>/dev/null || true

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

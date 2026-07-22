#!/usr/bin/env bash
set -Eeuo pipefail

helper="/usr/libexec/bc250-llm-server/40cu/bc250-enable-40cu-fedora.sh"
status_helper="/usr/bin/bc250-cu-status"
manager="/usr/bin/bc250-cu-live-manager"

usage_extra() {
  cat <<'USAGE'
Additional package commands:
  bc250-40cu
      Open the bundled interactive live CU manager.

  bc250-40cu verify
      Verify the replacement module, then show kernel enumeration, RADV
      information and live-manager CU routing.

  bc250-40cu health-test [OLLAMA_MODEL]
      Run CU status, Vulkan initialization, sensors and optionally three short
      Ollama generations. This is a smoke test, not proof every CU is good.

  bc250-40cu live-status
  bc250-40cu live-full
  bc250-40cu live-stock
      Call the bundled pinned live manager.

  bc250-40cu mask WGP_ID [WGP_ID ...]
  bc250-40cu unmask WGP_ID [WGP_ID ...]
      Disable or enable selected WGP pairs. IDs use SE.SH.WGP notation.

Clock and voltage policy belongs entirely to the operator. This wrapper does
not inspect, limit or alter the governor configuration.

The guided installer prepares the matching kernel module and initramfs. The
only activation step is: sudo bc250-40cu enable
USAGE
}

require_live_manager() {
  [[ -x "$manager" ]] || {
    echo "ERROR: the packaged CU live manager is missing: $manager" >&2
    exit 1
  }
}

health_test() {
  local model="${1:-}"
  "$status_helper" || true
  echo
  echo "Vulkan initialization:"
  vulkaninfo --summary >/dev/null && echo "  [ OK ] vulkaninfo completed" || {
    echo "  [FAIL] vulkaninfo failed" >&2
    return 1
  }
  echo
  sensors 2>/dev/null | grep -Ei 'edge:|junction:|mem:|power1:' | head -20 || true

  if [[ -n "$model" ]]; then
    command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required." >&2; return 1; }
    for run in 1 2 3; do
      payload="$(jq -nc --arg model "$model" --arg prompt "Return exactly: CU smoke test $run OK" \
        '{model:$model,prompt:$prompt,stream:false,keep_alive:"2m",options:{num_predict:24}}')"
      echo "Ollama smoke test $run/3:"
      curl -fsS --max-time 900 -H 'Content-Type: application/json' \
        -d "$payload" http://127.0.0.1:11434/api/generate | jq -r '.response // .error'
    done
  else
    echo "No Ollama model supplied; generation tests skipped."
  fi
  echo "Repeat a representative benchmark and compare output correctness before persistence."
}

command="${1:-}"
case "$command" in
  ""|menu)
    require_live_manager
    exec "$manager" menu
    ;;
  verify)
    "$helper" verify
    echo
    exec "$status_helper"
    ;;
  health-test)
    shift
    health_test "${1:-}"
    ;;
  live-status)
    require_live_manager
    exec "$manager" status
    ;;
  live-full)
    require_live_manager
    exec "$manager" enable all
    ;;
  live-stock)
    require_live_manager
    exec "$manager" stock-dispatch
    ;;
  mask|unmask)
    action="$command"
    shift
    (($# > 0)) || { echo "ERROR: provide at least one WGP ID, e.g. 1.0.4" >&2; exit 2; }
    require_live_manager
    [[ "$action" == mask ]] && manager_command=disable-wgp || manager_command=enable-wgp
    printf '%s selected WGP pair(s): %s\n' "$action" "$*"
    read -r -p "Type APPLY-WGP-TABLE to continue: " answer
    [[ "$answer" == APPLY-WGP-TABLE ]] || { echo "Cancelled."; exit 0; }
    for wgp in "$@"; do
      "$manager" "$manager_command" "$wgp"
    done
    "$manager" status
    ;;
  enable)
    [[ -x "$helper" ]] || { echo "ERROR: 40-CU helper is missing." >&2; exit 1; }
    printf 'This will enable experimental harvested CUs and reboot the host.\n'
    read -r -p "Type ENABLE-40CU to continue: " answer
    [[ "$answer" == ENABLE-40CU ]] || { echo "Cancelled."; exit 0; }
    exec "$helper" "$@"
    ;;
  prepare)
    [[ -x "$helper" ]] || { echo "ERROR: 40-CU helper is missing." >&2; exit 1; }
    exec "$helper" prepare
    ;;
  help-extra)
    usage_extra
    ;;
  *)
    [[ -x "$helper" ]] || { echo "ERROR: 40-CU helper is missing." >&2; exit 1; }
    exec "$helper" "$@"
    ;;
esac

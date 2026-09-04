#!/usr/bin/env bash
# Guided Fedora setup. CU activation and maintenance scheduling remain separate.
set -Eeuo pipefail
umask 0022

readonly SCRIPT_PATH="$(readlink -f -- "${BASH_SOURCE[0]}")"
readonly ORIGINAL_ARGS=("$@")
readonly LOG_FILE="${BC250_INSTALL_LOG:-/var/log/bc250-llm-install.log}"
runtime_env="${BC250_RUNTIME_ENV:-/usr/share/bc250-llm-server/runtime.env}"
if [[ ! -r "$runtime_env" ]]; then
  runtime_env="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../../config/runtime.env"
fi
[[ -r "$runtime_env" ]] || { echo "ERROR: runtime metadata missing: $runtime_env" >&2; exit 1; }
# shellcheck disable=SC1090
source "$runtime_env"
INSTALL_MODE="full"
HF_AUTH_PREPARED=0

usage() {
  cat <<'USAGE'
Usage: sudo bc250-install [--models-only]

Before 1.0 this is a pre-1.0 greenfield appliance setup. Apply or resume the packaged BC-250 setup. The command checks current
state, avoids completed work where practical, applies the TTM/swap baseline,
prepares optional 40-CU support for the exact running kernel, offers one unified
model selection, configures Open WebUI, and verifies the result.

A normal update has one primary reboot after Fedora/kernel + memory setup. A
second reboot is requested only when persistent 40-CU mode is already configured
and a newly prepared replacement module is not yet running.

Use --models-only to reconcile runtime topology, models and Open WebUI without system/kernel setup.
Set BC250_MODEL_SELECTION for unattended model selection; Enter skips models.
Set BC250_UPDATE_OLLAMA=1 to refresh official Ollama explicitly.
USAGE
}
parse_arguments() {
  while (($#)); do
    case "$1" in
      --models-only) INSTALL_MODE="models" ;;
      -h|--help) usage; exit 0 ;;
      *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
  done
}
require_root() {
  [[ ${EUID} -eq 0 ]] || {
    echo "ERROR: run this installer with sudo." >&2
    exit 1
  }
}

require_progress_terminal() {
  command -v script >/dev/null 2>&1 || {
    echo "ERROR: /usr/bin/script is required (Fedora package: util-linux-script)." >&2
    exit 1
  }
}

capture_input_mode() {
  # Preserve the caller's real stdin mode before util-linux `script` can wrap
  # the installer in a pseudo-terminal. This keeps unattended installs
  # unattended even when stdout is a terminal and a transcript PTY is used.
  if [[ -z "${BC250_INPUT_INTERACTIVE+x}" ]]; then
    if [[ -t 0 ]]; then
      export BC250_INPUT_INTERACTIVE=1
    else
      export BC250_INPUT_INTERACTIVE=0
    fi
  fi
  [[ "${BC250_INPUT_INTERACTIVE}" == 0 || "${BC250_INPUT_INTERACTIVE}" == 1 ]] || {
    echo "ERROR: BC250_INPUT_INTERACTIVE must be 0 or 1." >&2
    exit 2
  }
}

input_is_interactive() {
  if [[ -n "${BC250_INPUT_INTERACTIVE+x}" ]]; then
    [[ "${BC250_INPUT_INTERACTIVE}" == 1 ]]
  else
    [[ -t 0 ]]
  fi
}

start_transcript() {
  install -d -m0755 "$(dirname -- "$LOG_FILE")"
  touch "$LOG_FILE"
  chmod 0600 "$LOG_FILE"

  # A pseudo-terminal keeps Hugging Face and Ollama progress bars visible while
  # preserving the installation transcript. BC250_INPUT_INTERACTIVE records the
  # original stdin mode, so this wrapper cannot accidentally make a pipe or
  # /dev/null look interactive to the child.
  if [[ "${BC250_INSTALL_TRANSCRIPT:-0}" != 1 && -t 1 ]] && command -v script >/dev/null 2>&1; then
    local command
    printf -v command '%q ' \
      env BC250_INSTALL_TRANSCRIPT=1 \
      BC250_INPUT_INTERACTIVE="$BC250_INPUT_INTERACTIVE" \
      bash "$SCRIPT_PATH" "${ORIGINAL_ARGS[@]}"
    exec script --quiet --return --append --command "$command" "$LOG_FILE"
  fi
  if [[ "${BC250_INSTALL_TRANSCRIPT:-0}" != 1 ]]; then
    exec > >(tee -a "$LOG_FILE") 2>&1
  fi
}

heading() {
  printf '\n===== %s =====\n' "$1"
}

yes_no() {
  local prompt="$1" answer
  if [[ "${BC250_ASSUME_YES:-0}" == 1 ]]; then
    return 0
  fi
  input_is_interactive || return 1
  read -r -p "$prompt [y/N]: " answer
  [[ "${answer,,}" == y || "${answer,,}" == yes ]]
}

yes_no_default_yes() {
  local prompt="$1" answer
  if [[ "${BC250_ASSUME_YES:-0}" == 1 ]]; then
    return 0
  fi
  input_is_interactive || return 1
  read -r -p "$prompt [Y/n]: " answer
  [[ -z "$answer" || "${answer,,}" == y || "${answer,,}" == yes ]]
}

rerun_command() {
  local command
  printf -v command '%q ' sudo bc250-install "${ORIGINAL_ARGS[@]}"
  printf '%s\n' "$command"
}

step_1_grow_root_filesystem() {
  heading "1. GROW ROOT FILESYSTEM"
  local source fstype
  source="$(findmnt -nro SOURCE /)"
  fstype="$(findmnt -nro FSTYPE /)"
  echo "Root filesystem: $source ($fstype)"

  if command -v lvs >/dev/null && lvs "$source" >/dev/null 2>&1; then
    local vg free
    vg="$(lvs --noheadings -o vg_name "$source" | xargs)"
    free="$(vgs --noheadings --units b --nosuffix -o vg_free "$vg" | awk '{printf "%.0f", $1}')"
    if [[ "$free" =~ ^[0-9]+$ ]] && ((free > 4 * 1024 * 1024)); then
      lvextend --resizefs --extents +100%FREE "$source"
    else
      echo "Root LV already uses available volume-group space."
    fi
    return
  fi

  case "$fstype" in
    xfs)
      command -v xfs_growfs >/dev/null || dnf install -y xfsprogs
      xfs_growfs / || echo "NOTE: XFS may already fill its device."
      ;;
    ext2|ext3|ext4)
      command -v resize2fs >/dev/null || dnf install -y e2fsprogs
      resize2fs "$source" || echo "NOTE: ext filesystem may already fill its device."
      ;;
    btrfs)
      command -v btrfs >/dev/null || dnf install -y btrfs-progs
      btrfs filesystem resize max / || echo "NOTE: Btrfs may already fill its device."
      ;;
    *) echo "NOTE: no automatic grow operation is defined for $fstype." ;;
  esac
}

pending_kernel() {
  local running newest
  running="$(uname -r)"
  newest="$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-core 2>/dev/null | sort -V | tail -1)"
  [[ -n "$newest" && "$newest" != "$running" ]] && printf '%s' "$newest"
}

request_primary_reboot_if_needed() {
  local kernel=""
  kernel="$(pending_kernel || true)"
  if [[ -z "$kernel" ]] && bc250-memory-profile status --quiet >/dev/null 2>&1; then
    return 0
  fi
  echo
  echo "One primary reboot is required before kernel-specific setup."
  [[ -z "$kernel" ]] || echo "  pending kernel: $kernel (running $(uname -r))"
  bc250-memory-profile status --quiet >/dev/null 2>&1 || echo "  TTM profile: configured, not active"
  echo "  sudo reboot"
  printf '  '; rerun_command
  echo "Transcript: $LOG_FILE"
  exit 10
}

step_2_update_fedora() {
  heading "2. UPDATE FEDORA"
  local rc=0
  dnf check-upgrade --refresh >/dev/null 2>&1 || rc=$?
  case "$rc" in
    0) echo "Fedora packages already current." ;;
    100) dnf upgrade -y ;;
    *) echo "ERROR: dnf update check failed (rc=$rc)." >&2; return "$rc" ;;
  esac
}

remove_fedora_ollama() {
  rpm -q ollama >/dev/null 2>&1 || return 0
  local blockers=""
  if ! blockers="$(rpm -e --test ollama 2>&1)"; then
    echo "ERROR: Fedora's Ollama package cannot be removed safely:" >&2
    printf '%s\n' "$blockers" >&2
    echo "Refusing to install a second Ollama copy." >&2
    return 1
  fi
  echo "Removing Fedora's Ollama package and unused dependencies."
  dnf remove -y ollama
  hash -r
  systemctl daemon-reload
}

ollama_version() {
  "$1" --version 2>/dev/null | awk '{print $NF}' | sed 's/^v//'
}

step_3_install_ollama() {
  heading "3. INSTALL OFFICIAL OLLAMA"
  local requested
  requested="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"
  export PATH="/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:$PATH"
  hash -r
  remove_fedora_ollama
  echo "Reconciling official Ollama ${requested} with the package-owned main service."
  BC250_ASSUME_YES=1 OLLAMA_VERSION="$requested" OLLAMA_REINSTALL="${BC250_UPDATE_OLLAMA:-0}" bc250-install-ollama
  hash -r
}

step_4_memory_and_swap() {
  heading "4. ENSURE MEMORY AND SWAP PROFILES"
  rpm -q zram-generator >/dev/null 2>&1 || dnf install -y zram-generator
  bc250-memory-profile ensure
  bc250-swap-profile ensure
}

prepare_hf_authentication() {
  ((HF_AUTH_PREPARED == 0)) || return 0
  [[ -z "${HF_TOKEN:-}" ]] || {
    echo "Using HF_TOKEN supplied in the environment."
    HF_AUTH_PREPARED=1
    return
  }
  [[ "${BC250_HF_ANONYMOUS:-0}" != 1 ]] || {
    echo "Using anonymous Hugging Face downloads."
    HF_AUTH_PREPARED=1
    return
  }
  if [[ "${BC250_ASSUME_YES:-0}" == 1 ]] || ! input_is_interactive; then
    echo "HF_TOKEN is unset; using anonymous Hugging Face downloads."
    export BC250_HF_ANONYMOUS=1
    HF_AUTH_PREPARED=1
    return 0
  fi
  local token=""
  read -r -s -p "HF_TOKEN (optional; Enter for anonymous downloads): " token
  echo
  if [[ -n "$token" ]]; then
    export HF_TOKEN="$token"
    unset BC250_HF_ANONYMOUS || true
  else
    export BC250_HF_ANONYMOUS=1
  fi
  HF_AUTH_PREPARED=1
}

step_5_prepare_40cu() {
  heading "5. PREPARE OPTIONAL 40-CU SUPPORT"
  local kernel
  kernel="$(uname -r)"
  echo "Installing build files for the exact running kernel: $kernel"
  dnf install -y "kernel-devel-$kernel"
  bc250-40cu prepare
  if [[ -f /etc/modprobe.d/bc250-40cu.conf ]]; then
    echo "Persistent 40-CU mode is configured."
    if [[ ! -r /sys/module/amdgpu/parameters/bc250_cc_write_mode ]]; then
      echo "The prepared persistent AMDGPU module needs one activation reboot."
      echo "  sudo reboot"
      printf '  '; rerun_command
      exit 12
    fi
  fi
}

step_6_runtime_topology() {
  heading "6. ESTABLISH OLLAMA RUNTIME TOPOLOGY"
  local unit fragment
  systemctl daemon-reload
  for unit in ollama.service ollama-task.service ollama-embedding.service ollama-agent.service; do
    systemctl cat "$unit" >/dev/null 2>&1 || {
      echo "ERROR: required package unit is missing: $unit" >&2
      return 1
    }
    fragment="$(systemctl show -p FragmentPath --value "$unit" 2>/dev/null || true)"
    if [[ "$fragment" != "/usr/lib/systemd/system/$unit" ]]; then
      echo "ERROR: $unit is overridden by ${fragment:-an unknown unit file}." >&2
      echo "This pre-1.0 greenfield release requires the package-owned static lane unit." >&2
      return 1
    fi
  done
  systemctl enable ollama.service ollama-task.service ollama-embedding.service
  systemctl disable ollama-agent.service >/dev/null 2>&1 || true
  bc250-agent-mode leave
}

step_7_models() {
  heading "7. MODELS"
  require_progress_terminal
  prepare_hf_authentication

  echo "Ensuring baseline Open WebUI infrastructure models."
  bc250-model install all \
    "task-gemma3-1b-unsloth-ud-q4-k-xl,embed-jina-v5-small-retrieval-q4-k-m"

  echo
  echo "Optional production, experiment, agent and additional model selection:"
  bc250-model list all --all
  local selection="${BC250_MODEL_SELECTION:-}"
  if input_is_interactive && [[ "${BC250_ASSUME_YES:-0}" != 1 ]]; then
    read -r -p "Additional models (index/range/name/recommended/production/all; Enter to skip): " selection
  elif [[ -z "$selection" ]]; then
    echo "BC250_MODEL_SELECTION is unset; no additional models selected in non-interactive mode."
    echo "Baseline task + embedding models are installed."
    return 0
  fi
  [[ -n "$selection" ]] || { echo "Skipping additional models; baseline models are installed."; return 0; }
  bc250-model install all "$selection" --include-disabled
  echo "RAG source documents remain operator-managed under /srv/bc250-documents/."
}

enable_open_webui_boot() {
  local source="${BC250_OWUI_ENABLE_SOURCE:-/usr/share/bc250-llm-server/openwebui/open-webui-enable.conf}"
  local target="${BC250_OWUI_ENABLE_DROPIN:-/etc/containers/systemd/open-webui.container.d/90-enable.conf}"
  [[ -r "$source" ]] || {
    echo "ERROR: Open WebUI enablement template is missing: $source" >&2
    return 1
  }
  install -D -m0644 "$source" "$target"
  systemctl daemon-reload
}

step_8_application_services() {
  heading "8. START APPLICATION SERVICES"
  systemctl enable --now firewalld.service cyan-skillfish-governor-smu.service
  if systemctl is-active --quiet firewalld.service; then
    firewall-cmd --quiet --permanent --add-service=http
    firewall-cmd --quiet --reload
  fi
  command -v setsebool >/dev/null 2>&1 && setsebool -P httpd_can_network_connect 1 || true
  enable_open_webui_boot
  systemctl start tika.service open-webui.service
  systemctl enable --now nginx.service
}


show_plan() {
  heading "BC-250 SETUP PLAN"
  local kernel="" memory="active" swap="pending" cu="prepare for $(uname -r)" ollama="install/update" reboot="no"
  kernel="$(pending_kernel || true)"
  bc250-memory-profile status --quiet >/dev/null 2>&1 || memory="configure/pending reboot"
  bc250-swap-profile status --quiet >/dev/null 2>&1 && swap="configured"
  if [[ -x /usr/local/bin/ollama ]] && [[ "$(ollama_version /usr/local/bin/ollama)" == "$BC250_OLLAMA_VERSION" ]]; then
    ollama="current ($BC250_OLLAMA_VERSION)"
  fi
  if [[ -r /var/lib/bc250-llm-server/40cu/prepared ]] &&
      grep -Fxq "kernel=$(uname -r)" /var/lib/bc250-llm-server/40cu/prepared; then
    cu="prepared for running kernel"
  fi
  [[ -z "$kernel" && "$memory" == active ]] || reboot="yes: kernel/TTM activation"
  printf '  root grow             check/apply if needed\n'
  printf '  Fedora update         check/apply\n'
  printf '  package               %s\n' "$(rpm -q bc250-llm-server.x86_64 2>/dev/null || echo missing)"
  printf '  Ollama                %s\n' "$ollama"
  printf '  kernel                %s\n' "${kernel:+pending -> $kernel}${kernel:-current}"
  printf '  TTM profile           %s\n' "$memory"
  printf '  swap                  %s\n' "$swap"
  printf '  40-CU                 %s\n' "$cu"
  printf '  storage headroom      %s available\n' "$(df -h --output=avail /var/lib/bc250-llm-server 2>/dev/null | awk 'NR==2{print $1}' || echo unknown)"
  printf '  models                baseline task+embedding + one optional selection\n'
  printf '  Open WebUI            start after models, then apply/status\n'
  printf '  primary reboot        %s\n' "$reboot"
}

wait_for_open_webui() {
  local attempt
  for attempt in {1..60}; do
    curl -fsS --connect-timeout 2 --max-time 3 http://127.0.0.1:3000/ >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

step_9_open_webui() {
  heading "9. CONFIGURE OPEN WEBUI"
  command -v bc250-openwebui-setup >/dev/null 2>&1 || {
    echo "Open WebUI setup helper is unavailable; skipping application configuration."
    return 0
  }
  if ! wait_for_open_webui; then
    echo "Open WebUI is not reachable on 127.0.0.1:3000; configure it later with:"
    echo "  sudo bc250-openwebui-setup init"
    return 0
  fi

  if [[ -n "${OWUI_API_KEY:-}" ]]; then
    echo "Applying the package-owned Open WebUI baseline with OWUI_API_KEY from the environment."
    if ! bc250-openwebui-setup apply; then
      echo "WARNING: Open WebUI API setup failed; no credentials were stored." >&2
      echo "Retry later with: sudo bc250-openwebui-setup init" >&2
    fi
    return 0
  fi

  if [[ "${BC250_ASSUME_YES:-0}" == 1 ]] || ! input_is_interactive; then
    echo "Non-interactive install: Open WebUI administrator setup was not attempted."
    echo "Run later in an interactive terminal:"
    echo "  sudo bc250-openwebui-setup init"
    return 0
  fi

  if yes_no_default_yes "Configure package-owned Open WebUI providers, tasks, RAG and model presets now?"; then
    if ! bc250-openwebui-setup init; then
      echo "WARNING: Open WebUI API setup was not completed; the appliance remains usable." >&2
      echo "Retry later with: sudo bc250-openwebui-setup init" >&2
    fi
  else
    echo "Skipped. Run later with: sudo bc250-openwebui-setup init"
  fi
}

step_10_verify() {
  heading "10. VERIFICATION"
  local verify_status=0 diagnose_status=0
  bc250-memory-profile status
  bc250-swap-profile status
  bc250-cu-status
  bc250-verify || verify_status=$?
  llm-run-diagnose --no-load || diagnose_status=$?
  if ((verify_status != 0 || diagnose_status != 0)); then
    echo "ERROR: verification reported failures; review both reports above." >&2
    return 1
  fi
}

run_models_only() {
  command -v bc250-model >/dev/null 2>&1 || {
    echo "ERROR: bc250-model is unavailable; install the binary RPM first." >&2
    exit 1
  }
  step_6_runtime_topology
  step_7_models
  step_8_application_services
  step_9_open_webui
  echo
  echo "Model and Open WebUI reconciliation completed."
  echo "Transcript: $LOG_FILE"
}

main() {
  parse_arguments "$@"
  require_root
  capture_input_mode
  start_transcript
  if [[ "$INSTALL_MODE" == models ]]; then
    run_models_only
    return
  fi
  show_plan
  step_1_grow_root_filesystem
  step_2_update_fedora
  step_3_install_ollama
  step_4_memory_and_swap
  request_primary_reboot_if_needed
  step_5_prepare_40cu
  step_6_runtime_topology
  step_7_models
  step_8_application_services
  step_9_open_webui
  step_10_verify
  echo
  echo "Installation and verification completed."
  echo "Transcript: $LOG_FILE"
  if [[ -f /etc/modprobe.d/bc250-40cu.conf ]]; then
    echo "Persistent 40-CU mode is configured; maintenance timers were not changed."
  else
    echo "40-CU support is prepared but disabled; maintenance timers were not changed."
  fi
  echo "Optional CU experiment/inspection: sudo bc250-40cu status"
  echo "Open WebUI initialization: sudo bc250-openwebui-setup init"
  echo "Open WebUI desired-state status: bc250-openwebui-setup status"
  echo "Exclusive coding mode: sudo bc250-agent-mode enter; leave with sudo bc250-agent-mode leave"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

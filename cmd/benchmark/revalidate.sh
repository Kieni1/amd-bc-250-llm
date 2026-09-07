#!/usr/bin/env bash
# BC-250 package revalidation harness v4.0
#
# Intended target: bc250-llm-server 0.11.0 on Fedora 44; release suffix is not hard-coded.
# `start` launches one systemd-owned qualification worker. Routine revalidation
# exercises packaged defaults only; tuning and hardware A/B decisions are explicit
# benchmark/diagnostic work. Per-phase reports are retained and exclusive-agent state
# is restored on every exit. Supplied OWUI credentials remain under /run and are never bundled.
set -Eeuo pipefail
umask 0077

HARNESS_VERSION=4.0
TARGET_VERSION=0.11.0
TARGET_RELEASE_PREFIX=${TARGET_RELEASE_PREFIX:-}
HARDWARE_PCI_ID=1002:13fe

STATE_ROOT=/var/lib/bc250-llm-server/revalidation
WORK=$STATE_ROOT/work
REPORT_DIR=$STATE_ROOT/results
RUN_DIR=/run/bc250-llm-server/revalidation
UNIT=bc250-revalidation.service
UNIT_PATH=/etc/systemd/system/$UNIT
LOCK=/run/lock/bc250-llm-server-revalidation.lock
HARNESS_COPY=$WORK/harness.sh

PHASE_FILE=$WORK/phase
STAGE_FILE=$WORK/stage
LAST_EVENT_FILE=$WORK/last-event
STAGE_STARTED_FILE=$WORK/stage-started
RUN_STATE_FILE=$WORK/run-state
INFRA_STATE_FILE=$WORK/infrastructure-state
QUALITY_STATE_FILE=$WORK/quality-state
RESTORATION_STATE_FILE=$WORK/restoration-state
RUN_ID_FILE=$WORK/run-id
RUN_HARNESS_VERSION_FILE=$WORK/harness-version
EVENTS=$WORK/events.tsv
RAW=$WORK/results
PHASE_REPORT_DIR=$WORK/phase-reports
SETTINGS_FILE=$WORK/settings.env
OWUI_TOKEN=$RUN_DIR/owui-token
COVERAGE_STATE_FILE=$WORK/coverage-state
FAILURE_RC_FILE=$WORK/failure-rc
FAILURE_GUARD=$WORK/failure-handler-active
ERROR_CONTEXT=$WORK/error-context.txt
SERVICE_JOURNAL=$WORK/revalidation-service-journal.txt

PARAM_REGEX='^(amdgpu\.gttsize|ttm\.pages_limit|ttm\.page_pool_size|amdgpu\.ppfeaturemask)='

# Revalidation v4.0 qualifies packaged defaults only. Candidate/tuning A/B work belongs
# under explicit bc250-benchmark commands and is never selected by this worker.

# Immutable package-owned role definitions. Revalidation never accepts model-role
# overrides; candidate selection belongs exclusively to bc250-benchmark.
readonly E2B_MODEL=prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl
readonly E4B_MODEL=prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
readonly LFM_MODEL=prod-lfm25-8b-a1b-liquidai-q6-k
readonly QWEN_MODEL=prod-qwen35-9b-unsloth-q6-k
readonly GPT_OSS_MODEL=prod-gpt-oss20b-ggml-org-mxfp4
readonly EMBED_MODEL=embed-jina-v5-small-retrieval-q4-k-m
readonly TASK_MODEL=task-gemma3-1b-unsloth-ud-q4-k-xl
readonly AGENT_MODEL=agentic-qwen25-coder7b-unsloth-q5-k-m
readonly OWUI_RAG_MODEL=bc250-office-documents
readonly -a PACKAGE_PROD_MODELS=(
  "$E2B_MODEL" "$E4B_MODEL" "$LFM_MODEL" "$QWEN_MODEL" "$GPT_OSS_MODEL"
)

# Gross-regression gates only. These floors are intentionally conservative and
# package-owned; ordinary run-to-run performance variation must not fail qualification.
# Gross-regression qualification policy, not performance targets. Same-board decode
# baselines in MODELS.md map conservatively to these floors: E2B ~112 -> 50,
# E4B ~72 -> 30, LFM ~147 -> 65, Qwen9B ~46 -> 20, GPT-OSS ~80 -> 35 tok/s.
# Residency 0.90 catches major CPU spill; 128 MiB MemAvailable is a deliberately
# unsafe floor rather than desired headroom; 85 C matches the benchmark's highest
# thermal warning/qualification ceiling.
readonly EDGE_MIN_RESIDENCY_RATIO=0.90
readonly EDGE_MIN_MEM_AVAILABLE_MIB=128
readonly EDGE_MAX_TEMP_C=85
readonly EDGE_SEVERE_CONTEXT_TOKENS=4096

usage() {
  cat <<'USAGE'
Usage:
  sudo bc250-revalidate start --owui-token-file FILE [--detach]
  sudo bc250-revalidate start --skip-owui [--detach]
  sudo bc250-revalidate status [--raw]
  sudo bc250-revalidate abort
  sudo bc250-revalidate cleanup

Recommended authenticated start:
  sudo bc250-revalidate start --owui-token-file /root/owui-test.key

`start` launches one systemd-owned qualification worker and follows a compact
six-phase dashboard by default. Ctrl-C detaches from the display; it never kills
the worker. Use --detach for immediate return.

Revalidation answers one question only: does the configuration currently shipped
by this package qualify on this BC-250? It does not choose configuration and does
not run num_batch, embedding-batch, chunk-min, RAG_SYSTEM_CONTEXT, thinking-policy,
kernel/governor, keepalive, or experimental-model A/B sweeps. Run those explicitly
through bc250-benchmark or the appropriate hardware diagnostic workflow.

Full package qualification requires a protected Open WebUI admin API-key file.
Use --skip-owui only for an explicitly incomplete qualification run. The key is
copied only to /run and is never bundled or persisted as package state.
USAGE
}

need_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: run with sudo/root." >&2; exit 1; }
}

now() { date --iso-8601=seconds; }

run_id() { cat "$RUN_ID_FILE" 2>/dev/null || true; }

sanitize_event_field() {
  local value="${1//$'\t'/ }"
  value="${value//$'\n'/ }"
  printf '%s' "$value"
}

record_event() {
  local step="$1" kind="$2" outcome="$3" detail="${4:-}" ts phase
  ts="$(now)"
  phase="$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$ts" "$(sanitize_event_field "$phase")" "$(sanitize_event_field "$step")" \
    "$(sanitize_event_field "$kind")" "$(sanitize_event_field "$outcome")" \
    "$(sanitize_event_field "$detail")" >> "$EVENTS"
  printf '%s\n' "$ts" > "$LAST_EVENT_FILE"
}

set_stage() {
  local msg="$1" ts
  ts="$(now)"
  printf '%s\n' "$msg" > "$STAGE_FILE"
  printf '%s\n' "$ts" > "$STAGE_STARTED_FILE"
  record_event "$msg" progress progress
}

set_phase() {
  printf '%s\n' "$1" > "$PHASE_FILE"
  set_stage "$2"
}

record_progress() { set_stage "$1"; }

abort_requested() {
  [[ -e $WORK/ABORT ]]
}

check_abort() {
  abort_requested || return 0
  record_progress "operator abort requested"
  return 130
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

# Revalidation sanitizes every benchmark invocation so systemd manager/default
# environment cannot replace package-owned fixtures, lane endpoints, models, or
# sampling/tuning policy. Standalone bc250-benchmark intentionally remains flexible.
qualification_benchmark() {
  env \
    -u OLLAMA_URL -u OLLAMA_HOST -u EMBEDDING_OLLAMA_URL \
    -u BC250_BENCH_FIXTURES -u AGENT_TEMPERATURE \
    -u TRANSLATION_MODEL -u TRANSLATION_EXPLICIT_DIRECTION \
    -u RAG_EMBED_MODEL -u RAG_ANSWER_MODEL -u RAG_QUALITY_TOP_K \
    -u RAG_QUALITY_NUM_PREDICT -u EMBED_REPEATS -u EMBED_QUERY_PREFIX \
    -u EMBED_CONTENT_PREFIX -u KEEP_ALIVE -u REQUEST_TIMEOUT \
    -u TELEMETRY_INTERVAL -u BENCH_INCLUDE_EXPERIMENTS -u BOARD_NOTE \
    -u EARLY_EOS_FRACTION -u LATENCY_REPEATS -u NUM_PREDICT_CONTEXT \
    -u NUM_PREDICT_LATENCY -u NUM_PREDICT_LATENCY_THINKING \
    -u NUM_PREDICT_LONG -u NUM_PREDICT_PREFILL -u NUM_PREDICT_SHORT \
    -u NUM_PREDICT_WARM_PREFIX -u PREFILL_SENTENCES -u REPEATS \
    -u RUN_CONTEXT -u RUN_LATENCY -u RUN_THERMAL -u RUN_WARM_PREFIX \
    -u CTX_POINTS -u THROTTLE_WINDOWS -u WARM_PREFIX_SENTENCES \
    "$@"
}

save_settings() {
  printf 'SKIP_OWUI=%q\n' "${SKIP_OWUI:-0}" > "$SETTINGS_FILE"
  chmod 0600 "$SETTINGS_FILE"
}

load_settings() {
  SKIP_OWUI=0
  [[ -f $SETTINGS_FILE ]] && source "$SETTINGS_FILE"
}

validate_protected_token_file() {
  local path="$1" mode
  [[ -f $path && -r $path && -s $path ]] || {
    echo "ERROR: Open WebUI API key file must be a readable, non-empty regular file: $path" >&2
    return 2
  }
  mode="$(stat -c '%a' "$path" 2>/dev/null || true)"
  [[ $mode =~ ^[0-7]{3,4}$ ]] || {
    echo "ERROR: cannot determine permissions for Open WebUI API key file: $path" >&2
    return 2
  }
  if (( (8#$mode) & 077 )); then
    echo "ERROR: Open WebUI API key file must not be group/world accessible: $path (mode $mode)" >&2
    return 2
  fi
}

validate_owui_token_file() {
  local path="$1"
  validate_protected_token_file "$path" || return $?
  python3 - "$path" <<'PYTOKEN'
import pathlib
import sys
import urllib.error
import urllib.request

path = pathlib.Path(sys.argv[1])
token = path.read_text(encoding="utf-8").strip()
if not token:
    print("ERROR: supplied Open WebUI credential is empty.", file=sys.stderr)
    raise SystemExit(2)
req = urllib.request.Request(
    "http://127.0.0.1:3000/ollama/config",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=10) as response:
        response.read(1)
except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
    print(
        "ERROR: supplied Open WebUI credential was rejected or the admin API is unavailable: "
        f"{exc}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PYTOKEN
}

validate_owui_token() {
  [[ -s $OWUI_TOKEN ]] || { echo "ERROR: Open WebUI token copy is missing." >&2; return 1; }
  validate_owui_token_file "$OWUI_TOKEN"
}


api_ready() {
  local port="$1"
  curl -fsS --connect-timeout 2 --max-time 4 "http://127.0.0.1:${port}/api/tags" >/dev/null 2>&1
}

wait_api() {
  local port="$1" attempts="${2:-45}" i
  for ((i=1; i<=attempts; i++)); do
    api_ready "$port" && return 0
    sleep 1
  done
  return 1
}

model_registered() {
  local port="$1" model="$2"
  curl -fsS "http://127.0.0.1:${port}/api/tags" 2>/dev/null | \
    jq -e --arg m "$model" 'any(.models[]?; (.name | sub(":latest$"; "")) == $m)' >/dev/null 2>&1
}


current_relevant_args() {
  sed -E 's/[[:space:]]+/\n/g' /proc/cmdline | grep -E "$PARAM_REGEX" | sort | paste -sd' ' - || true
}

install_unit() {
  cat > "$UNIT_PATH" <<EOFUNIT
[Unit]
Description=BC-250 0.11.0 package qualification v${HARNESS_VERSION}
After=network-online.target cyan-skillfish-governor-smu.service ollama.service open-webui.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash $HARNESS_COPY worker
TimeoutStartSec=infinity
TimeoutStopSec=120
KillMode=mixed

EOFUNIT
  systemctl daemon-reload
}

preflight() {
  local cmd missing=0 pkg
  for cmd in curl jq python3 rpm systemctl journalctl podman sensors vulkaninfo timeout flock tar lspci bc250-status bc250-verify bc250-benchmark bc250-agent-mode bc250-openwebui-setup bc250-cu-status; do
    if ! command_exists "$cmd"; then
      echo "ERROR: missing required command: $cmd" >&2
      missing=1
    fi
  done
  ((missing == 0)) || return 1
  lspci -Dnn 2>/dev/null | grep -iF "[$HARDWARE_PCI_ID]" >/dev/null || {
    echo "ERROR: BC-250 PCI device [$HARDWARE_PCI_ID] was not detected." >&2
    return 1
  }
  pkg="$(rpm -q bc250-llm-server 2>/dev/null || true)"
  [[ $pkg == bc250-llm-server-${TARGET_VERSION}-* ]] || {
    echo "ERROR: expected bc250-llm-server ${TARGET_VERSION}; installed: ${pkg:-not installed}" >&2
    return 1
  }
  if [[ -n $TARGET_RELEASE_PREFIX && $pkg != *"${TARGET_RELEASE_PREFIX}"* ]]; then
    echo "WARN: package release differs from requested ${TARGET_RELEASE_PREFIX}: $pkg" >&2
  fi
  [[ $(systemctl is-active ollama-agent.service 2>/dev/null || true) != active ]] || {
    echo "INFO: agent mode is currently active; start will restore normal mode first."
  }
  local storage_avail
  storage_avail="$(df -h --output=avail /var/lib/bc250-llm-server 2>/dev/null | awk 'NR==2{print $1}' || true)"
  echo "Storage headroom: ${storage_avail:-unknown} available on /var/lib/bc250-llm-server"
}

owui_container_http() {
  local url="$1"
  podman exec open-webui python -c \
    'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=8).read()' \
    "$url" >/dev/null 2>&1
}

application_network_preflight() {
  record_progress "checking Open WebUI private-network connectivity"
  local dir="$RAW/preflight" attempt failed=0 url label
  install -d -m 0700 "$dir"
  : > "$dir/connectivity.txt"

  for unit in tika.service open-webui.service ollama.service ollama-task.service ollama-embedding.service; do
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
      printf 'PASS service %s active\n' "$unit" >> "$dir/connectivity.txt"
    else
      printf 'FAIL service %s inactive\n' "$unit" >> "$dir/connectivity.txt"
      failed=1
    fi
  done

  # Give freshly recreated Quadlets a short readiness window, but do not repair
  # networking here. Revalidation should fail early on stale Podman/netavark state
  # instead of discovering it after the expensive model lanes.
  for attempt in {1..30}; do
    if podman exec open-webui getent hosts tika >/dev/null 2>&1 && \
       podman exec open-webui getent hosts host.containers.internal >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if podman exec open-webui getent hosts tika >/dev/null 2>&1; then
    echo 'PASS dns tika' >> "$dir/connectivity.txt"
  else
    echo 'FAIL dns tika' >> "$dir/connectivity.txt"
    failed=1
  fi
  if podman exec open-webui getent hosts host.containers.internal >/dev/null 2>&1; then
    echo 'PASS dns host.containers.internal' >> "$dir/connectivity.txt"
  else
    echo 'FAIL dns host.containers.internal' >> "$dir/connectivity.txt"
    failed=1
  fi

  while read -r label url; do
    [[ -n "$label" && -n "$url" ]] || continue
    for attempt in {1..30}; do
      owui_container_http "$url" && break
      sleep 1
    done
    if owui_container_http "$url"; then
      printf 'PASS http %s %s\n' "$label" "$url" >> "$dir/connectivity.txt"
    else
      printf 'FAIL http %s %s\n' "$label" "$url" >> "$dir/connectivity.txt"
      failed=1
    fi
  done <<'EOF_PREFLIGHT_URLS'
tika http://tika:9998/version
ollama-main http://host.containers.internal:11434/api/tags
ollama-task http://host.containers.internal:11435/api/tags
ollama-embedding http://host.containers.internal:11437/api/tags
EOF_PREFLIGHT_URLS

  if ((failed)); then
    echo "ERROR: Open WebUI private-network preflight failed:" >&2
    sed 's/^/  /' "$dir/connectivity.txt" >&2
    echo "Repair the application/container network before rerunning; no benchmark lanes were started." >&2
    return 1
  fi
  record_event "private-network" infra pass "Open WebUI private network healthy"
}

phase_label() {
  case "$1" in
    initializing) echo "Initializing" ;;
    preflight) echo "Preflight" ;;
    roles) echo "Production roles" ;;
    edge) echo "Resource edge" ;;
    agent) echo "Agent mode" ;;
    owui) echo "Open WebUI" ;;
    restore) echo "Restore / report" ;;
    done) echo "Complete" ;;
    failed) echo "Failed" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

phase_position() {
  case "$1" in
    preflight) echo "1/6" ;;
    roles) echo "2/6" ;;
    edge) echo "3/6" ;;
    agent) echo "4/6" ;;
    owui) echo "5/6" ;;
    restore|done) echo "6/6" ;;
  esac
}

format_elapsed() {
  local seconds="${1:-0}"
  ((seconds < 0)) && seconds=0
  printf '%02d:%02d:%02d' $((seconds/3600)) $(((seconds%3600)/60)) $((seconds%60))
}

event_age() {
  local value="$1" now_s value_s age
  [[ -n "$value" && "$value" != none ]] || { echo "unknown"; return 0; }
  value_s="$(date -d "$value" +%s 2>/dev/null || true)"
  [[ "$value_s" =~ ^[0-9]+$ ]] || { echo "unknown"; return 0; }
  now_s="$(date +%s)"
  age=$((now_s - value_s)); ((age < 0)) && age=0
  if ((age < 60)); then echo "${age}s ago"
  elif ((age < 3600)); then echo "$((age/60))m $((age%60))s ago"
  else echo "$((age/3600))h $(((age%3600)/60))m ago"
  fi
}

quality_counts() {
  [[ -r "$EVENTS" ]] || { echo "0 0 0"; return; }
  awk -F '\t' '$4=="quality" {if($5=="pass")p++; else if($5=="quality-fail")q++; else if($5=="skipped")s++} END{print p+0,q+0,s+0}' "$EVENTS"
}

quality_state() {
  local p q skipped
  read -r p q skipped <<<"$(quality_counts)"
  if ((p == 0 && q == 0)); then echo "not-run"
  elif ((q > 0 && p == 0)); then echo "fail"
  elif ((q > 0)); then echo "mixed"
  else echo "pass"
  fi
}

recent_step_results() {
  local count=0 step outcome symbol
  [[ -r "$EVENTS" ]] || { echo "  (none yet)"; return; }
  while IFS=$'\t' read -r step outcome; do
    case "$outcome" in
      pass) symbol='✓' ;;
      quality-fail) symbol='!' ;;
      infra-fail) symbol='×' ;;
      skipped) symbol='·' ;;
      *) symbol='·' ;;
    esac
    printf '  %-2s %-34s %s\n' "$symbol" "$step" "$outcome"
    count=$((count + 1))
  done < <(awk -F '\t' '$4=="quality" || $4=="infra" {rows[++n]=$3 "\t" $5} END {start=n-5; if(start<1)start=1; for(i=start;i<=n;i++) print rows[i]}' "$EVENTS")
  ((count > 0)) || echo "  (none yet)"
}

dashboard_text() {
  local phase stage last_event stage_started started now_s elapsed stage_elapsed position label service p q skipped
  phase="$(cat "$PHASE_FILE" 2>/dev/null || echo initializing)"
  stage="$(cat "$STAGE_FILE" 2>/dev/null || echo starting)"
  last_event="$(cat "$LAST_EVENT_FILE" 2>/dev/null || echo none)"
  stage_started="$(cat "$STAGE_STARTED_FILE" 2>/dev/null || echo none)"
  stage="${stage//$'\n'/ }"; ((${#stage} <= 96)) || stage="${stage:0:93}..."
  started="$(stat -c %Y "$RUN_ID_FILE" 2>/dev/null || date +%s)"; now_s="$(date +%s)"
  elapsed="$(format_elapsed $((now_s - started)))"
  if [[ "$stage_started" != none ]]; then
    local stage_s; stage_s="$(date -d "$stage_started" +%s 2>/dev/null || echo "$now_s")"
    stage_elapsed="$(format_elapsed $((now_s - stage_s)))"
  else stage_elapsed=unknown; fi
  position="$(phase_position "$phase")"; label="$(phase_label "$phase")"
  service="$(systemctl is-active "$UNIT" 2>/dev/null || true)"
  read -r p q skipped <<<"$(quality_counts)"

  printf 'BC-250 revalidation  [RUNNING %s]\n\n' "$elapsed"
  printf 'Phase         %-4s  %s\n' "${position:-?}" "$label"
  printf 'Stage         %s\n' "$stage"
  printf 'Stage time    %s\n' "$stage_elapsed"
  printf 'Worker        %s\n' "${service:-unknown}"
  printf 'Last event    %s\n' "$(event_age "$last_event")"
  local infra_state
  infra_state="$(cat "$INFRA_STATE_FILE" 2>/dev/null || echo pass)"
  printf '\nInfrastructure  %s so far\n' "${infra_state^^}"
  printf 'Quality         %s pass / %s quality-fail / %s skipped\n' "$p" "$q" "$skipped"
  printf '\nRecent results\n'
  recent_step_results
  printf '\nCtrl-C detaches; the worker continues under systemd.\n'
}

follow_run() {
  local interrupted=0 phase stage last="" rc=1 dashboard="" drawn_lines=0 new_lines=0
  trap 'interrupted=1' INT
  echo
  while ((interrupted == 0)); do
    phase="$(cat "$PHASE_FILE" 2>/dev/null || echo initializing)"
    stage="$(cat "$STAGE_FILE" 2>/dev/null || echo starting)"
    if [[ -t 1 ]]; then
      dashboard="$(dashboard_text)"; new_lines="$(printf '%s\n' "$dashboard" | awk 'END{print NR}')"
      ((drawn_lines == 0)) || printf '\033[%dA' "$drawn_lines"
      while IFS= read -r line; do printf '\033[2K\r%s\n' "$line"; done <<< "$dashboard"
      drawn_lines="$new_lines"
    elif [[ "$phase|$stage" != "$last" ]]; then
      printf '[%s] phase=%s  %s\n' "$(format_elapsed $(( $(date +%s) - $(stat -c %Y "$RUN_ID_FILE" 2>/dev/null || date +%s) )))" "$phase" "$stage"
      last="$phase|$stage"
    fi
    case "$phase" in
      done) [[ -n $(latest_bundle_path) ]] && break ;;
      failed) break ;;
    esac
    sleep 2 || true
  done
  trap - INT
  if ((interrupted)); then
    echo "Detached. Worker continues in the background."
    echo "Status: sudo bc250-revalidate status"
    return 0
  fi
  phase="$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)"
  if [[ "$phase" == done ]]; then
    echo "Revalidation run completed."
    printf 'Run state:      %s\n' "$(effective_run_state)"
    printf 'Infrastructure: %s\n' "$(cat "$INFRA_STATE_FILE" 2>/dev/null || echo unknown)"
    printf 'Quality:        %s\n' "$(cat "$QUALITY_STATE_FILE" 2>/dev/null || quality_state)"
    printf 'Restoration:    %s\n' "$(cat "$RESTORATION_STATE_FILE" 2>/dev/null || echo unknown)"
    printf 'Coverage:       %s\n' "$(cat "$COVERAGE_STATE_FILE" 2>/dev/null || echo unknown)"
    echo "Final bundle: $(find "$REPORT_DIR" -maxdepth 1 -type f -name "$(run_id)-bc250-revalidation-results.tar.gz" -print -quit 2>/dev/null)"
    return 0
  fi
  [[ -r "$FAILURE_RC_FILE" ]] && rc="$(cat "$FAILURE_RC_FILE")"; [[ "$rc" =~ ^[0-9]+$ ]] || rc=1
  echo "Revalidation failed at phase=$phase (rc=$rc)." >&2
  [[ ! -e $ERROR_CONTEXT ]] || echo "Error context: $ERROR_CONTEXT" >&2
  return "$rc"
}

cleanup_transient_token() {
  rm -f "$OWUI_TOKEN"
}

cleanup_failed_launch() {
  cleanup_transient_token
  rm -f "$UNIT_PATH"
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RUN_DIR"
}

launch_worker() {
  if ! install_unit; then
    cleanup_failed_launch
    return 1
  fi
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
  if ! systemctl start --no-block "$UNIT"; then
    cleanup_failed_launch
    return 1
  fi
}

start_run() {
  need_root
  local token_file="" detach=0 skip_owui=0
  shift || true
  while (($#)); do
    case "$1" in
      --owui-token-file)
        [[ $# -ge 2 ]] || { echo "ERROR: --owui-token-file requires a path" >&2; exit 2; }
        token_file="$2"; shift 2 ;;
      --skip-owui) skip_owui=1; shift ;;
      --detach) detach=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) echo "ERROR: unknown start option: $1" >&2; usage >&2; exit 2 ;;
    esac
  done
  ((skip_owui == 0 || ${#token_file} == 0)) || {
    echo "ERROR: --skip-owui and --owui-token-file are mutually exclusive." >&2
    exit 2
  }
  if ((skip_owui == 0)) && [[ -z $token_file ]]; then
    echo "ERROR: full package qualification requires --owui-token-file FILE." >&2
    echo "       Use --skip-owui only for an explicitly incomplete run." >&2
    exit 2
  fi

  preflight
  if [[ -n $token_file ]]; then
    # Validate protection before any run state exists. Authentication is also
    # validated before state creation, after normal topology is available.
    validate_protected_token_file "$token_file" || exit $?
  fi
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    echo "ERROR: $UNIT is already running." >&2
    exit 1
  fi
  if [[ -d $WORK && -f $PHASE_FILE ]]; then
    case "$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)" in
      done|failed) ;;
      *) echo "ERROR: unfinished session under $WORK; use status/abort/cleanup first." >&2; exit 1 ;;
    esac
  fi
  ensure_normal_mode
  [[ -z $token_file ]] || validate_owui_token_file "$token_file" || exit $?

  rm -rf "$WORK" "$RUN_DIR"
  install -d -m 0700 "$WORK" "$RAW" "$PHASE_REPORT_DIR" "$RUN_DIR" "$STATE_ROOT" "$REPORT_DIR"
  install -m 0700 "$0" "$HARNESS_COPY"
  SKIP_OWUI="$skip_owui"
  save_settings
  : > "$EVENTS"
  printf 'initializing\n' > "$PHASE_FILE"; printf 'start requested\n' > "$STAGE_FILE"
  printf '%s\n' "$(now)" > "$STAGE_STARTED_FILE"; cp "$STAGE_STARTED_FILE" "$LAST_EVENT_FILE"
  printf '%s-%s\n' "$(date +%Y%m%dT%H%M%S%z)" "$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')" > "$RUN_ID_FILE"
  printf '%s\n' "$HARNESS_VERSION" > "$RUN_HARNESS_VERSION_FILE"
  printf 'running\n' > "$RUN_STATE_FILE"; printf 'pass\n' > "$INFRA_STATE_FILE"; printf 'not-run\n' > "$QUALITY_STATE_FILE"; printf 'not-needed\n' > "$RESTORATION_STATE_FILE"
  if ((skip_owui)); then
    printf 'partial\n' > "$COVERAGE_STATE_FILE"
  else
    printf 'full\n' > "$COVERAGE_STATE_FILE"
    install -m 0600 "$token_file" "$OWUI_TOKEN"
  fi
  printf 'preflight\n' > "$PHASE_FILE"
  record_event start infra pass "qualification worker requested"

  launch_worker
  echo
  echo "Started BC-250 revalidation run $(run_id) with harness v$HARNESS_VERSION."
  if ((skip_owui)); then
    echo "Coverage is partial: authenticated Open WebUI qualification was explicitly skipped."
  fi
  echo "The systemd worker qualifies packaged defaults only; this terminal only follows progress."
  echo "Status: sudo bc250-revalidate status"
  echo "Final bundles: $REPORT_DIR"
  ((detach)) || follow_run
}

capture_cmd() {
  local file="$1"; shift
  { echo '$' "$@"; "$@"; } > "$file" 2>&1 || echo "command_rc=$?" >> "$file"
}

snapshot() {
  local label="$1" dir="$RAW/$1"
  record_progress "capturing snapshot: $label"
  install -d -m 0700 "$dir"
  {
    echo "timestamp=$(now)"
    echo "kernel=$(uname -r)"
    echo "package=$(rpm -q bc250-llm-server 2>/dev/null || true)"
    echo "cmdline=$(cat /proc/cmdline)"
    echo "current_relevant_args=$(current_relevant_args | paste -sd' ' -)"
    for f in \
      /sys/module/amdgpu/parameters/gttsize \
      /sys/module/amdgpu/parameters/ppfeaturemask \
      /sys/module/ttm/parameters/pages_limit \
      /sys/module/ttm/parameters/page_pool_size; do
      [[ -r $f ]] && echo "$f=$(cat "$f")" || true
    done
    for d in /sys/class/drm/card*/device; do
      [[ -r $d/vendor && $(cat "$d/vendor" 2>/dev/null) == 0x1002 ]] || continue
      for f in mem_info_vram_total mem_info_vram_used mem_info_gtt_total mem_info_gtt_used; do
        [[ -r $d/$f ]] && echo "$f=$(cat "$d/$f")"
      done
      break
    done
  } > "$dir/kernel-profile.txt" 2>&1
  capture_cmd "$dir/kernel-rpms.txt" rpm -q kernel-core mesa-vulkan-drivers vulkan-loader vulkan-tools
  command_exists grubby && capture_cmd "$dir/grubby-all.txt" grubby --info=ALL || true
  command_exists bc250-memory-profile && capture_cmd "$dir/memory-profile.txt" bc250-memory-profile status || true
  command_exists bc250-cu-status && capture_cmd "$dir/cu-status.txt" bc250-cu-status || true
  if [[ -r /etc/cyan-skillfish-governor-smu/config.toml ]]; then
    cp -a /etc/cyan-skillfish-governor-smu/config.toml "$dir/governor-config.toml"
  fi
  command_exists cyan-skillfish-performance-mode && capture_cmd "$dir/performance-mode.txt" cyan-skillfish-performance-mode --status || true
  capture_cmd "$dir/bc250-status.txt" bc250-status
  if [[ -s $OWUI_TOKEN ]]; then
    bc250-verify --owui-token-file "$OWUI_TOKEN" > "$dir/bc250-verify.txt" 2>&1 || echo "command_rc=$?" >> "$dir/bc250-verify.txt"
    bc250-openwebui-setup status --owui-token-file "$OWUI_TOKEN" > "$dir/openwebui-status-auth.txt" 2>&1 || echo "command_rc=$?" >> "$dir/openwebui-status-auth.txt"
  else
    capture_cmd "$dir/bc250-verify.txt" bc250-verify
    capture_cmd "$dir/openwebui-status.txt" bc250-openwebui-setup status
  fi
  capture_cmd "$dir/agent-mode.txt" bc250-agent-mode status
  capture_cmd "$dir/systemctl.txt" systemctl --no-pager --full status ollama.service ollama-task.service ollama-embedding.service ollama-agent.service open-webui.service tika.service nginx.service
  for port in 11434 11435 11436 11437; do
    curl -fsS "http://127.0.0.1:$port/api/version" > "$dir/ollama-$port-version.json" 2>&1 || true
    curl -fsS "http://127.0.0.1:$port/api/tags" > "$dir/ollama-$port-tags.json" 2>&1 || true
    curl -fsS "http://127.0.0.1:$port/api/ps" > "$dir/ollama-$port-ps.json" 2>&1 || true
  done
  podman inspect open-webui --format '{{json .State}}' > "$dir/openwebui-container-state.json" 2>&1 || true
  podman inspect open-webui --format '{{.ImageName}}' > "$dir/openwebui-container-image.txt" 2>&1 || true
  capture_cmd "$dir/free.txt" free -h
  capture_cmd "$dir/swapon.txt" swapon --show
  capture_cmd "$dir/sensors.txt" sensors
  capture_cmd "$dir/vulkan.txt" vulkaninfo --summary
  journalctl -b --no-pager -n 1200 -u ollama.service -u ollama-task.service -u ollama-embedding.service -u ollama-agent.service -u open-webui.service > "$dir/services-journal.txt" 2>&1 || true
  journalctl -k -b --no-pager -n 1200 > "$dir/kernel-journal.txt" 2>&1 || true
}

write_phase_report() {
  local label="$1" scope="$2" stamp file
  stamp="$(date +%Y%m%dT%H%M%S)"
  file="$PHASE_REPORT_DIR/$(run_id)-${label}-${stamp}.txt"
  {
    echo "# BC-250 0.11.0 revalidation v${HARNESS_VERSION} phase report"
    echo "generated=$(now)"
    echo "run_id=$(run_id)"
    echo "phase=$(cat "$PHASE_FILE")"
    echo "stage=$(cat "$STAGE_FILE")"
    echo "kernel=$(uname -r)"
    echo "package=$(rpm -q bc250-llm-server 2>/dev/null || true)"
    echo "current_relevant_args=$(current_relevant_args | paste -sd' ' -)"
    echo
    echo "## Events"
    cat "$EVENTS"
    echo
    echo "## Phase files: $scope"
    if [[ -d $RAW/$scope ]]; then
      while IFS= read -r f; do
        echo
        echo "===== BEGIN FILE: ${f#"$WORK"/} ====="
        case "$f" in
          *.png|*.jpg|*.jpeg|*.tar|*.gz) echo "[binary omitted from text report]" ;;
          *) cat "$f" 2>/dev/null || true ;;
        esac
        echo "===== END FILE: ${f#"$WORK"/} ====="
      done < <(find "$RAW/$scope" -type f -print | sort)
    fi
  } > "$file"
  chmod 0644 "$file"
  record_progress "immutable phase report written: $file"
}

sample_loop() {
  local out="$1" dev="" hw="" temp="" power="" clock="" gtt="" mem="" swap=""
  local d h label f
  for d in /sys/class/drm/card*/device; do
    [[ -r $d/vendor && $(cat "$d/vendor" 2>/dev/null) == 0x1002 ]] || continue
    dev="$d"
    break
  done
  if [[ -n $dev ]]; then
    for h in "$dev"/hwmon/hwmon*; do
      [[ -d $h ]] || continue
      hw="$h"
      break
    done
  fi
  printf 'timestamp\tclock_mhz\ttemp_c\tsmu_power_w\tgtt_used_mib\tmemavailable_mib\tswap_used_mib\n' > "$out"
  while :; do
    clock=""; temp=""; power=""; gtt=""; mem=""; swap=""
    if [[ -n $dev && -r $dev/pp_dpm_sclk ]]; then
      clock="$(awk '/\*/{gsub("Mhz", "", $2); print $2; exit}' "$dev/pp_dpm_sclk" 2>/dev/null || true)"
    fi
    if [[ -n $hw ]]; then
      # Prefer edge, then junction, then temp1.
      for label in edge junction; do
        for f in "$hw"/temp*_label; do
          [[ -r $f ]] || continue
          if [[ $(cat "$f" 2>/dev/null) == "$label" ]]; then
            f="${f%_label}_input"
            [[ -r $f ]] && temp="$(awk '{printf "%.1f", $1/1000}' "$f" 2>/dev/null || true)"
            break 2
          fi
        done
      done
      [[ -n $temp || ! -r $hw/temp1_input ]] || temp="$(awk '{printf "%.1f", $1/1000}' "$hw/temp1_input" 2>/dev/null || true)"
      [[ ! -r $hw/power1_average ]] || power="$(awk '{printf "%.2f", $1/1000000}' "$hw/power1_average" 2>/dev/null || true)"
    fi
    if [[ -n $dev && -r $dev/mem_info_gtt_used ]]; then
      gtt="$(awk '{printf "%.1f", $1/1048576}' "$dev/mem_info_gtt_used" 2>/dev/null || true)"
    fi
    mem="$(awk '/^MemAvailable:/{printf "%.1f", $2/1024}' /proc/meminfo 2>/dev/null || true)"
    swap="$(awk '/^SwapTotal:/{t=$2}/^SwapFree:/{f=$2}END{printf "%.1f", (t-f)/1024}' /proc/meminfo 2>/dev/null || true)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%s.%N)" "$clock" "$temp" "$power" "$gtt" "$mem" "$swap" >> "$out"
    sleep 0.5
  done
}

SAMPLER_PID=""
WORKER_BASHPID=""

write_rc_outcome() {
  local rc="$1" out="$2"
  case "$rc" in
    0) printf 'pass\n' > "$out" ;;
    3) printf 'quality-fail\n' > "$out" ;;
    *) printf 'infra-fail\n' > "$out" ;;
  esac
}

start_sampler() {
  local out="$1"
  stop_sampler "${SAMPLER_PID:-}"
  ( trap - ERR TERM INT; set +eE; sample_loop "$out" ) >/dev/null 2>&1 &
  SAMPLER_PID=$!
}

stop_sampler() {
  local pid="${1:-${SAMPLER_PID:-}}"
  [[ -n $pid ]] || return 0
  kill "$pid" >/dev/null 2>&1 || true; wait "$pid" 2>/dev/null || true
  [[ ${SAMPLER_PID:-} != "$pid" ]] || SAMPLER_PID=""
}

worker_exit_cleanup() { stop_sampler "${SAMPLER_PID:-}"; }

run_step() {
  local scope="$1" label="$2" kind="$3"; shift 3
  local dir="$RAW/$scope/$label" rc sampler_pid outcome
  [[ "$kind" == quality || "$kind" == infra ]] || { echo "ERROR: invalid step kind: $kind" >&2; return 2; }
  install -d -m 0700 "$dir"
  set_stage "$label"
  start_sampler "$dir/sampler.tsv"; sampler_pid="$SAMPLER_PID"
  if ( trap - ERR TERM INT; set +eE; cd "$dir" || exit $?; exec timeout --signal=INT --kill-after=30s 45m "$@" ) > "$dir/console.txt" 2>&1; then rc=0; else rc=$?; fi
  stop_sampler "$sampler_pid"
  printf '%s\n' "$rc" > "$dir/exit-status.txt"; write_rc_outcome "$rc" "$dir/outcome.txt"; outcome="$(cat "$dir/outcome.txt")"
  if [[ "$kind" == quality && $rc -eq 3 ]]; then
    record_event "$label" quality quality-fail "scope=$scope rc=3"
    return 0
  fi
  if ((rc == 0)); then
    record_event "$label" "$kind" pass "scope=$scope rc=0"
    return 0
  fi
  record_event "$label" infra infra-fail "scope=$scope rc=$rc kind=$kind"
  return "$rc"
}



warm_embedding() {
  local payload
  model_registered 11437 "$EMBED_MODEL" || return 1
  payload="$(jq -nc --arg model "$EMBED_MODEL" '{model:$model,input:["Query: BC-250 embedding residency check"],keep_alive:"10m"}')"
  curl -fsS --connect-timeout 2 --max-time 90 \
    -H 'Content-Type: application/json' -d "$payload" \
    http://127.0.0.1:11437/api/embed | jq -e '.embeddings | length > 0' >/dev/null
}

ensure_normal_mode() {
  for unit in ollama-task.service ollama-embedding.service ollama-agent.service; do
    systemctl cat "$unit" >/dev/null 2>&1 || {
      echo "ERROR: required package unit is missing: $unit" >&2
      return 1
    }
  done
  bc250-agent-mode leave >/dev/null
  systemctl start tika.service open-webui.service nginx.service >/dev/null
  wait_api 11434 45 || return 1
  wait_api 11435 45 || return 1
  wait_api 11437 45 || return 1
  local i
  for i in {1..60}; do
    curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:3000/ >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:3000/ >/dev/null 2>&1 || return 1
  curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1/ >/dev/null 2>&1 || return 1
}

container_env_value() {
  local key="$1"
  podman inspect open-webui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | \
    awk -F= -v k="$key" '$1==k{v=$2} END{print v}'
}

check_openwebui_bootstrap_env() {
  local out="$RAW/preflight/openwebui-bootstrap-contract.txt" key expected actual failures=0
  : > "$out"
  while IFS='|' read -r key expected; do
    actual="$(container_env_value "$key")"
    printf '%s expected=%s actual=%s\n' "$key" "$expected" "${actual:-missing}" >> "$out"
    if [[ ${actual,,} != "${expected,,}" ]]; then
      failures=$((failures + 1))
    fi
  done <<'EOFENV'
OFFLINE_MODE|true
HF_HUB_OFFLINE|1
ENABLE_OPENAI_API|false
ENABLE_DIRECT_CONNECTIONS|false
ENABLE_CODE_EXECUTION|false
ENABLE_CODE_INTERPRETER|false
RAG_SYSTEM_CONTEXT|false
EOFENV
  printf 'failures=%d\n' "$failures" >> "$out"
  ((failures == 0))
}

required_role_models() {
  printf '%s\n' "${PACKAGE_PROD_MODELS[@]}"
}

check_required_models() {
  local model failed=0 out="$RAW/preflight/required-models.txt"
  : > "$out"
  while IFS= read -r model; do
    if model_registered 11434 "$model"; then echo "PASS main $model" >> "$out"; else echo "FAIL main $model" >> "$out"; failed=1; fi
  done < <(required_role_models)
  if model_registered 11435 "$TASK_MODEL"; then echo "PASS task $TASK_MODEL" >> "$out"; else echo "FAIL task $TASK_MODEL" >> "$out"; failed=1; fi
  if model_registered 11437 "$EMBED_MODEL"; then echo "PASS embedding $EMBED_MODEL" >> "$out"; else echo "FAIL embedding $EMBED_MODEL" >> "$out"; failed=1; fi
  ((failed == 0))
}

health_gate() {
  local label="$1" out="$2" rc
  install -d -m 0700 "$(dirname "$out")"
  if [[ ${SKIP_OWUI:-0} -eq 1 ]]; then
    if bc250-verify > "$out" 2>&1; then rc=0; else rc=$?; fi
  else
    if bc250-verify --owui-token-file "$OWUI_TOKEN" > "$out" 2>&1; then rc=0; else rc=$?; fi
  fi
  if ((rc == 0)); then
    record_event "$label" infra pass "bc250-verify health gate passed"
    return 0
  fi
  record_event "$label" infra infra-fail "bc250-verify health gate rc=$rc"
  echo "ERROR: appliance health gate failed ($label, rc=$rc); inspect $out" >&2
  return "$rc"
}

model_loaded() {
  local port="$1" model="$2"
  curl -fsS "http://127.0.0.1:${port}/api/ps" 2>/dev/null | \
    jq -e --arg m "$model" 'any(.models[]?; (.name | sub(":latest$"; "")) == $m)' >/dev/null 2>&1
}

write_edge_policy() {
  local out="$1"
  cat > "$out" <<EOF_POLICY
{
  "min_residency_ratio": $EDGE_MIN_RESIDENCY_RATIO,
  "min_mem_available_mib": $EDGE_MIN_MEM_AVAILABLE_MIB,
  "max_temp_c": $EDGE_MAX_TEMP_C,
  "severe_context_tokens": $EDGE_SEVERE_CONTEXT_TOKENS,
  "models": {
    "$E2B_MODEL": {"min_decode_tps": 50.0, "min_context": 32768},
    "$E4B_MODEL": {"min_decode_tps": 30.0, "min_context": 32768},
    "$LFM_MODEL": {"min_decode_tps": 65.0, "min_context": 32768},
    "$QWEN_MODEL": {"min_decode_tps": 20.0, "min_context": 32768},
    "$GPT_OSS_MODEL": {"min_decode_tps": 35.0, "min_context": 16384}
  }
}
EOF_POLICY
}

check_edge_generation_sanity() {
  local jsonl="$1" policy="$2" out="$3"
  python3 - "$jsonl" "$policy" "$out" <<'PY_EDGE'
import json
import statistics
import sys
from pathlib import Path

jsonl, policy_path, output = map(Path, sys.argv[1:4])
policy = json.loads(policy_path.read_text(encoding="utf-8"))
records = []
for line_no, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        continue
    row = json.loads(line)
    if row.get("category") == "generation":
        records.append(row)

failures = []
checks = {}
for model, limits in policy["models"].items():
    rows = [r for r in records if str(r.get("model", "")).removesuffix(":latest") == model]
    passed = [r for r in rows if r.get("outcome") == "pass"]
    model_checks = {}
    if not passed:
        failures.append(f"{model}: no successful generation measurements")
        checks[model] = {"measurements_present": False}
        continue

    missing_evidence = []
    for r in passed:
        case_id = str(r.get("case_id", "unknown"))
        metrics = r.get("metrics", {})
        required = (
            "allocated_context",
            "resident_size_bytes",
            "resident_vram_bytes",
            "mem_available_min_mib",
            "temp_max_c",
        )
        for field in required:
            value = metrics.get(field)
            invalid = value is None
            if field in {"allocated_context", "resident_size_bytes"} and value is not None:
                try:
                    invalid = float(value) <= 0
                except (TypeError, ValueError):
                    invalid = True
            if invalid:
                missing_evidence.append(f"{case_id}:{field}")
        if case_id.startswith("short-") and metrics.get("tokens_per_second") is None:
            missing_evidence.append(f"{case_id}:tokens_per_second")

    model_checks["resource_evidence_complete"] = not missing_evidence
    model_checks["missing_required_evidence"] = missing_evidence
    if missing_evidence:
        failures.append(
            f"{model}: required Phase-3 evidence unavailable for "
            + ", ".join(missing_evidence)
        )

    short = [
        float(r.get("metrics", {}).get("tokens_per_second"))
        for r in passed
        if str(r.get("case_id", "")).startswith("short-")
        and r.get("metrics", {}).get("tokens_per_second") is not None
    ]
    decode = statistics.fmean(short) if short else 0.0
    model_checks["decode_tps"] = decode
    model_checks["decode_floor"] = float(limits["min_decode_tps"])
    if decode < float(limits["min_decode_tps"]):
        failures.append(f"{model}: gross decode regression {decode:.2f} < {limits['min_decode_tps']} tok/s")

    contexts = [
        int(r.get("metrics", {}).get("allocated_context"))
        for r in passed
        if r.get("metrics", {}).get("allocated_context") is not None
    ]
    allocated = min(contexts, default=0)
    model_checks["min_allocated_context"] = allocated
    model_checks["required_context"] = int(limits["min_context"])
    if allocated < int(limits["min_context"]):
        failures.append(f"{model}: minimum allocated context {allocated} < package requirement {limits['min_context']}")

    ratios = []
    for r in passed:
        m = r.get("metrics", {})
        size_raw = m.get("resident_size_bytes")
        vram_raw = m.get("resident_vram_bytes")
        if size_raw is None or vram_raw is None:
            continue
        size = float(size_raw)
        if size > 0:
            ratios.append(float(vram_raw) / size)
    residency = min(ratios, default=0.0)
    model_checks["min_residency_ratio"] = residency
    if residency < float(policy["min_residency_ratio"]):
        failures.append(f"{model}: GPU residency ratio {residency:.3f} < {policy['min_residency_ratio']}")

    mem_values = [
        float(r.get("metrics", {}).get("mem_available_min_mib"))
        for r in passed
        if r.get("metrics", {}).get("mem_available_min_mib") is not None
    ]
    mem_min = min(mem_values) if mem_values else 0.0
    model_checks["mem_available_min_mib"] = mem_min
    if mem_min < float(policy["min_mem_available_mib"]):
        failures.append(f"{model}: MemAvailable floor {mem_min:.0f} MiB < {policy['min_mem_available_mib']} MiB")

    temps = [
        float(r.get("metrics", {}).get("temp_max_c"))
        for r in passed
        if r.get("metrics", {}).get("temp_max_c") is not None
    ]
    model_checks["temperature_telemetry_present"] = bool(temps)
    model_checks["temperature_telemetry_complete"] = len(temps) == len(passed)
    if temps:
        temp_max = max(temps)
        model_checks["temp_max_c"] = temp_max
        if temp_max >= float(policy["max_temp_c"]):
            failures.append(f"{model}: temperature {temp_max:.1f} C reached gross qualification ceiling {policy['max_temp_c']} C")
    else:
        model_checks["temp_max_c"] = None

    severe = [
        r for r in passed
        if "context-truncation" in r.get("diagnostics", [])
        and int(r.get("metrics", {}).get("prompt_eval_count") or 0) < int(policy["severe_context_tokens"])
    ]
    model_checks["severe_early_context_truncation"] = bool(severe)
    if severe:
        failures.append(f"{model}: severe early context truncation below {policy['severe_context_tokens']} evaluated tokens")
    checks[model] = model_checks

result = {"passed": not failures, "policy": policy, "checks": checks, "failures": failures}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if failures:
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    raise SystemExit(1)
PY_EDGE
}

check_recent_device_errors() {
  local out="$1" since
  since="$(awk 'NR==1{print $1; exit}' "$EVENTS" 2>/dev/null || true)"
  [[ -n $since ]] || since="$(now)"
  journalctl -k -b --since "$since" --no-pager > "$out" 2>&1 || return 1
  if grep -Eiq 'amdgpu.*(ring[^[:space:]]*.*timeout|gpu reset|device lost|vm fault|page fault)' "$out"; then
    echo "ERROR: AMDGPU/device fault detected during qualification; inspect $out" >&2
    return 1
  fi
}

check_live_cu_routing() {
  local out="$RAW/preflight/cu-routing.txt"
  bc250-cu-status --summary > "$out" 2>&1 || true
  if grep -Fq 'Live routing status     : routed entries present; no off/problem cells' "$out"; then
    record_event "live-cu-routing" infra pass "complete live routing table healthy"
    return 0
  fi
  echo "ERROR: complete live SPI/WGP routing table is not healthy; inspect $out" >&2
  return 1
}

phase_preflight() {
  set_phase preflight "restoring normal topology and checking packaged prerequisites"
  install -d -m 0700 "$RAW/preflight"
  ensure_normal_mode
  [[ $(systemctl is-active ollama-agent.service 2>/dev/null || true) != active ]]
  check_openwebui_bootstrap_env
  check_live_cu_routing
  application_network_preflight
  check_required_models
  if [[ ${SKIP_OWUI:-0} -eq 0 ]]; then
    local rc
    validate_owui_token > "$RAW/preflight/token-validation.txt" 2>&1
    if bc250-openwebui-setup status --owui-token-file "$OWUI_TOKEN" > "$RAW/preflight/package-drift.txt" 2>&1; then rc=0; else rc=$?; fi
    ((rc == 0)) || { echo "ERROR: packaged Open WebUI state cannot be qualified without first resolving drift/API error (rc=$rc)." >&2; return "$rc"; }
    record_event "openwebui-drift" infra pass "package-owned settings current"
  else
    echo "SKIP: authenticated Open WebUI checks explicitly disabled by --skip-owui" > "$RAW/preflight/openwebui-skipped.txt"
    record_event "openwebui-drift" coverage skipped "explicit --skip-owui"
  fi
  health_gate "preflight-health" "$RAW/preflight/bc250-verify-gate.txt"
  snapshot preflight/final
  write_phase_report preflight-results preflight
}

phase_roles() {
  set_phase roles "qualifying promoted production roles"
  install -d -m 0700 "$RAW/roles"
  warm_embedding > "$RAW/roles/embed-warm.txt" 2>&1
  run_step roles embeddings quality qualification_benchmark bc250-benchmark embeddings "$EMBED_MODEL" --ollama-url http://127.0.0.1:11437 --output-dir "$RAW/roles/embeddings/results"
  run_step roles task quality qualification_benchmark bc250-benchmark task "$TASK_MODEL" --ollama-url http://127.0.0.1:11435 --output-dir "$RAW/roles/task/results"
  # Qualify the package's shipped translation behavior only. Direction A/B remains
  # an explicit standalone benchmark and cannot leak in through manager environment.
  run_step roles translation quality qualification_benchmark bc250-benchmark translation "$LFM_MODEL" --ollama-url http://127.0.0.1:11434 --output-dir "$RAW/roles/translation/results"
  warm_embedding >/dev/null 2>&1 || true
  run_step roles rag-quality quality qualification_benchmark bc250-benchmark rag-quality "$EMBED_MODEL" "$E4B_MODEL" --ollama-url http://127.0.0.1:11434 --embedding-ollama-url http://127.0.0.1:11437 --think auto --output-dir "$RAW/roles/rag-quality/results"
  run_step roles usecase quality qualification_benchmark bc250-benchmark usecase --ollama-url http://127.0.0.1:11434 --output-dir "$RAW/roles/production-usecase/results" "${PACKAGE_PROD_MODELS[@]}"
  snapshot roles/final
  write_phase_report production-role-results roles
}

phase_edge() {
  set_phase edge "checking bounded production performance and coexistence"
  local policy="$RAW/edge/edge-policy.json" gpt_policy="$RAW/edge/gpt-oss-policy.json"
  install -d -m 0700 "$RAW/edge"
  write_edge_policy "$policy"

  warm_embedding >/dev/null 2>&1
  run_step edge production-generation infra qualification_benchmark env RUN_LATENCY=0 RUN_CONTEXT=1 RUN_THERMAL=0 CTX_POINTS="88 220" NUM_PREDICT_CONTEXT=16 bc250-benchmark generation --ollama-url http://127.0.0.1:11434 --mode production --profile edge --output-dir "$RAW/edge/production-generation/results" "${PACKAGE_PROD_MODELS[@]}"
  run_step edge production-sanity infra check_edge_generation_sanity     "$RAW/edge/production-generation/results/results.jsonl" "$policy" "$RAW/edge/production-generation/sanity.json"

  api_ready 11434 || ensure_normal_mode
  warm_embedding >/dev/null 2>&1
  jq --arg m "$GPT_OSS_MODEL" '.models |= with_entries(select(.key == $m))' "$policy" > "$gpt_policy"
  run_step edge gpt-oss-jina infra qualification_benchmark env RUN_LATENCY=0 RUN_CONTEXT=1 RUN_THERMAL=0 PREFILL_SENTENCES=352 CTX_POINTS="352 704" NUM_PREDICT_PREFILL=16 NUM_PREDICT_CONTEXT=32 bc250-benchmark generation --ollama-url http://127.0.0.1:11434 --mode production --profile edge --output-dir "$RAW/edge/gpt-oss-jina/results" "$GPT_OSS_MODEL"
  run_step edge gpt-oss-sanity infra check_edge_generation_sanity     "$RAW/edge/gpt-oss-jina/results/results.jsonl" "$gpt_policy" "$RAW/edge/gpt-oss-jina/sanity.json"
  run_step edge jina-still-resident infra model_loaded 11437 "$EMBED_MODEL"

  api_ready 11434 || ensure_normal_mode
  run_step edge main-embedding-concurrency infra qualification_benchmark bc250-benchmark concurrency "$E2B_MODEL" "$EMBED_MODEL" --main-url http://127.0.0.1:11434 --embed-url http://127.0.0.1:11437 --output-dir "$RAW/edge/main-embedding-concurrency/results"
  run_step edge device-errors infra check_recent_device_errors "$RAW/edge/kernel-device-errors.txt"
  snapshot edge/final
  write_phase_report resource-edge-results edge
}

phase_agent() {
  set_phase agent "qualifying exclusive package-default agent"
  local dir="$RAW/agent" port
  install -d -m 0700 "$dir"
  systemctl cat ollama-agent.service >/dev/null 2>&1
  bc250-agent-mode enter > "$dir/agent-mode-enter.txt" 2>&1
  wait_api 11436 45
  for port in 11434 11435 11437; do api_ready "$port" && { echo "ERROR: normal Ollama port $port remained available in agent mode." >&2; return 1; }; done
  model_registered 11436 "$AGENT_MODEL" || { echo "ERROR: package-default agent model $AGENT_MODEL is not registered on 11436" >&2; return 1; }
  snapshot agent/active
  run_step agent agent quality qualification_benchmark bc250-benchmark agent "$AGENT_MODEL" --ollama-url http://127.0.0.1:11436 --output-dir "$RAW/agent/benchmark/results"
  bc250-agent-mode leave > "$dir/agent-mode-leave.txt" 2>&1
  wait_api 11434 45; wait_api 11435 45; wait_api 11437 45
  [[ $(systemctl is-active ollama-agent.service 2>/dev/null || true) != active ]]
  record_event "normal-topology-restored" infra pass "agent mode left successfully"
  snapshot agent/restored
  write_phase_report agent-mode-results agent
}

phase_owui() {
  set_phase owui "qualifying packaged Open WebUI RAG configuration"
  local dir="$RAW/owui" rc
  install -d -m 0700 "$dir"
  if [[ ${SKIP_OWUI:-0} -eq 1 ]]; then
    echo "SKIP: authenticated Open WebUI qualification explicitly disabled by --skip-owui" > "$dir/skipped.txt"
    record_event "openwebui-rag" coverage skipped "explicit --skip-owui"
    snapshot owui/skipped
    write_phase_report openwebui-results owui
    return 0
  fi
  validate_owui_token > "$dir/token-recheck.txt" 2>&1
  if bc250-openwebui-setup status --owui-token-file "$OWUI_TOKEN" > "$dir/package-drift-before.txt" 2>&1; then rc=0; else rc=$?; fi
  ((rc == 0)) || { echo "ERROR: Open WebUI package-owned state drift/API failure rc=$rc" >&2; return "$rc"; }
  run_step owui owui-rag quality qualification_benchmark bc250-benchmark owui-rag "$OWUI_RAG_MODEL" --url http://127.0.0.1:3000 --token-file "$OWUI_TOKEN" --output-dir "$dir/packaged-rag/results"
  if bc250-openwebui-setup status --owui-token-file "$OWUI_TOKEN" > "$dir/package-drift-after.txt" 2>&1; then rc=0; else rc=$?; fi
  ((rc == 0)) || { echo "ERROR: Open WebUI package-owned state changed during qualification rc=$rc" >&2; return "$rc"; }
  record_event "openwebui-state-unchanged" infra pass "package-owned settings unchanged"
  snapshot owui/final
  write_phase_report openwebui-results owui
}

quality_cause_report() {
  python3 - "$RAW" "$EVENTS" <<'PY_CAUSES'
import json
import sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1])
events = Path(sys.argv[2])
aggregate = {}
invalid = []
covered_labels = set()
for path in sorted(root.rglob("summary.json")):
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        invalid.append(f"{path}: {exc}")
        continue
    if not isinstance(summary, dict):
        invalid.append(f"{path}: summary root is not an object")
        continue
    category = str(summary.get("category") or path.parent.name)
    counts = summary.get("qualification_counts") or {}
    try:
        passed = int(counts.get("pass") or 0)
        failed = int(counts.get("quality-fail") or 0)
    except (AttributeError, TypeError, ValueError) as exc:
        invalid.append(f"{path}: invalid qualification_counts: {exc}")
        continue
    if failed <= 0:
        continue
    covered_labels.add(category)
    entry = aggregate.setdefault(category, {"pass": 0, "fail": 0, "causes": defaultdict(int)})
    entry["pass"] += passed
    entry["fail"] += failed
    failures = summary.get("failure_kinds") or {}
    if not isinstance(failures, dict):
        invalid.append(f"{path}: failure_kinds is not an object")
        continue
    for name, count in failures.items():
        entry["causes"][str(name)] += int(count)

failed_steps = []
if events.exists():
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split("\t")
        if len(fields) >= 5 and fields[3] == "quality" and fields[4] == "quality-fail":
            failed_steps.append(fields[2])

if not aggregate and not invalid and not failed_steps:
    print("  (none)")
else:
    for category, entry in sorted(aggregate.items()):
        total = entry["pass"] + entry["fail"]
        print(f"  {category:<28} {entry['pass']}/{total}")
        for name, count in sorted(entry["causes"].items()):
            print(f"    {name}={count}")
    for detail in invalid:
        print(f"  canonical summary unavailable — {detail}")
    for label in sorted(set(failed_steps)):
        # Step labels and benchmark categories usually match. If canonical evidence
        # did not yield any failure details, surface that fact rather than hiding it.
        if label not in covered_labels and not any(label in key for key in aggregate):
            print(f"  {label:<28} quality-fail — canonical summary unavailable")
PY_CAUSES
}

create_summary() {
  local out="$WORK/revalidation-summary.txt" p q skipped quality coverage
  read -r p q skipped <<<"$(quality_counts)"; quality="$(quality_state)"
  coverage="$(cat "$COVERAGE_STATE_FILE" 2>/dev/null || echo unknown)"
  printf '%s\n' "$quality" > "$QUALITY_STATE_FILE"
  {
    echo "BC-250 revalidation complete"
    echo
    printf 'Run             %s\n' "$(run_id)"
    printf 'Package         %s\n' "$(rpm -q bc250-llm-server 2>/dev/null || true)"
    printf 'Harness         %s\n' "$HARNESS_VERSION"
    printf 'Kernel          %s\n' "$(uname -r)"
    echo
    printf 'Run state       %s\n' "$(tr '[:lower:]' '[:upper:]' < "$RUN_STATE_FILE" 2>/dev/null || echo UNKNOWN)"
    printf 'Infrastructure  %s\n' "$(tr '[:lower:]' '[:upper:]' < "$INFRA_STATE_FILE" 2>/dev/null || echo UNKNOWN)"
    printf 'Quality         %s       %s pass / %s quality-fail / %s skipped\n' "${quality^^}" "$p" "$q" "$skipped"
    printf 'Restoration     %s\n' "$(tr '[:lower:]' '[:upper:]' < "$RESTORATION_STATE_FILE" 2>/dev/null || echo UNKNOWN)"
    printf 'Coverage        %s\n' "${coverage^^}"
    echo
    echo "Quality failures"
    quality_cause_report
    echo
    echo "Result root"
    echo "  $RAW"
    echo
    echo "Policy"
    echo "  Revalidation qualifies packaged defaults only; tuning/model/hardware A/B comparisons belong to explicit benchmark/diagnostic workflows."
    echo "  The complete live SPI/WGP routing table is the CU authority; numeric kernel/RADV counters are diagnostic only."
    echo "  BC-250 resource headroom is interpreted through residency, MemAvailable and swap context; VRAM/GTT are not additive pools."
  } > "$out"
}

create_final_bundle() {
  local bundle tmp journal_since
  bundle="$REPORT_DIR/$(run_id)-bc250-revalidation-results.tar.gz"
  tmp="${bundle}.tmp.$$"
  create_summary
  record_progress "creating final bundle"
  # The service journal is decisive for shell/control-flow failures and contains no
  # supplied OWUI token material. Limit it to this run when the first event timestamp
  # is available so repeated same-boot revalidations do not contaminate each bundle.
  journal_since="$(awk 'NR==1{print $1; exit}' "$EVENTS" 2>/dev/null || true)"
  if [[ -n $journal_since ]]; then
    journalctl -b -u "$UNIT" --since "$journal_since" --no-pager > "$SERVICE_JOURNAL" 2>&1 || true
  else
    journalctl -b -u "$UNIT" --no-pager > "$SERVICE_JOURNAL" 2>&1 || true
  fi
  local -a items=(events.tsv phase stage stage-started last-event run-id run-state infrastructure-state quality-state restoration-state coverage-state settings.env revalidation-summary.txt results phase-reports)
  [[ ! -e $FAILURE_RC_FILE ]] || items+=(failure-rc)
  [[ ! -e $ERROR_CONTEXT ]] || items+=(error-context.txt)
  [[ ! -e $SERVICE_JOURNAL ]] || items+=(revalidation-service-journal.txt)
  rm -f "$tmp"
  tar -C "$WORK" -czf "$tmp" "${items[@]}"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$bundle"
  FINAL_BUNDLE="$bundle"
  record_progress "final bundle written: $bundle"
}

restore_all() {
  local rc=0
  # Restore appliance state only. The transient credential must remain available
  # through the final authenticated health gate/snapshot and failure evidence.
  if command_exists bc250-agent-mode; then bc250-agent-mode leave >/dev/null 2>&1 || rc=1; fi
  return "$rc"
}

finish_worker_session() {
  local bundle="${FINAL_BUNDLE:-}"
  # Never remove/reload the unit or delete $WORK from inside the executing oneshot.
  # Doing so can make systemd terminate an otherwise successful worker. Leave the
  # finished state for `status`; `cleanup` or the next `start` removes it safely.
  cleanup_transient_token
  [[ -z $bundle ]] || echo "Final bundle: $bundle"
}

finish_failed_run() {
  local rc="$1" label="$2"
  printf '%s\n' "$rc" > "$FAILURE_RC_FILE"
  printf 'failed\n' > "$RUN_STATE_FILE"; printf 'fail\n' > "$INFRA_STATE_FILE"
  if restore_all && ensure_normal_mode >/dev/null 2>&1; then printf 'pass\n' > "$RESTORATION_STATE_FILE"; else printf 'fail\n' > "$RESTORATION_STATE_FILE"; fi
  snapshot "$label" || true
  write_phase_report "$label-results" "$label" || true
  printf 'failed\n' > "$PHASE_FILE"
  create_final_bundle
  finish_worker_session
  exit "$rc"
}

capture_error_context() {
  local rc="$1" command="$2" line="$3" bash_lines="$4" functions="$5"
  {
    echo "timestamp=$(now)"
    echo "rc=$rc"
    echo "phase=$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)"
    echo "stage=$(cat "$STAGE_FILE" 2>/dev/null || echo unknown)"
    echo "worker_bashpid=${WORKER_BASHPID:-}"
    echo "current_bashpid=$BASHPID"
    printf 'bash_command=%q\n' "$command"
    echo "line=$line"
    echo "bash_lineno=$bash_lines"
    echo "funcname=$functions"
  } > "$ERROR_CONTEXT"
}

worker_fail() {
  local rc="${1:-1}" command="${2:-unknown}" line="${3:-unknown}" bash_lines="${4:-}" functions="${5:-}"
  if [[ -n ${WORKER_BASHPID:-} && $BASHPID != "$WORKER_BASHPID" ]]; then trap - ERR; return "$rc"; fi
  trap - ERR TERM INT; set +e
  capture_error_context "$rc" "$command" "$line" "$bash_lines" "$functions" || true
  mkdir "$FAILURE_GUARD" 2>/dev/null || exit "$rc"
  record_event "worker-failure" infra infra-fail "rc=$rc"
  finish_failed_run "$rc" failure
}

worker_abort() {
  if [[ -n ${WORKER_BASHPID:-} && $BASHPID != "$WORKER_BASHPID" ]]; then trap - TERM INT; return 130; fi
  trap - ERR TERM INT; set +e; printf 'abort\n' > "$WORK/ABORT"
  record_event "operator-abort" infra infra-fail "signal=TERM/INT"
  finish_failed_run 130 aborted
}

phase_restore_report() {
  set_phase restore "restoring normal topology and producing final report"
  if restore_all && ensure_normal_mode; then
    printf 'pass\n' > "$RESTORATION_STATE_FILE"
    record_event "restoration" infra pass "normal topology restored"
  else
    printf 'fail\n' > "$RESTORATION_STATE_FILE"
    record_event "restoration" infra infra-fail "normal topology restoration failed"
    return 1
  fi
  health_gate "final-health" "$RAW/restore/bc250-verify-gate.txt"
  snapshot final
  write_phase_report final-restored-state restore
  if [[ $(cat "$COVERAGE_STATE_FILE" 2>/dev/null || echo full) == partial ]]; then
    printf 'incomplete\n' > "$RUN_STATE_FILE"
  else
    printf 'completed\n' > "$RUN_STATE_FILE"
  fi
  printf 'pass\n' > "$INFRA_STATE_FILE"; printf '%s\n' "$(quality_state)" > "$QUALITY_STATE_FILE"
  printf 'done\n' > "$PHASE_FILE"
  record_event "qualification-complete" infra pass "qualification sequence completed; report pending"
  create_final_bundle
  finish_worker_session
}

run_qualification_sequence() {
  phase_preflight; check_abort
  phase_roles; check_abort
  phase_edge; check_abort
  phase_agent; check_abort
  phase_owui; check_abort
  phase_restore_report
}

worker() {
  need_root
  exec 9>"$LOCK"; flock -n 9 || { echo "ERROR: another worker holds $LOCK" >&2; exit 1; }
  rm -rf "$FAILURE_GUARD"; WORKER_BASHPID=$BASHPID
  trap 'worker_fail "$?" "$BASH_COMMAND" "$LINENO" "${BASH_LINENO[*]}" "${FUNCNAME[*]}"' ERR
  trap worker_abort TERM INT; trap worker_exit_cleanup EXIT
  load_settings
  record_event "worker-start" infra pass "pid=$$ kernel=$(uname -r)"
  case "$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)" in
    preflight|initializing) run_qualification_sequence ;;
    done|failed) echo "Run already stopped at phase=$(cat "$PHASE_FILE")." ;;
    *) echo "ERROR: unknown phase: $(cat "$PHASE_FILE" 2>/dev/null || echo missing)" >&2; return 1 ;;
  esac
  trap - ERR TERM INT
}

latest_phase_report_path() {
  find "$PHASE_REPORT_DIR" -maxdepth 1 -type f -name "$(run_id)-*.txt" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
}

latest_bundle_path() {
  find "$REPORT_DIR" -maxdepth 1 -type f -name "$(run_id)-bc250-revalidation-results.tar.gz" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
}

saved_run_harness_version() {
  local report value=""
  if [[ -r "$RUN_HARNESS_VERSION_FILE" ]]; then
    value="$(cat "$RUN_HARNESS_VERSION_FILE" 2>/dev/null || true)"
  fi
  if [[ -z "$value" ]]; then
    report="$(latest_phase_report_path)"
    if [[ -r "$report" ]]; then
      value="$(sed -nE 's/^# BC-250 [^ ]+ revalidation v([^ ]+) phase report$/\1/p' "$report" | head -1)"
    fi
  fi
  printf '%s\n' "${value:-unknown}"
}

effective_run_state() {
  local state service
  state="$(cat "$RUN_STATE_FILE" 2>/dev/null || echo none)"
  service="$(systemctl is-active "$UNIT" 2>/dev/null || true)"
  if [[ "$state" == running && "$service" != active && "$service" != activating && "$service" != reloading ]]; then
    echo incomplete
  else
    echo "$state"
  fi
}

status_raw() {
  echo "harness_version=$HARNESS_VERSION"
  echo "run_harness_version=$(saved_run_harness_version)"
  echo "target_version=$TARGET_VERSION"
  echo "run_id=$(run_id)"
  echo "phase=$(cat "$PHASE_FILE" 2>/dev/null || echo none)"
  echo "stage=$(cat "$STAGE_FILE" 2>/dev/null || echo none)"
  echo "stage_started=$(cat "$STAGE_STARTED_FILE" 2>/dev/null || echo none)"
  echo "last_event=$(cat "$LAST_EVENT_FILE" 2>/dev/null || echo none)"
  echo "run_state=$(effective_run_state)"
  echo "infrastructure=$(cat "$INFRA_STATE_FILE" 2>/dev/null || echo none)"
  echo "quality=$(cat "$QUALITY_STATE_FILE" 2>/dev/null || quality_state)"
  echo "restoration=$(cat "$RESTORATION_STATE_FILE" 2>/dev/null || echo none)"
  echo "coverage=$(cat "$COVERAGE_STATE_FILE" 2>/dev/null || echo none)"
  echo "kernel=$(uname -r)"
  echo "service=$(systemctl is-active "$UNIT" 2>/dev/null || true)"
  echo "phase_reports=$(find "$PHASE_REPORT_DIR" -maxdepth 1 -type f -name "$(run_id)-*.txt" 2>/dev/null | wc -l)"
  echo "latest_phase_report=$(latest_phase_report_path)"
  echo "latest_bundle=$(latest_bundle_path)"
  [[ ! -e $ERROR_CONTEXT ]] || echo "error_context=$ERROR_CONTEXT"
}

status_run() {
  need_root
  local raw=0 phase stage service rid run_version worker position label stage_started last_event
  shift || true
  while (($#)); do case "$1" in --raw) raw=1; shift ;; -h|--help) echo "Usage: sudo bc250-revalidate status [--raw]"; return 0 ;; *) echo "ERROR: unknown status option: $1" >&2; return 2 ;; esac; done
  ((raw == 0)) || { status_raw; return; }
  rid="$(run_id)"; phase="$(cat "$PHASE_FILE" 2>/dev/null || echo none)"; stage="$(cat "$STAGE_FILE" 2>/dev/null || echo none)"
  stage_started="$(cat "$STAGE_STARTED_FILE" 2>/dev/null || echo none)"; last_event="$(cat "$LAST_EVENT_FILE" 2>/dev/null || echo none)"
  service="$(systemctl is-active "$UNIT" 2>/dev/null || true)"; run_version="$(saved_run_harness_version)"; label="$(phase_label "$phase")"; position="$(phase_position "$phase")"
  case "$service" in active|activating|reloading) worker="running ($service)" ;; *) worker="not running${service:+ (systemd: $service)}" ;; esac

  echo "BC-250 revalidation"
  printf 'Current harness : %s\n' "$HARNESS_VERSION"; printf 'Target version  : %s\n' "$TARGET_VERSION"; printf 'Worker          : %s\n' "$worker"; echo
  if [[ -z "$rid" ]]; then echo "Last run        : none"; return; fi
  echo "Run"
  printf '  ID             : %s\n' "$rid"; printf '  Harness        : %s\n' "$run_version"
  printf '  State          : %s\n' "$(effective_run_state)"
  printf '  Infrastructure : %s\n' "$(cat "$INFRA_STATE_FILE" 2>/dev/null || echo unknown)"
  printf '  Quality        : %s\n' "$(cat "$QUALITY_STATE_FILE" 2>/dev/null || quality_state)"
  printf '  Restoration    : %s\n' "$(cat "$RESTORATION_STATE_FILE" 2>/dev/null || echo unknown)"
  printf '  Coverage       : %s\n' "$(cat "$COVERAGE_STATE_FILE" 2>/dev/null || echo unknown)"
  if [[ "$phase" != done && "$phase" != failed ]]; then
    printf '  Phase          : %s %s\n' "${position:-?}" "$label"; printf '  Stage          : %s\n' "$stage"
    printf '  Stage started  : %s\n' "$stage_started"; printf '  Last event     : %s (%s)\n' "$last_event" "$(event_age "$last_event")"
  else
    printf '  Last phase     : %s\n' "$label"
  fi
  printf '  Bundle         : %s\n' "$(latest_bundle_path)"
  [[ ! -e $ERROR_CONTEXT ]] || printf '  Error context  : %s\n' "$ERROR_CONTEXT"
  echo; echo "System"; printf '  Kernel         : %s\n' "$(uname -r)"; printf '  Memory profile : %s\n' "$(current_relevant_args)"
  [[ "$run_version" == unknown || "$run_version" == "$HARNESS_VERSION" ]] || echo "Note: recorded run used harness v$run_version; installed command is v$HARNESS_VERSION."
}

abort_run() {
  need_root
  [[ -d $WORK ]] || { echo "No run state found."; exit 0; }
  touch "$WORK/ABORT"
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    systemctl kill --kill-who=main --signal=TERM "$UNIT" || true
  else
    set +e
    finish_failed_run 130 aborted
  fi
  echo "Abort requested; the worker will restore normal appliance mode before stopping."
}

cleanup_run() {
  need_root
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    echo "ERROR: worker is still active; abort it first." >&2
    exit 1
  fi
  restore_all || true
  rm -f "$UNIT_PATH"
  systemctl daemon-reload
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RUN_DIR"
  echo "Removed revalidation work state/unit. Result bundles under $REPORT_DIR were retained."
}

case "${1:-}" in
  start) start_run "$@" ;;
  worker) worker ;;
  status) status_run ;;
  abort) abort_run ;;
  cleanup) cleanup_run ;;
  help|-h|--help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac

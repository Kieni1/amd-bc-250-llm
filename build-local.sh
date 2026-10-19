#!/usr/bin/env bash
set -Eeuo pipefail

# Local Fedora 44 build driver. All generated state lives under .build/ by default.

usage() {
  cat <<'USAGE'
Usage: ./build-local.sh [--full] [--allow-dirty] [--background] [--jobs N] [--plan]

  (no args)     Fast developer RPM build at normal priority using all detected CPUs.
  --full        Authoritative local Fedora 44 release gate, including exact kernel/Mesa builds and SRPM rebuild.
  --allow-dirty Engineering-only full gate from a dirty tree; never release-qualified.
  --background  Lower CPU/I/O priority for builds while actively using the workstation.
  --jobs N      CPU-heavy worker count (default: nproc).
  --plan        Print the selected build stage plan and exit without changing the system.

Environment:
  BC250_LOCAL_BUILD_ROOT=DIR   Generated build root (default: REPO/.build)
  BC250_LOCAL_BUILD_JOBS=N       Same as --jobs (CLI wins)
  BC250_LOCAL_BUILD_BACKGROUND=1  Same as --background (CLI wins)
  BC250_ALLOW_DIRTY_FULL=1       Allow an engineering full gate from a dirty tree; never release-qualified
USAGE
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

FULL=0
PLAN=0
ALLOW_DIRTY="${BC250_ALLOW_DIRTY_FULL:-0}"
BACKGROUND="${BC250_LOCAL_BUILD_BACKGROUND:-0}"
JOBS="${BC250_LOCAL_BUILD_JOBS:-}"
while (($#)); do
  case "$1" in
    --full) FULL=1; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --plan) PLAN=1; shift ;;
    --background) BACKGROUND=1; shift ;;
    --jobs) [[ $# -ge 2 ]] || { echo "ERROR: --jobs requires a value" >&2; exit 2; }; JOBS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

print_plan() {
  local -a args=(python3 "$SCRIPT_DIR/scripts/release-contract.py" plan --mode fast)
  if ((FULL)); then
    args=(python3 "$SCRIPT_DIR/scripts/release-contract.py" plan --mode full)
    [[ $ALLOW_DIRTY == 1 ]] && args+=(--allow-dirty)
  fi
  "${args[@]}"
}

if ((PLAN)); then
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required to read release-contract.json." >&2; exit 2; }
  print_plan
  exit 0
fi

if [[ $EUID -eq 0 ]]; then
  echo "ERROR: run as your normal user; --full uses sudo only for dependency provisioning." >&2
  exit 2
fi

if [[ -f "$SCRIPT_DIR/Makefile" && -d "$SCRIPT_DIR/packaging" ]]; then
  REPO="$SCRIPT_DIR"
elif [[ -f "$PWD/Makefile" && -d "$PWD/packaging" ]]; then
  REPO="$PWD"
else
  echo "ERROR: run from the bc250-llm-server repository or keep this script in its root." >&2
  exit 2
fi
cd "$REPO"

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required to read release-contract.json." >&2; exit 2; }
TARGET_FEDORA="$(python3 "$REPO/scripts/release-contract.py" field package.fedora)"
PACKAGE_NAME="$(python3 "$REPO/scripts/release-contract.py" field package.name)"
PACKAGE_VERSION="$(python3 "$REPO/scripts/release-contract.py" field package.version)"

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: Fedora 44 host metadata is unavailable." >&2
  exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ ${ID:-} != fedora || ${VERSION_ID:-} != "$TARGET_FEDORA" ]]; then
  echo "ERROR: local RPM builds require Fedora $TARGET_FEDORA (found ${ID:-unknown} ${VERSION_ID:-unknown})." >&2
  exit 2
fi

CPU_COUNT="$(nproc)"
if [[ -z "$JOBS" ]]; then
  JOBS="$CPU_COUNT"
fi
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: jobs must be a positive integer: $JOBS" >&2; exit 2; }
[[ "$BACKGROUND" == 0 || "$BACKGROUND" == 1 ]] || { echo "ERROR: BC250_LOCAL_BUILD_BACKGROUND must be 0 or 1" >&2; exit 2; }
[[ "$ALLOW_DIRTY" == 0 || "$ALLOW_DIRTY" == 1 ]] || { echo "ERROR: BC250_ALLOW_DIRTY_FULL/--allow-dirty must resolve to 0 or 1" >&2; exit 2; }

MODE=fast
((FULL)) && MODE=full
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
BUILD_HOME="${BC250_LOCAL_BUILD_ROOT:-$REPO/.build}"
mkdir -p "$BUILD_HOME"
BUILD_HOME="$(cd -- "$BUILD_HOME" && pwd -P)"
export BC250_LOCAL_BUILD_ROOT="$BUILD_HOME"
RUN_ROOT="$BUILD_HOME/runs/$STAMP"
CACHE_ROOT="$BUILD_HOME/cache"
WORK_DIR="$RUN_ROOT/work"
RPM_DIR="$RUN_ROOT/rpmbuild"
ARTIFACT_DIR="$RUN_ROOT/artifacts"
LOG_DIR="$RUN_ROOT/logs"
LOG="$LOG_DIR/build-local-${MODE}.log"
RESULT="$RUN_ROOT/result.json"
STAGE_FILE="$RUN_ROOT/.stage"
FROZEN_SOURCE_ROOT="$WORK_DIR/frozen-source/$PACKAGE_NAME-$PACKAGE_VERSION"
BUILD_SOURCE_ROOT="$REPO"
mkdir -p "$LOG_DIR" "$CACHE_ROOT/sources" "$CACHE_ROOT/gfx1013" "$CACHE_ROOT/sccache"
printf '%s\n' initialization > "$STAGE_FILE"

export PYTHONDONTWRITEBYTECODE=1
export BC250_GFX1013_BUILD_JOBS="$JOBS"
export CARGO_BUILD_JOBS="$JOBS"
export BC250_GFX1013_KERNEL="${BC250_GFX1013_KERNEL:-$(uname -r)}"

SCCACHE_STATE=unavailable
if command -v sccache >/dev/null 2>&1; then
  export SCCACHE_DIR="$CACHE_ROOT/sccache"
  export RUSTC_WRAPPER=sccache
  SCCACHE_STATE=enabled
fi

MAKE_VARS=(
  "BUILD_DIR=$WORK_DIR"
  "TOPDIR=$RPM_DIR"
  "DISTDIR=$ARTIFACT_DIR"
  "SOURCE_CACHE_DIR=$CACHE_ROOT/sources"
  "GFX_CACHE_DIR=$CACHE_ROOT/gfx1013"
)

RUN=()
PRIORITY_MODE=normal
if ((BACKGROUND)); then
  PRIORITY_MODE=background
  RUN=(nice -n 5)
  if command -v ionice >/dev/null 2>&1; then RUN+=(ionice -c 2 -n 7); fi
fi

CURRENT_STAGE=initialization
STAGE_STARTED_EPOCH=0
START_EPOCH="$(date +%s)"
START_ISO="$(date --iso-8601=seconds)"
GIT_COMMIT=unavailable
GIT_STATE=unavailable
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  GIT_COMMIT="$(git rev-parse HEAD)"
  if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then GIT_STATE=DIRTY; else GIT_STATE=clean; fi
fi
if ((FULL)) && [[ $GIT_STATE != clean && $ALLOW_DIRTY != 1 ]]; then
  echo "ERROR: full release authority requires a clean Git worktree (found $GIT_STATE)." >&2
  echo "       Commit/stash changes, or use --allow-dirty only for an engineering full gate." >&2
  exit 2
fi
GIT_SNAPSHOT_VERIFIED=0

verify_frozen_source_identity() {
  ((FULL)) || return 0
  if [[ $GIT_STATE != clean ]]; then
    GIT_SNAPSHOT_VERIFIED=0
    return 0
  fi
  local current_commit current_state
  current_commit="$(git rev-parse HEAD)"
  if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
    current_state=DIRTY
  else
    current_state=clean
  fi
  if [[ $current_commit != "$GIT_COMMIT" || $current_state != clean ]]; then
    echo "ERROR: source changed during preflight before the release snapshot was frozen." >&2
    echo "       Start from a clean tree and rerun --full; the frozen inputs are preserved for diagnosis." >&2
    return 1
  fi
  GIT_SNAPSHOT_VERIFIED=1
}

require_tools() {
  local missing=() tool
  local tools=(make rpm rpmbuild rpm2cpio cpio rpmlint ruff shellcheck python3 sha256sum curl tar gzip xz find awk sed grep stat cmp timeout mktemp)
  ((FULL)) && tools+=(sudo free git)
  for tool in "${tools[@]}"; do command -v "$tool" >/dev/null 2>&1 || missing+=("$tool"); done
  ((${#missing[@]} == 0)) || { printf 'ERROR: missing local-build tools: %s\n' "${missing[*]}" >&2; return 2; }
}

SUDO_KEEPALIVE_PID=""

start_sudo_session() {
  ((FULL)) || return 0
  set_stage "sudo authentication"
  echo
  echo "=== $CURRENT_STAGE ==="
  echo "Full release builds need sudo only for exact Fedora kernel/Mesa dependency provisioning."
  echo "Authenticate once now; the credential will be refreshed non-interactively while this build runs."
  if ! sudo -v; then
    echo "ERROR: sudo authentication failed; full release build cannot provision dependencies." >&2
    return 2
  fi
  (
    while sleep 60; do
      sudo -n -v >/dev/null 2>&1 || exit 0
    done
  ) &
  SUDO_KEEPALIVE_PID=$!
  finish_stage
}

stop_sudo_session() {
  local pid=${SUDO_KEEPALIVE_PID:-}
  [[ -n $pid ]] || return 0
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true
  SUDO_KEEPALIVE_PID=""
}

checkpoint() {
  local label=$1 now_epoch now_iso elapsed
  now_epoch="$(date +%s)"
  now_iso="$(date --iso-8601=seconds)"
  elapsed=$((now_epoch - START_EPOCH))
  printf '[%s] +%02d:%02d:%02d %s\n' \
    "$now_iso" "$((elapsed / 3600))" "$(((elapsed % 3600) / 60))" "$((elapsed % 60))" "$label"
}

set_stage() {
  CURRENT_STAGE="$1"
  STAGE_STARTED_EPOCH="$(date +%s)"
  printf '%s\n' "$CURRENT_STAGE" > "$STAGE_FILE"
  checkpoint "START $CURRENT_STAGE"
}

finish_stage() {
  local now_epoch stage_elapsed
  now_epoch="$(date +%s)"
  stage_elapsed=$((now_epoch - STAGE_STARTED_EPOCH))
  checkpoint "DONE  $CURRENT_STAGE (stage elapsed $((stage_elapsed / 60))m $((stage_elapsed % 60))s)"
}

run_stage() {
  set_stage "$1"; shift
  echo
  echo "=== $CURRENT_STAGE ==="
  "${RUN[@]}" "$@"
  finish_stage
}

run_make_stage() {
  local stage=$1; shift
  run_stage "$stage" make "${MAKE_VARS[@]}" "$@"
}

main_rpm() {
  local -a matches=()
  shopt -s nullglob
  matches=("$ARTIFACT_DIR"/"$PACKAGE_NAME"-*.x86_64.rpm)
  shopt -u nullglob
  local -a filtered=() path
  for path in "${matches[@]}"; do
    [[ $path == *-debuginfo-* || $path == *-debugsource-* ]] || filtered+=("$path")
  done
  ((${#filtered[@]} == 1)) || { printf 'ERROR: expected exactly one main RPM, found %d\n' "${#filtered[@]}" >&2; return 1; }
  printf '%s\n' "${filtered[0]}"
}

show_artifacts() {
  [[ -d "$ARTIFACT_DIR" ]] || { echo "ERROR: artifact directory is missing" >&2; return 1; }
  local rpm_path
  rpm_path="$(main_rpm)"
  echo
  echo "=== artifacts ==="
  ls -lh "$ARTIFACT_DIR"
  echo
  echo "=== main package ==="
  rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' "$rpm_path"
  echo
  echo "=== checksums ==="
  [[ -f "$ARTIFACT_DIR/SHA256SUMS" ]] && cat "$ARTIFACT_DIR/SHA256SUMS" || sha256sum "$ARTIFACT_DIR"/*.rpm
}

provision_full_deps() {
  local helper
  for helper in "$BUILD_SOURCE_ROOT/scripts/provision-gfx1013-kernel-builddeps.sh" "$BUILD_SOURCE_ROOT/scripts/provision-gfx1013-mesa-builddeps.sh"; do
    [[ -x $helper ]] || { echo "ERROR: $helper is missing or not executable." >&2; return 2; }
  done
  [[ -d "/usr/src/kernels/$BC250_GFX1013_KERNEL" ]] || {
    echo "ERROR: missing /usr/src/kernels/$BC250_GFX1013_KERNEL" >&2
    echo "       Install: sudo dnf install kernel-devel-$BC250_GFX1013_KERNEL" >&2
    return 2
  }
  set_stage "provision exact Fedora kernel + Mesa build dependencies"
  echo
  echo "=== $CURRENT_STAGE ==="
  sudo -n env BC250_GFX1013_KERNEL="$BC250_GFX1013_KERNEL" BC250_GFX1013_CACHE_ROOT="$CACHE_ROOT/gfx1013" "$BUILD_SOURCE_ROOT/scripts/provision-gfx1013-kernel-builddeps.sh"
  sudo -n env BC250_GFX1013_CACHE_ROOT="$CACHE_ROOT/gfx1013" "$BUILD_SOURCE_ROOT/scripts/provision-gfx1013-mesa-builddeps.sh"
  # Provisioning is privileged only because dnf builddep is privileged. Return
  # cached source ownership to the non-root build user for subsequent runs.
  sudo -n chown -R "$(id -u):$(id -g)" "$CACHE_ROOT/gfx1013"
  finish_stage
}

build_fast() {
  run_make_stage "make sources" sources
  run_make_stage "make lint" lint
  run_make_stage "make preflight" preflight
  run_make_stage "RPM build / %check" RPM_TREE_TARGET=rpm-tree-prevalidated rpm
  set_stage "rpmlint"
  echo
  echo "=== $CURRENT_STAGE ==="
  "${RUN[@]}" rpmlint -c packaging/rpmlint.toml "$ARTIFACT_DIR"/*.rpm
  finish_stage
  show_artifacts
  echo
  echo "===== FAST LOCAL RPM GATES PASSED ====="
  echo "Not release-qualified: exact GFX kernel/Mesa production checks and clean SRPM rebuild were skipped."
}

build_full() {
  set_stage "authoritative release preflight"
  echo
  echo "=== $CURRENT_STAGE (non-root) ==="
  "${RUN[@]}" make "${MAKE_VARS[@]}" release-gate-preflight </dev/null
  verify_frozen_source_identity
  checkpoint "frozen source identity verified"
  finish_stage

  [[ -d "$FROZEN_SOURCE_ROOT" ]] || {
    echo "ERROR: preflight did not produce frozen source tree: $FROZEN_SOURCE_ROOT" >&2
    return 1
  }
  BUILD_SOURCE_ROOT="$FROZEN_SOURCE_ROOT"

  provision_full_deps

  set_stage "authoritative release build"
  echo
  echo "=== $CURRENT_STAGE (non-root; frozen source) ==="
  "${RUN[@]}" make -C "$BUILD_SOURCE_ROOT" "${MAKE_VARS[@]}" release-gate-postprovision </dev/null
  finish_stage
  checkpoint "release build gates complete"
  show_artifacts
  echo
  if [[ $GIT_STATE == clean && $GIT_SNAPSHOT_VERIFIED == 1 ]]; then
    echo "===== FULL LOCAL RELEASE GATE PASSED ====="
  else
    echo "===== FULL ENGINEERING GATE PASSED — SOURCE NOT CLEAN ====="
    echo "Not release-qualified: source state is $GIT_STATE. Commit/stash changes and rerun --full for release authority."
  fi
}

write_result() {
  local rc=$1 finished_iso=$2 duration=$3 outcome=FAIL main='' package='' ollama='' hashes='[]' stage='initialization'
  ((rc == 0)) && outcome=PASS
  [[ -r "$STAGE_FILE" ]] && stage="$(<"$STAGE_FILE")"
  ollama="$(sed -n 's/^BC250_OLLAMA_VERSION=//p' "$BUILD_SOURCE_ROOT/config/runtime.env" | head -1)"
  if [[ -d "$ARTIFACT_DIR" ]]; then
    main="$(main_rpm 2>/dev/null || true)"
    [[ -z $main ]] || package="$(rpm -qp --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}' "$main" 2>/dev/null || true)"
  fi
  python3 - "$RESULT" "$outcome" "$rc" "$MODE" "$stage" "$START_ISO" "$finished_iso" "$duration" "$REPO" "$RUN_ROOT" "$GIT_COMMIT" "$GIT_STATE" "$(uname -r)" "$ollama" "$package" "$ARTIFACT_DIR" "$BUILD_SOURCE_ROOT" "$WORK_DIR/RPM-INPUTS.sha256" "$GIT_SNAPSHOT_VERIFIED" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
(
    target, outcome, rc, mode, stage, started, finished, duration, repo, run_root,
    commit, git_state, kernel, ollama, package, artifact_dir, build_source_root, frozen_inputs_path, snapshot_verified,
) = sys.argv[1:]
artifacts = []
root = Path(artifact_dir)
if root.is_dir():
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append({"name": path.name, "bytes": path.stat().st_size, "sha256": digest})
frozen_inputs = {}
frozen_path = Path(frozen_inputs_path)
if frozen_path.is_file():
    for line in frozen_path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            frozen_inputs[parts[1]] = parts[0]
contract_path = Path(build_source_root) / "release-contract.json"
contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest() if contract_path.is_file() else None
snapshot_verified_bool = snapshot_verified == "1"
release_qualified = outcome == "PASS" and mode == "full" and git_state == "clean" and snapshot_verified_bool
qualification = (
    "release" if release_qualified
    else "engineering" if mode == "full" and outcome == "PASS"
    else "developer" if mode == "fast" and outcome == "PASS"
    else "failed"
)
payload = {
    "schema": "bc250.local-build.v1",
    "result": outcome,
    "qualification": qualification,
    "release_qualified": release_qualified,
    "exit_status": int(rc),
    "mode": mode,
    "failed_stage": stage if outcome != "PASS" else None,
    "started_at": started,
    "finished_at": finished,
    "duration_seconds": int(duration),
    "repository": repo,
    "run_root": run_root,
    "git_commit": None if commit == "unavailable" else commit,
    "git_state": git_state,
    "git_snapshot_verified": snapshot_verified_bool,
    "kernel": kernel,
    "ollama_pin": ollama or None,
    "package": package or None,
    "validated_source_root": build_source_root,
    "release_contract_sha256": contract_sha256,
    "frozen_rpm_inputs": frozen_inputs,
    "artifacts": artifacts,
}
Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

set +e
(
  set -Eeuo pipefail
  trap stop_sudo_session EXIT
  require_tools
  checkpoint "build start"
  if ((FULL)); then
    start_sudo_session
  fi
  echo "bc250 local build"
  echo "mode:        $MODE"
  echo "repository:  $REPO"
  echo "build root:  $RUN_ROOT"
  echo "cache:       $CACHE_ROOT"
  echo "kernel:      $(uname -r)"
  echo "Fedora:      ${VERSION_ID}"
  echo "cpus/jobs:   $CPU_COUNT/$JOBS"
  echo "priority:    $PRIORITY_MODE"
  echo "sccache:     $SCCACHE_STATE"
  if [[ $SCCACHE_STATE == enabled ]]; then
    echo
    echo "=== sccache statistics (before) ==="
    sccache --show-stats || echo "WARNING: unable to read initial sccache statistics."
    echo
  fi
  echo "source:      $GIT_COMMIT ($GIT_STATE)"
  echo "Ollama pin:  $(sed -n 's/^BC250_OLLAMA_VERSION=//p' "$REPO/config/runtime.env" | head -1)"
  echo "started:     $START_ISO"
  if ((FULL)); then
    build_full
  else
    build_fast
  fi
  checkpoint "build command phase complete"
) 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

if [[ $SCCACHE_STATE == enabled ]]; then
  {
    echo
    echo "=== sccache statistics (after) ==="
    sccache --show-stats || echo "WARNING: unable to read final sccache statistics."
  } 2>&1 | tee -a "$LOG"
fi

FINISH_EPOCH="$(date +%s)"
FINISH_ISO="$(date --iso-8601=seconds)"
DURATION=$((FINISH_EPOCH - START_EPOCH))
FINAL_MAIN_RPM=''
if ((rc == 0)); then
  if ! FINAL_MAIN_RPM="$(main_rpm)"; then
    echo "ERROR: successful build did not leave exactly one main RPM artifact." >&2
    rc=2
  fi
fi
write_result "$rc" "$FINISH_ISO" "$DURATION"

if ((rc == 0)); then
  rm -rf -- "$WORK_DIR" "$RPM_DIR"
fi
FAILED_STAGE="$(cat "$STAGE_FILE" 2>/dev/null || printf initialization)"
rm -f -- "$STAGE_FILE"
find "$RUN_ROOT" -depth -type d -empty -delete 2>/dev/null || true

echo
echo "Build result: $([[ $rc -eq 0 ]] && echo PASS || echo FAIL)"
echo "Mode:         $MODE"
if ((rc == 0 && FULL)); then
  if [[ $GIT_STATE == clean && $GIT_SNAPSHOT_VERIFIED == 1 ]]; then
    echo "Qualification: full release gate PASS"
  else
    echo "Qualification: engineering only ($GIT_STATE source)"
  fi
fi
echo "Duration:     $((DURATION / 60))m $((DURATION % 60))s"
if ((rc != 0)); then echo "Failed stage: $FAILED_STAGE"; fi
echo "Run folder:   $RUN_ROOT"
echo "Log:          $LOG"
echo "Result:       $RESULT"
if ((rc == 0)); then
  echo "$FINAL_MAIN_RPM"
fi
exit "$rc"

#!/usr/bin/env bash
# Delete Open WebUI files through its API by age and then total-size ceiling.
set -Eeuo pipefail
umask 0077
OWUI_URL="${OWUI_URL:-http://127.0.0.1:3000}"
OWUI_API_KEY="${OWUI_API_KEY:?Set OWUI_API_KEY in /etc/bc250-llm-server/maintenance.env}"
[[ "$OWUI_API_KEY" != "REPLACE_WITH_ADMIN_API_KEY" ]] || { echo "ERROR: replace the placeholder OWUI_API_KEY first." >&2; exit 1; }
MAX_AGE_DAYS="${MAX_AGE_DAYS:-90}"
MAX_TOTAL_GB="${MAX_TOTAL_GB:-100}"
DRY_RUN="${DRY_RUN:-0}"

[[ "$MAX_AGE_DAYS" =~ ^[0-9]+$ ]] || { echo "ERROR: MAX_AGE_DAYS must be integer." >&2; exit 1; }
[[ "$MAX_TOTAL_GB" =~ ^[0-9]+$ ]] || { echo "ERROR: MAX_TOTAL_GB must be integer." >&2; exit 1; }
[[ "$DRY_RUN" == 0 || "$DRY_RUN" == 1 ]] || { echo "ERROR: DRY_RUN must be 0 or 1." >&2; exit 1; }
((MAX_AGE_DAYS > 0 || MAX_TOTAL_GB > 0)) || {
  echo "ERROR: MAX_AGE_DAYS and MAX_TOTAL_GB cannot both be disabled (0)." >&2
  exit 1
}

AUTH=(-H "Authorization: Bearer ${OWUI_API_KEY}")
now="$(date +%s)"
max_total_bytes=$(( MAX_TOTAL_GB * 1024 * 1024 * 1024 ))
cutoff=$(( now - MAX_AGE_DAYS * 86400 ))
log(){ printf '%s %s\n' "$(date '+%F %T')" "$*"; }

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
rows_file="$tmpdir/files.tsv"

page=1; fetched=0; expected_total=-1
while :; do
  json="$tmpdir/page-${page}.json"
  curl --fail --silent --show-error --retry 3 --retry-all-errors \
    --connect-timeout 10 --max-time 60 "${AUTH[@]}" \
    "${OWUI_URL}/api/v1/files/?content=false&page=${page}" > "$json"
  summary="$(python3 - "$json" <<'PY_PAGE'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
if isinstance(data, dict):
    items = data.get("items") if isinstance(data.get("items"), list) else data.get("files")
    total = data.get("total", -1)
else:
    items, total = data, -1
if not isinstance(items, list):
    raise SystemExit("API response is not a file list")
try:
    total = int(total)
except (TypeError, ValueError):
    total = -1
print(len(items), total)
PY_PAGE
)" || { log "ERROR: invalid Open WebUI file-list JSON; aborting without deletion."; exit 1; }
  read -r page_count page_total <<< "$summary"
  if (( page_total >= 0 )); then
    if (( expected_total < 0 )); then
      expected_total=$page_total
    elif (( page_total != expected_total )); then
      log "ERROR: Open WebUI file total changed while listing; aborting without deletion."
      exit 1
    fi
  fi
  ((page_count > 0)) || break
  fetched=$((fetched + page_count))
  ((expected_total >= 0 && fetched >= expected_total)) && break
  if ((page_count < 50)); then
    if ((expected_total >= 0 && fetched < expected_total)); then
      log "ERROR: Open WebUI pagination ended before the advertised total; aborting without deletion."
      exit 1
    fi
    break
  fi
  page=$((page + 1))
  ((page <= 10000)) || { log "ERROR: unreasonable Open WebUI pagination depth; aborting."; exit 1; }
done

if ! python3 - "$tmpdir"/page-*.json > "$rows_file" <<'PY_FILES'
import datetime, json, sys

def timestamp(value):
    if value is None: return 0
    if isinstance(value, (int, float)):
        value = float(value)
        if value > 10_000_000_000: value /= 1000
        return int(value)
    try:
        s = str(value).replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(s).timestamp())
    except (TypeError, ValueError, OverflowError):
        return 0

def byte_size(value):
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else -1
    except (TypeError, ValueError, OverflowError):
        return -1

rows=[]; seen=set()
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("items") if isinstance(data.get("items"), list) else data.get("files")
    if not isinstance(data, list):
        raise SystemExit("API response is not a file list")
    for f in data:
        if not isinstance(f, dict): continue
        fid=f.get("id")
        if not fid or str(fid) in seen: continue
        seen.add(str(fid))
        ts=timestamp(f.get("created_at"))
        meta=f.get("meta") if isinstance(f.get("meta"), dict) else {}
        size=byte_size(meta.get("size", f.get("size")))
        rows.append((ts, size, str(fid)))
for ts, size, fid in sorted(rows, key=lambda row: (row[0] <= 0, row[0], row[2])):
    print(f"{ts}\t{size}\t{fid}")
PY_FILES
then
  log "ERROR: invalid Open WebUI file-list JSON; aborting without deletion."
  exit 1
fi

mapfile -t rows < "$rows_file"
total=0; unknown_age=0; unknown_size=0
for row in "${rows[@]}"; do
  IFS=$'\t' read -r ts size _ <<< "$row"
  ((ts > 0)) || unknown_age=$((unknown_age+1))
  if ((size >= 0)); then total=$((total+size)); else unknown_size=$((unknown_size+1)); fi
done
age_label="${MAX_AGE_DAYS}d"; ceiling_label="${MAX_TOTAL_GB}GiB"
((MAX_AGE_DAYS > 0)) || age_label=disabled
((MAX_TOTAL_GB > 0)) || ceiling_label=disabled
log "Files=${#rows[@]} known_total=$((total/1024/1024))MiB ceiling=${ceiling_label} age=${age_label} dry_run=${DRY_RUN}"
if ((unknown_age > 0 || unknown_size > 0)); then
  log "WARNING: preserving uncertain metadata for size pruning (unknown_age=${unknown_age} unknown_size=${unknown_size})."
fi

deleted=0; freed=0; failures=0
delete_one(){
  local ts="$1" size="$2" id="$3" reason="$4" age_label="unknown" size_label="unknown"
  ((ts > 0)) && age_label="$(((now-ts)/86400))d"
  ((size >= 0)) && size_label="$((size/1024/1024))MiB"
  if [[ "$DRY_RUN" == 1 ]]; then
    log "WOULD delete [$reason] id=$id size=$size_label age=$age_label"
  elif ! curl --fail --silent --show-error --retry 2 --retry-all-errors \
      --connect-timeout 10 --max-time 60 -X DELETE "${AUTH[@]}" \
      "${OWUI_URL}/api/v1/files/${id}" >/dev/null; then
    log "FAILED delete id=$id"
    failures=$((failures+1))
    return 1
  else
    log "deleted [$reason] id=$id size=$size_label"
  fi
  deleted=$((deleted+1))
  if ((size >= 0)); then freed=$((freed+size)); total=$((total-size)); fi
}

remaining=()
for row in "${rows[@]}"; do
  IFS=$'\t' read -r ts size id <<< "$row"
  if (( MAX_AGE_DAYS > 0 && ts > 0 && ts < cutoff )); then
    delete_one "$ts" "$size" "$id" "age>${MAX_AGE_DAYS}d" || remaining+=("$row")
  else
    remaining+=("$row")
  fi
done
if ((MAX_TOTAL_GB > 0)); then
  for row in "${remaining[@]}"; do
    (( total <= max_total_bytes )) && break
    IFS=$'\t' read -r ts size id <<< "$row"
    # Files without a trustworthy age or size are never selected by the
    # storage ceiling. An administrator must review them in Open WebUI.
    ((ts > 0 && size >= 0)) || continue
    delete_one "$ts" "$size" "$id" "size-ceiling" || true
  done
  if ((total > max_total_bytes)); then
    log "WARNING: known upload total remains above the ceiling; review preserved uncertain files in Open WebUI."
  fi
fi

log "Done. deleted/planned=$deleted freed/planned=$((freed/1024/1024))MiB remaining/simulated=$((total/1024/1024))MiB failures=$failures"
(( failures == 0 ))

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

AUTH=(-H "Authorization: Bearer ${OWUI_API_KEY}")
now="$(date +%s)"
max_total_bytes=$(( MAX_TOTAL_GB * 1024 * 1024 * 1024 ))
cutoff=$(( now - MAX_AGE_DAYS * 86400 ))
log(){ printf '%s %s\n' "$(date '+%F %T')" "$*"; }

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
json="$tmpdir/files.json"
rows_file="$tmpdir/files.tsv"

curl --fail --silent --show-error --retry 3 --retry-all-errors \
  --connect-timeout 10 --max-time 60 "${AUTH[@]}" \
  "${OWUI_URL}/api/v1/files/?content=false" > "$json"

if ! python3 - "$json" > "$rows_file" <<'PY_FILES'
import datetime, json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
if isinstance(data, dict):
    data = data.get("items") or data.get("files")
if not isinstance(data, list):
    raise SystemExit("API response is not a file list")

def timestamp(value):
    if value is None: return 0
    if isinstance(value, (int, float)):
        value = float(value)
        if value > 10_000_000_000: value /= 1000
        return int(value)
    s = str(value).replace("Z", "+00:00")
    return int(datetime.datetime.fromisoformat(s).timestamp())

rows=[]
for f in data:
    if not isinstance(f, dict): continue
    fid=f.get("id")
    if not fid: continue
    ts=timestamp(f.get("created_at"))
    size=(f.get("meta") or {}).get("size", f.get("size", 0)) or 0
    rows.append((ts, int(size), str(fid)))
for ts, size, fid in sorted(rows):
    print(f"{ts}\t{size}\t{fid}")
PY_FILES
then
  log "ERROR: invalid Open WebUI file-list JSON; aborting without deletion."
  exit 1
fi

mapfile -t rows < "$rows_file"
total=0
for row in "${rows[@]}"; do IFS=$'\t' read -r _ size _ <<< "$row"; total=$((total+size)); done
log "Files=${#rows[@]} total=$((total/1024/1024))MiB ceiling=${MAX_TOTAL_GB}GiB age=${MAX_AGE_DAYS}d dry_run=${DRY_RUN}"

deleted=0; freed=0; failures=0
delete_one(){
  local ts="$1" size="$2" id="$3" reason="$4" age_label="unknown"
  ((ts > 0)) && age_label="$(((now-ts)/86400))d"
  if [[ "$DRY_RUN" == 1 ]]; then
    log "WOULD delete [$reason] id=$id size=$((size/1024/1024))MiB age=$age_label"
  elif ! curl --fail --silent --show-error --retry 2 --retry-all-errors \
      --connect-timeout 10 --max-time 60 -X DELETE "${AUTH[@]}" \
      "${OWUI_URL}/api/v1/files/${id}" >/dev/null; then
    log "FAILED delete id=$id"
    failures=$((failures+1))
    return 1
  else
    log "deleted [$reason] id=$id size=$((size/1024/1024))MiB"
  fi
  deleted=$((deleted+1)); freed=$((freed+size)); total=$((total-size))
}

remaining=()
for row in "${rows[@]}"; do
  IFS=$'\t' read -r ts size id <<< "$row"
  if (( ts > 0 && ts < cutoff )); then
    delete_one "$ts" "$size" "$id" "age>${MAX_AGE_DAYS}d" || remaining+=("$row")
  else
    remaining+=("$row")
  fi
done
for row in "${remaining[@]}"; do
  (( total <= max_total_bytes )) && break
  IFS=$'\t' read -r ts size id <<< "$row"
  delete_one "$ts" "$size" "$id" "size-ceiling" || true
done

log "Done. deleted/planned=$deleted freed/planned=$((freed/1024/1024))MiB remaining/simulated=$((total/1024/1024))MiB failures=$failures"
(( failures == 0 ))

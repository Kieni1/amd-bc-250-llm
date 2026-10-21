#!/usr/bin/env bash
set -uo pipefail

if (($# < 2)); then
  echo "usage: $0 STAGE COMMAND [ARG ...]" >&2
  exit 2
fi

stage=$1
shift
start=$(date +%s)
set +e
"$@"
rc=$?
set -e
end=$(date +%s)
printf 'BC250_TIMING stage=%s seconds=%d rc=%d\n' "$stage" "$((end - start))" "$rc"
exit "$rc"

#!/usr/bin/env bash
# Generate and optionally create a commit for the already staged diff.
set -Eeuo pipefail
umask 0077

YES=0
[[ "${1:-}" == "--yes" ]] && { YES=1; shift; }
[[ $# -eq 0 ]] || {
  echo "Usage: bc250-code-commit [--yes]" >&2
  exit 2
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "ERROR: not inside a Git work tree." >&2
  exit 1
}
git diff --cached --quiet && {
  echo "ERROR: no staged changes. Stage only the files intended for this commit." >&2
  exit 1
}

MAX_DIFF_BYTES="${CODING_AGENT_MAX_DIFF_BYTES:-60000}"
diff_file="$(mktemp)"
msg_file="$(mktemp)"
trap 'rm -f "$diff_file" "$msg_file"' EXIT
git diff --cached --binary --no-ext-diff > "$diff_file"
size="$(wc -c < "$diff_file")"
(( size <= MAX_DIFF_BYTES )) || {
  echo "ERROR: staged diff is ${size} bytes; limit is ${MAX_DIFF_BYTES}." >&2
  exit 1
}

bc250-code commit "$diff_file" "$msg_file"

subject="$(sed -n 's/^SUBJECT:[[:space:]]*//p' "$msg_file" | head -1)"
body="$(awk '
  BEGIN { in_body=0 }
  /^BODY:[[:space:]]*/ {
    in_body=1
    sub(/^BODY:[[:space:]]*/, "")
    if (length) print
    next
  }
  in_body { print }
' "$msg_file")"
[[ -n "$subject" ]] || {
  echo "ERROR: model response did not contain SUBJECT:." >&2
  cat "$msg_file" >&2
  exit 1
}
(( ${#subject} <= 72 )) || {
  echo "ERROR: generated subject exceeds 72 characters." >&2
  exit 1
}

printf '\nProposed commit:\n  %s\n' "$subject"
[[ -n "${body//[[:space:]]/}" ]] && printf '\n%s\n' "$body"
printf '\nStaged files:\n'
git diff --cached --name-status

if (( YES == 0 )); then
  read -r -p "Create this local commit? [y/N]: " answer
  case "${answer,,}" in y|yes) ;; *) echo "Cancelled."; exit 0 ;; esac
fi

if [[ -n "${body//[[:space:]]/}" ]]; then
  git commit -m "$subject" -m "$body"
else
  git commit -m "$subject"
fi

echo "Commit created locally. Nothing was pushed."

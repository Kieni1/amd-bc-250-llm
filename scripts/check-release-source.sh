#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-${BC250_BUILD_DIR:-$ROOT/build}/SOURCE-IDENTITY.json}"
require_git="${BC250_REQUIRE_GIT_SOURCE:-0}"
mkdir -p "$(dirname -- "$OUT")"

if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  status="$(git -C "$ROOT" status --porcelain --untracked-files=all)"
  if [[ -n "$status" ]]; then
    echo "ERROR: release-gate source tree is dirty at freeze time:" >&2
    printf '%s\n' "$status" >&2
    exit 1
  fi
  commit="$(git -C "$ROOT" rev-parse HEAD)"
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    github_sha="${GITHUB_SHA:-}"
    if [[ -z "$github_sha" ]]; then
      echo "ERROR: GITHUB_ACTIONS=true but GITHUB_SHA is empty." >&2
      exit 1
    fi
    if [[ "$commit" != "$github_sha" ]]; then
      echo "ERROR: checked-out HEAD does not match authoritative GitHub run SHA." >&2
      echo "  HEAD=$commit" >&2
      echo "  GITHUB_SHA=$github_sha" >&2
      exit 1
    fi
  fi
  printf '{"schema":"bc250.source-identity.v1","kind":"git","commit":"%s","clean":true}\n' "$commit" >"$OUT"
else
  if [[ "$require_git" == "1" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "ERROR: authoritative GitHub release build requires a Git worktree." >&2
    exit 1
  fi
  printf '{"schema":"bc250.source-identity.v1","kind":"archive","commit":null,"clean":null}\n' >"$OUT"
fi

echo "Release source identity: $(cat "$OUT")"

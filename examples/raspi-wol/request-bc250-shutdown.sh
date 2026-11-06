#!/usr/bin/env bash
# Raspberry Pi: call only the forced-command SSH power-control account.
set -Eeuo pipefail
SSH_CONFIG="${BC250_PI_SSH_CONFIG:-/etc/bc250/ssh_config}"
[[ -r "$SSH_CONFIG" ]] || { echo "ERROR: missing SSH config: $SSH_CONFIG" >&2; exit 1; }
set +e
ssh -F "$SSH_CONFIG" -o BatchMode=yes bc250-power
rc=$?
set -e
case "$rc" in
  0) echo 'BC-250 accepted the request (it may have deferred for active work).'; exit 0 ;;
  1) echo 'BC-250 refused the shutdown request; inspect its maintenance policy.' >&2; exit 1 ;;
  *) echo "ERROR: SSH/power request failed (exit $rc)." >&2; exit "$rc" ;;
esac

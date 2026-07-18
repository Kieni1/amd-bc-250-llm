#!/usr/bin/env bash
# Run from a different LAN machine, not from the BC-250 itself.
set -Eeuo pipefail
HOST="${1:?Usage: verify-lan.sh <server-host-or-ip>}"
HTTP_PORT="${HTTP_PORT:-80}"
PASS=0; FAIL=0
ok(){ echo "[ OK ] $*"; PASS=$((PASS+1)); }
bad(){ echo "[FAIL] $*"; FAIL=$((FAIL+1)); }
port_open(){ timeout 4 bash -c "</dev/tcp/$HOST/$1" >/dev/null 2>&1; }

if curl --fail --silent --show-error --connect-timeout 5 --max-time 15     "http://${HOST}:${HTTP_PORT}/" >/dev/null; then
  ok "HTTP UI reachable (unencrypted testing endpoint)"
else
  bad "HTTP UI not reachable"
fi
for port in 3000 11434 11435 9998; do
  if port_open "$port"; then bad "port $port is reachable from LAN"
  else ok "port $port is not reachable from LAN"; fi
done
echo "$PASS ok / $FAIL fail"
exit "$FAIL"

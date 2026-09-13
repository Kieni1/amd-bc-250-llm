#!/usr/bin/env bash
# Optional Raspberry Pi-facing maintenance and read-only backup export setup.
set -Eeuo pipefail

POWER_USER="${BC250_POWER_CONTROL_USER:-bc250-power-control}"
POWER_HOME="${BC250_POWER_CONTROL_HOME:-/var/lib/bc250-power-control}"
EXPORT_USER="${BC250_BACKUP_EXPORT_USER:-bc250-backup-export}"
EXPORT_GROUP="${BC250_BACKUP_EXPORT_GROUP:-bc250-backup-export}"
EXPORT_HOME="${BC250_BACKUP_EXPORT_HOME:-/var/lib/bc250-backup-export}"
BACKUP_ROOT="${BC250_BACKUP_ROOT:-/var/backups/bc250-llm-server}"

require_root() {
  [[ ${EUID} -eq 0 ]] || { echo "ERROR: run this command with sudo." >&2; exit 1; }
}

systemd_available() { [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; }

ensure_account() {
  local user="$1" group="$2" home="$3"
  getent group "$group" >/dev/null 2>&1 || groupadd --system "$group"
  id "$user" >/dev/null 2>&1 || \
    useradd --system --gid "$group" --home-dir "$home" --create-home --shell /bin/sh "$user"
  passwd -l "$user" >/dev/null 2>&1 || true
  install -d -m0700 -o "$user" -g "$group" "$home/.ssh"
  touch "$home/.ssh/authorized_keys"
  chown "$user:$group" "$home/.ssh/authorized_keys"
  chmod 0600 "$home/.ssh/authorized_keys"
}

firewall_zone() {
  local nic zone
  nic="$(ip route show default 2>/dev/null | awk 'NR==1 {print $5}')"
  [[ -z "$nic" ]] || zone="$(firewall-cmd --get-zone-of-interface="$nic" 2>/dev/null || true)"
  [[ -n "${zone:-}" && "$zone" != 'no zone' ]] || zone="$(firewall-cmd --get-default-zone 2>/dev/null || true)"
  printf '%s' "${zone:-public}"
}

firewall_state() {
  local zone
  if systemctl is-active --quiet firewalld.service 2>/dev/null && command -v firewall-cmd >/dev/null 2>&1; then
    zone="$(firewall_zone)"
    firewall-cmd --quiet --zone="$zone" --permanent --query-service="$1" && printf 'allowed (%s)' "$zone" || printf 'blocked (%s)' "$zone"
  else
    printf unavailable
  fi
}

ensure_ssh_path() {
  local changed=0 service zone
  systemd_available || { echo "ERROR: systemd is not available." >&2; return 1; }
  systemctl cat sshd.service >/dev/null 2>&1 || {
    echo "ERROR: sshd is unavailable. Install it first: sudo dnf install openssh-server" >&2
    return 1
  }
  systemctl enable --now sshd.service firewalld.service
  zone="$(firewall_zone)"
  for service in http ssh; do
    firewall-cmd --quiet --zone="$zone" --permanent --query-service="$service" || {
      firewall-cmd --quiet --zone="$zone" --permanent --add-service="$service"
      changed=1
    }
  done
  ((changed == 0)) || firewall-cmd --quiet --reload
}

companion_status() {
  local nic='not configured' wol='not configured' sshd_state
  [[ ! -r /etc/default/bc250-wol ]] || nic="$(sed -n 's/^BC250_NIC=//p' /etc/default/bc250-wol | tail -1)"
  if [[ "$nic" != 'not configured' && -n "$nic" && -x /usr/sbin/ethtool ]]; then
    wol="$(/usr/sbin/ethtool "$nic" 2>/dev/null | sed -n 's/^[[:space:]]*Wake-on:[[:space:]]*//p' | tail -1)"
    [[ -n "$wol" ]] || wol=unknown
  fi
  sshd_state="$(systemctl is-active sshd.service 2>/dev/null || true)"
  echo "BC-250 Pi maintenance companion"
  printf '  office endpoint:       HTTP :80 (%s)\n' "$(firewall_state http)"
  printf '  maintenance SSH:       TCP :22 (%s)\n' "$(firewall_state ssh)"
  printf '  sshd:                  %s\n' "${sshd_state:-inactive}"
  printf '  power-control account: %s\n' "$(id "$POWER_USER" >/dev/null 2>&1 && echo ready || echo absent)"
  printf '  WOL interface:         %s\n' "${nic:-not configured}"
  printf '  Wake-on:               %s\n' "$wol"
  echo "  internal Open WebUI/Ollama ports are not opened for the Pi."
}

companion_enable() {
  local sudoers=/etc/sudoers.d/bc250-power-control
  require_root
  ensure_ssh_path
  ensure_account "$POWER_USER" "$POWER_USER" "$POWER_HOME"
  printf '%s\n' "$POWER_USER ALL=(root) NOPASSWD: /usr/bin/bc250-maintenance request-shutdown" > "$sudoers"
  chmod 0440 "$sudoers"
  command -v visudo >/dev/null 2>&1 && visudo -cf "$sudoers" >/dev/null
  cat <<EOF_ENABLE
Pi maintenance access prepared.

Add the Pi power-control public key to:
  $POWER_HOME/.ssh/authorized_keys

Use exactly:
  restrict,command="/usr/bin/sudo /usr/bin/bc250-maintenance request-shutdown" ssh-ed25519 AAAA... pi-power-control

Network policy:
  HTTP 80 = office UI/readiness
  SSH 22  = restricted maintenance access
  WOL     = Ethernet magic packet; no host firewall port is opened
EOF_ENABLE
  companion_status
}

backup_status() {
  local auth="$EXPORT_HOME/.ssh/authorized_keys"
  echo "BC-250 optional backup export"
  printf '  rrsync:                %s\n' "$([[ -x /usr/bin/rrsync ]] && echo /usr/bin/rrsync || echo 'missing (install rsync-rrsync)')"
  printf '  export account:        %s\n' "$(id "$EXPORT_USER" >/dev/null 2>&1 && echo ready || echo absent)"
  printf '  config directory:      %s\n' "$([[ -d "$BACKUP_ROOT/config" ]] && echo present || echo absent)"
  printf '  users directory:       %s\n' "$([[ -d "$BACKUP_ROOT/users" ]] && echo present || echo absent)"
  if [[ -r "$auth" ]]; then
    printf '  config key scope:      %s\n' "$(grep -Fq '/config"' "$auth" && echo configured || echo absent)"
    printf '  users key scope:       %s\n' "$(grep -Fq '/users"' "$auth" && echo configured || echo absent)"
  else
    echo '  config key scope:      absent'
    echo '  users key scope:       absent'
  fi
  echo "  rollback backups:      not exported"
}

backup_enable() {
  require_root
  [[ -x /usr/bin/rrsync ]] || {
    echo "ERROR: /usr/bin/rrsync is missing. Install explicitly with:" >&2
    echo "  sudo dnf install rsync-rrsync" >&2
    return 1
  }
  ensure_ssh_path
  ensure_account "$EXPORT_USER" "$EXPORT_GROUP" "$EXPORT_HOME"
  install -d -m0710 -o root -g "$EXPORT_GROUP" "$BACKUP_ROOT"
  install -d -m0750 -o root -g "$EXPORT_GROUP" "$BACKUP_ROOT/config" "$BACKUP_ROOT/users"
  find "$BACKUP_ROOT/config" "$BACKUP_ROOT/users" -maxdepth 1 -type f \
    \( -name 'owui-config-*.tar.gz' -o -name 'owui-config-*.tar.gz.sha256' \
       -o -name 'owui-users-*.sql.gz' -o -name 'owui-users-*.sql.gz.sha256' \) \
    -exec chgrp "$EXPORT_GROUP" {} + -exec chmod 0640 {} +
  cat <<EOF_EXPORT
Read-only backup export prepared. Private keys stay on the Pi.

Append the appropriate public key line(s) to:
  $EXPORT_HOME/.ssh/authorized_keys

Config scope:
  restrict,command="/usr/bin/rrsync -ro $BACKUP_ROOT/config" ssh-ed25519 AAAA... pi-config-backup

Users scope:
  restrict,command="/usr/bin/rrsync -ro $BACKUP_ROOT/users" ssh-ed25519 AAAA... pi-users-backup

No additional firewall port is needed; export uses the same restricted SSH :22 path.
EOF_EXPORT
  backup_status
}

case "${1:-status}" in
  companion-status) companion_status ;;
  companion-enable) companion_enable ;;
  backup-status) backup_status ;;
  backup-enable) backup_enable ;;
  *) echo "ERROR: unknown maintenance companion action: ${1:-}" >&2; exit 2 ;;
esac

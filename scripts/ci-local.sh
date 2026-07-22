#!/usr/bin/env bash
set -Eeuo pipefail

repo_path=/workspace/bc250-llm-server

podman run --rm --pull=always \
  --volume "$PWD:$repo_path:Z" \
  --workdir "$repo_path" \
  fedora:44 \
  bash -Eeuxo pipefail -c '
    dnf install -y \
      bash cargo curl findutils gcc git gzip make \
      libdrm-devel patch python3 rpm-build rust \
      systemd systemd-rpm-macros tar xz

    make rpm
  '

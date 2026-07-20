#!/usr/bin/env bash
set -Eeuo pipefail

repo_path=/__w/amd-bc-250-llm/amd-bc-250-llm

podman run --rm --pull=always \
  --volume "$PWD:$repo_path:Z" \
  --workdir "$repo_path" \
  fedora:44 \
  bash -Eeuxo pipefail -c '
    dnf install -y \
      bash cargo curl findutils gcc git gzip jq make \
      libdrm-devel patch python3 rpm-build rpmdevtools rpmlint rust \
      systemd systemd-rpm-macros tar xz

    make validate
    make sources
    make rpm

    rpmlint dist/*.rpm 2>&1 | tee dist/RPMLINT.txt
    rpm -qpl dist/*.x86_64.rpm | tee dist/RPM-CONTENTS.txt
  '

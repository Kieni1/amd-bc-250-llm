#!/usr/bin/env bash
set -Eeuo pipefail

repo_path=/workspace/bc250-llm-server
build_image="${BC250_BUILD_IMAGE:-fedora:44}"
pull_policy="${BC250_BUILD_PULL_POLICY:-missing}"

podman run --rm --pull="$pull_policy" \
  --volume "$PWD:$repo_path:Z" \
  --workdir "$repo_path" \
  "$build_image" \
  bash -Eeuxo pipefail -c '
    build_packages=(
      bash cargo curl findutils gcc git gzip make
      libdrm-devel patch python3 rpm-build rust
      systemd systemd-rpm-macros tar xz
    )
    if ! rpm -q "${build_packages[@]}" >/dev/null 2>&1; then
      dnf install -y "${build_packages[@]}"
    fi

    make rpm
  '

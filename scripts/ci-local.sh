#!/usr/bin/env bash
set -Eeuo pipefail

repo_path=/workspace/bc250-llm-server
build_image="${BC250_BUILD_IMAGE:-fedora:44}"
pull_policy="${BC250_BUILD_PULL_POLICY:-missing}"
host_uid="$(id -u)"
host_gid="$(id -g)"

if [[ "$host_uid" -eq 0 ]]; then
  echo "ERROR: scripts/ci-local.sh must be invoked by a non-root workspace owner." >&2
  exit 2
fi

podman run --rm --pull="$pull_policy" \
  --env BC250_HOST_UID="$host_uid" \
  --env BC250_HOST_GID="$host_gid" \
  --volume "$PWD:$repo_path:Z" \
  --workdir "$repo_path" \
  "$build_image" \
  bash -Eeuxo pipefail -c '
    build_packages=(
      bash cargo coreutils cpio curl diffutils findutils gawk gcc git-core grep gzip make sed
      libdrm-devel patch python3 rpm-build rpmlint ruff rust ShellCheck shadow-utils
      systemd systemd-rpm-macros tar util-linux xz
    )
    if ! rpm -q "${build_packages[@]}" >/dev/null 2>&1; then
      dnf --disable-repo=fedora-cisco-openh264 --setopt=install_weak_deps=False install -y "${build_packages[@]}"
    fi

    groupadd --force --gid "$BC250_HOST_GID" bc250-builder
    useradd --no-create-home --uid "$BC250_HOST_UID" --gid "$BC250_HOST_GID" \
      --home-dir /tmp/bc250-builder --shell /bin/bash bc250-builder
    mkdir -p /tmp/bc250-builder
    chown "$BC250_HOST_UID:$BC250_HOST_GID" /tmp/bc250-builder

    runuser -u bc250-builder -- env \
      HOME=/tmp/bc250-builder LANG=C LC_ALL=C BC250_REQUIRE_GIT_SOURCE=0 \
      BC250_BUILD_IMAGE_REF="$build_image" BC250_RELEASE_AUTHORITY=false \
      bash -Eeuxo pipefail -c "cd '$repo_path' && make release-gate"
  '

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
      bash binutils bison bzip2 cargo cargo-rpm-macros cpio curl elfutils-libelf-devel
      expat-devel findutils flex gcc gcc-c++ git-core glslang glslang-devel gzip kernel-devel kernel-srpm-macros kmod libdrm-devel
      libzstd-devel make meson ninja-build openssl-devel patch pkgconf-pkg-config python3
      python3-mako python3-packaging python3-pycparser python3-pyyaml redhat-rpm-config rpm-build rpmlint ruff
      rust shadow-utils ShellCheck spirv-tools-devel systemd systemd-devel systemd-rpm-macros
      tar util-linux vulkan-headers vulkan-loader-devel xz zlib-devel zstd
    )
    if ! rpm -q "${build_packages[@]}" >/dev/null 2>&1; then
      dnf --disable-repo=fedora-cisco-openh264 install -y "${build_packages[@]}"
    fi

    groupadd --force --gid "$BC250_HOST_GID" bc250-builder
    useradd --no-create-home --uid "$BC250_HOST_UID" --gid "$BC250_HOST_GID" \
      --home-dir /tmp/bc250-builder --shell /bin/bash bc250-builder
    mkdir -p /tmp/bc250-builder
    chown "$BC250_HOST_UID:$BC250_HOST_GID" /tmp/bc250-builder

    runuser -u bc250-builder -- env \
      HOME=/tmp/bc250-builder LANG=C LC_ALL=C \
      bash -Eeuxo pipefail -c "cd '$repo_path' && make release-gate"
  '

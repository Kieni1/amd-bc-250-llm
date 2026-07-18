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
      libdrm-devel python3 rpm-build rpmdevtools rpmlint rust \
      systemd systemd-rpm-macros tar xz

    make validate
    make sources
    make rpm

    rpmlint dist/*.rpm 2>&1 | tee dist/RPMLINT.txt
    rpm -qpl dist/*.x86_64.rpm | tee dist/RPM-CONTENTS.txt
  '

### execute locally
#cd ~/Repos/amd-bc-250-llm
#
#printf '0.4.0\n' > VERSION
#
#sed -i \
#  -e 's/^Version:.*/Version:        0.4.0/' \
#  -e 's/^Release:.*/Release:        0.1.testing%{?dist}/' \
#  packaging/bc250-llm-server.spec
#
#sed -i '/^%changelog$/a\
#* Fri Jul 1x 2026 Kieni111 <xxx> - 0.x.0-0.1.testing\
#- Prepare the 0.x.0 testing release\
#- Refresh model handling and BC-250 runtime defaults\
#- Correct RPM packaging and validation issues\
#' packaging/bc250-llm-server.spec
#
#./scripts/ci-local.sh
#
#git add -A
#git diff --cached --check
#git commit -m "Release 0.4.0"
#git tag -a 0.4.0 -m "bc250-llm-server 0.4.0"
#
#git push origin HEAD
#git push origin 0.4.0
#
#gh auth status || gh auth login
#
#gh release create 0.4.0 \
#  dist/*.rpm \
#  dist/SHA256SUMS \
#  dist/RPMLINT.txt \
#  dist/RPM-CONTENTS.txt \
#  --verify-tag \
#  --title "bc250-llm-server 0.4.0" \
#  --generate-notes \
#  --prerelease

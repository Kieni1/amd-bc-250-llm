%global governor_version 0.4.11
%global governor_commit 60ab6e5b354f01f287c73d920990dcd618a674cc
%global unlock_commit 6c3969ddee40e894297869e6ca30537f274619cb
%global live_manager_commit 8eb45f07810af738f3e4945ea0cc29d399e378a6
%global source_date_epoch_from_changelog 1
%global project_libexec %{_libexecdir}/bc250-llm-server
%global project_share %{_datadir}/bc250-llm-server
%global project_config %{_sysconfdir}/bc250-llm-server
%global payload_filelist %{_builddir}/%{name}-%{version}.files
%global bc250_units cyan-skillfish-governor-smu.service owui-backup-config.timer owui-backup-users.timer owui-prune.timer owui-warmup.timer bc250-night-shutdown.timer bc250-enable-wol.service

Name:           bc250-llm-server
Version:        0.8.1
Release:        0.1.testing%{?dist}
Summary:        Testing local LLM server integration for AMD BC-250 hardware
License:        GPL-2.0-only AND MIT
URL:            https://github.com/Kieni1/amd-bc-250-llm
Source0:        %{name}-%{version}.tar.gz
# filippor/cyan-skillfish-governor, SMU branch, pinned release v0.4.11
Source1:        cyan-skillfish-governor-%{governor_commit}.tar.gz
Source2:        cyan-skillfish-governor-vendor-%{governor_commit}.tar.xz
# fduraibi/bc250-40cu-unlock, pinned Fedora helper revision
Source3:        bc250-40cu-unlock-%{unlock_commit}.tar.gz
# WinnieLV/bc250-cu-live-manager, pinned revision; upstream has no license file
Source4:        bc250-cu-live-manager-%{live_manager_commit}.tar.gz

ExclusiveArch:  x86_64

BuildRequires:  cargo
BuildRequires:  findutils
BuildRequires:  gcc
BuildRequires:  gzip
BuildRequires:  patch
BuildRequires:  pkgconfig(libdrm)
BuildRequires:  python3
BuildRequires:  rust
BuildRequires:  systemd-rpm-macros
BuildRequires:  xz

Requires:       bash
Requires:       btrfs-progs
Requires:       coreutils
Requires:       curl
Requires:       dbus
Requires:       dracut
Requires:       ethtool
Requires:       findutils
Requires:       firewalld
Requires:       gawk
Requires:       gcc
Requires:       git
Requires:       grubby
Requires:       gzip
Requires:       hostname
Requires:       iproute
Requires:       jq
Requires:       kmod
Requires:       lm_sensors
Requires:       make
Requires:       mesa-vulkan-drivers
Requires:       nginx
Requires:       pciutils
Requires:       podman
Requires:       policycoreutils
Requires:       procps-ng
Requires:       python3
Requires:       python3-huggingface-hub
Requires:       sqlite
Requires:       systemd
Requires:       tar
Requires:       util-linux
Requires:       umr
Requires:       vulkan-loader
Requires:       vulkan-tools
Requires:       xz
Requires:       zstd
Requires:       zram-generator
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd

%description
A testing-oriented Fedora integration package for using an AMD BC-250 as a
small local LLM server. It installs the reviewed Cyan Skillfish SMU governor,
Ollama Vulkan defaults, Open WebUI and Tika Quadlets, an HTTP reverse proxy,
model and experiment templates, maintenance tools, benchmarks and isolated
task and coding-agent helpers. The live CU manager and experimental 40-CU source
helper are installed, but the RPM never changes CU routing automatically.
Ollama remains an external operator-installed prerequisite. Model weights,
Open WebUI settings, HTTPS and CU changes remain operator-controlled.

%prep
%setup -q
mkdir governor-src
tar -xzf %{SOURCE1} -C governor-src --strip-components=1
tar -xJf %{SOURCE2} -C governor-src
mkdir unlock-src
tar -xzf %{SOURCE3} -C unlock-src --strip-components=1
mkdir live-manager-src
tar -xzf %{SOURCE4} -C live-manager-src --strip-components=1
patch -d live-manager-src -p1 < patches/cu-live-manager-rpm-paths.patch

%build
pushd governor-src
export CYAN_SKILLFISH_GOVERNOR_VERSION=%{governor_version}
cargo build --release --frozen
popd

%check
bash scripts/validate.sh

%install
python3 scripts/install-manifest.py \
  --manifest packaging/install-manifest.tsv \
  --source-root "$PWD" \
  --buildroot "%{buildroot}" \
  --filelist "%{payload_filelist}" \
  --define "bindir=%{_bindir}" \
  --define "libexec=%{project_libexec}" \
  --define "share=%{project_share}" \
  --define "config=%{project_config}" \
  --define "sysconfdir=%{_sysconfdir}" \
  --define "datadir=%{_datadir}" \
  --define "docdir=%{_docdir}/%{name}" \
  --define "unitdir=%{_unitdir}" \
  --define "tmpfilesdir=%{_tmpfilesdir}" \
  --define "sysusersdir=%{_sysusersdir}" \
  --define "presetdir=%{_presetdir}" \
  --define "modulesloaddir=%{_modulesloaddir}" \
  --define "modprobedir=%{_modprobedir}" \
  --define "dbusdir=%{_datadir}/dbus-1/system.d" \
  --define "unlock_commit=%{unlock_commit}" \
  --define "live_manager_commit=%{live_manager_commit}"

%post
%systemd_post %{bc250_units}
%tmpfiles_create bc250-llm-server.conf
systemctl daemon-reload >/dev/null 2>&1 || :

# This testing package deliberately starts its basic stack immediately.
systemctl enable --now firewalld.service >/dev/null 2>&1 || :
if systemctl is-active --quiet firewalld.service; then
  firewall-cmd --quiet --permanent --add-service=http >/dev/null 2>&1 || :
  firewall-cmd --quiet --reload >/dev/null 2>&1 || :
fi
systemctl enable --now cyan-skillfish-governor-smu.service nginx.service \
  >/dev/null 2>&1 || :
if command -v ollama >/dev/null 2>&1 && \
   systemctl cat ollama.service >/dev/null 2>&1; then
  systemctl enable --now ollama.service >/dev/null 2>&1 || :
else
  echo "Ollama is not installed. Run: sudo bc250-install-ollama"
fi
if [ "$1" -gt 1 ]; then
  systemctl try-restart tika.service open-webui.service >/dev/null 2>&1 || :
else
  systemctl start tika.service open-webui.service >/dev/null 2>&1 || :
fi
if command -v setsebool >/dev/null 2>&1; then
  setsebool -P httpd_can_network_connect 1 >/dev/null 2>&1 || :
fi
cat <<'EOF_POST'
BC-250 LLM server installed (testing profile).
Open http://SERVER_IP/ on a trusted LAN and register the first admin immediately.
HTTP is unencrypted. Read /usr/share/doc/bc250-llm-server/HTTPS.md before wider use.
No chat model is downloaded until production-models.toml enables an entry.
Optional helpers: bc250-install-ollama, bc250-ollama-profile,
bc250-memory-profile, bc250-swap-profile, bc250-setup-task-model and
bc250-setup-coding-agent. Run llm-run-diagnose for a performance capture.
EOF_POST

%preun
if [ "$1" -eq 0 ]; then
  systemctl stop open-webui.service tika.service >/dev/null 2>&1 || :
  systemctl disable --now %{bc250_units} >/dev/null 2>&1 || :
fi
%systemd_preun %{bc250_units}

%postun
%systemd_postun_with_restart %{bc250_units}
systemctl daemon-reload >/dev/null 2>&1 || :
if systemctl cat ollama.service >/dev/null 2>&1; then
  systemctl try-restart ollama.service >/dev/null 2>&1 || :
fi
systemctl reload nginx.service >/dev/null 2>&1 || :
if [ "$1" -eq 0 ]; then
  cat <<'EOF_POSTUN'
BC-250 LLM server package removed. Persistent data was not deleted.
Review /etc/bc250-llm-server, /etc/cyan-skillfish-governor-smu,
/var/lib/bc250-llm-server, /var/cache/bc250-llm-server,
/var/lib/open-webui, /var/backups/bc250-llm-server,
operator-added HTTPS/CU/task-model/coding-agent files, memory/swap and
Ollama profile overrides, firewalld/SELinux changes and .rpmsave files. Ollama installed separately is not removed.
EOF_POSTUN
fi

%files -f %{payload_filelist}
%license licenses/LICENSE governor-src/LICENSE licenses/40CU-LICENSE-NOTICE
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/gguf
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/production
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/experiments
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/mtp
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/task
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/agent
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/production
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/experiments
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/task
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/agent
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/ollama
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/main
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/task
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/agent
%ghost %dir %attr(0750,root,root) /var/lib/bc250-llm-server/swap
%ghost %dir %attr(0750,root,ollama) /var/cache/bc250-llm-server
%ghost %dir %attr(0750,ollama,ollama) /var/cache/bc250-llm-server/huggingface
%ghost %dir %attr(0750,ollama,ollama) /var/lib/ollama
%ghost %dir %attr(0750,root,root) /var/lib/open-webui
%ghost %dir %attr(0750,root,root) /var/backups/bc250-llm-server
%ghost %dir %attr(0750,root,root) /var/backups/bc250-llm-server/config
%ghost %dir %attr(0750,root,root) /var/backups/bc250-llm-server/users
%ghost %dir %attr(0750,root,root) /var/backups/bc250-llm-server/rollback
%ghost %dir %attr(0750,root,root) /var/backups/bc250-llm-server/rollback/config
%ghost %dir %attr(0750,root,root) /var/backups/bc250-llm-server/rollback/users

%changelog
* Wed Jul 22 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.8.1-0.1.testing
- Add an explicit full-purge command for package, state, Ollama and host profiles
- Restore verified stock AMDGPU backups and remove persistent 40-CU configuration
- Record packages added by the guided installer for bounded dependency cleanup
- Restore the pre-install firewalld and SELinux network policy on purge
- Keep ordered Hugging Face progress output in captured installer transcripts
- Prepare the running kernel's 40-CU module automatically without enabling it
- Cache kernel source, skip repeat builds and verify the initramfs module copy
- Distinguish installed, initramfs and actually loaded AMDGPU state
- Avoid false module-verification failures and redundant preparation on enable
- Add a models-only guided-installer resume path after interrupted host setup

* Wed Jul 22 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.8.0-0.1.testing
- Simplify pinned source caching and remove per-source digest/member bookkeeping
- Consolidate model management into one focused command with focused tests
- Provide the ollama account via sysusers and exclude Fedora's Ollama package
- Keep Fedora and official Ollama mutually exclusive and fix latest-release installation
- Reuse matching model state until --refresh and make cleanup explicit and non-mutating
- Preserve current catalogs, strict Modelfile metadata and all three Ollama instances

* Wed Jul 22 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.7.1-0.1.testing
- Improve model management stability with validated Hugging Face token handling
- Add --refresh for explicit re-download, rehash and Ollama re-registration
- Add low-disk cleanup for enabled production and experiment Ollama models
- Document cleanup, token and refresh workflows and validate the new contracts

* Mon Jul 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.7.0-0.1.testing
- Adopt cmd, config and examples source groups and FHS application-state paths
- Correct guided task and coding setup, selectable production installs and reboot detection
- Make GGUF revision changes replace stale files instead of relabeling cached content
- Install or update Ollama explicitly and require zram-generator for the swap workflow
- Keep live-manager persistence on the RPM-owned executable and probe llama.cpp MTP flags
- Expand deterministic validation for release, commands, paths, patches and installer contracts

* Mon Jul 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.6.4-0.1.testing
- Keep all current models, features, dependencies and pinned external tools
- Consolidate command routing and RPM build-tree preparation
- Group verification and Open WebUI guidance with their feature documentation
- Flatten full-name Modelfiles and prefix production display names
- Cache verified GGUF state and unchanged Ollama registration
- Add the resumable filesystem-to-verification installer and accurate CU totals

* Mon Jul 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.6.3-0.1.testing
- Group experiment, MTP and embedding helpers under the models feature tree
- Separate download-only MTP inputs from the Ollama experiment catalog
- Package the MTP catalog as an operator-editable noreplace configuration
- Keep repository scans out of RPM-prepared third-party source trees
- Reduce pre-1.0 validation to the deterministic checks needed to build RPMs

* Mon Jul 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.6.2-0.1.testing
- Keep catalogs and long-form Modelfile names aligned with the current model set
- Move task and coding-agent assets under models and isolate ports 11435/11436
- Remove obsolete model entries and templates while retaining MTP downloads

* Sun Jul 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.6.1-0.1.testing
- Remove pre-production legacy catalog migration code and upgrade hooks
- Retain strict Modelfile provenance checks and OLLAMA_URL compatibility

* Sun Jul 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.6.0-0.1.testing
- Consolidate model management, packaging metadata and compatibility commands
- Preserve model selections during migration from legacy shell catalogs

* Sat Jul 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.5.1-0.1.testing
- Add the command-first installation and operations guide
* Sat Jul 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.5.0-0.1.testing
- Prepare the 0.5.0 testing release
* Sat Jul 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.4.4-0.1.testing
- Publish the cleaned public repository

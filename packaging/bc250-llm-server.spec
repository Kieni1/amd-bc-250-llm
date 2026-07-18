%global governor_version 0.4.11
%global governor_commit 60ab6e5b354f01f287c73d920990dcd618a674cc
%global unlock_commit 6c3969ddee40e894297869e6ca30537f274619cb
%global live_manager_commit 8eb45f07810af738f3e4945ea0cc29d399e378a6
%global source_date_epoch_from_changelog 1
%global project_libexec %{_libexecdir}/bc250-llm-server
%global project_share %{_datadir}/bc250-llm-server
%global project_config %{_sysconfdir}/bc250-llm-server
%global bc250_units cyan-skillfish-governor-smu.service owui-backup-config.timer owui-backup-users.timer owui-prune.timer owui-warmup.timer bc250-night-shutdown.timer bc250-enable-wol.service

Name:           bc250-llm-server
Version:        0.4.4
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
Recommends:     zram-generator
Requires(pre):    shadow-utils
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd

%description
A testing-oriented Fedora integration package for using an AMD BC-250 as a
small local LLM server. It installs the reviewed Cyan Skillfish SMU governor,
Ollama Vulkan defaults, Open WebUI and Tika Quadlets, an HTTP reverse proxy,
model and experiment templates, maintenance tools, benchmarks and optional
local coding-agent helpers. The live CU manager and experimental 40-CU source
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
patch -d unlock-src -p1 < patches/40cu-fedora-helper.patch
mkdir live-manager-src
tar -xzf %{SOURCE4} -C live-manager-src --strip-components=1

%pre
getent group ollama >/dev/null || groupadd -r ollama
id ollama >/dev/null 2>&1 || \
  useradd -r -g ollama -d /var/lib/ollama \
    -s /usr/sbin/nologin -M ollama
exit 0

%build
pushd governor-src
export CYAN_SKILLFISH_GOVERNOR_VERSION=%{governor_version}
cargo build --release --frozen
popd

%check
bash scripts/validate.sh

%install
# Governor: pinned filippor binary plus locally reviewed support files.
install -Dpm0755 governor-src/target/release/cyan-skillfish-governor-smu \
  %{buildroot}%{_bindir}/cyan-skillfish-governor-smu
install -Dpm0755 governor-src/scripts/cyan-skillfish-performance-mode \
  %{buildroot}%{_bindir}/cyan-skillfish-performance-mode
install -Dpm0644 governor/cyan-skillfish-governor-smu.service \
  %{buildroot}%{_unitdir}/cyan-skillfish-governor-smu.service
install -Dpm0644 governor/config.toml \
  %{buildroot}%{_sysconfdir}/cyan-skillfish-governor-smu/config.toml
install -Dpm0644 governor/com.cyanskillfish.Governor.conf \
  %{buildroot}%{_datadir}/dbus-1/system.d/com.cyanskillfish.Governor.conf

# Persistent directory declarations and service defaults.
install -Dpm0644 packaging/bc250-llm-server.tmpfiles \
  %{buildroot}%{_tmpfilesdir}/bc250-llm-server.conf
install -Dpm0644 packaging/90-bc250-llm-server.preset \
  %{buildroot}%{_presetdir}/90-bc250-llm-server.preset
install -Dpm0644 system/99-sensors.conf \
  %{buildroot}%{_modulesloaddir}/99-bc250-sensors.conf
install -Dpm0644 system/options-sensors.conf \
  %{buildroot}%{_modprobedir}/99-bc250-sensors.conf
install -Dpm0644 system/ollama.service.d-override.conf \
  %{buildroot}%{_unitdir}/ollama.service.d/50-bc250-llm-server.conf
install -Dpm0644 system/ollama-profiles/balanced.conf \
  %{buildroot}%{_unitdir}/ollama.service.d/60-bc250-runtime-profile.conf

# Rootful Quadlets use Podman's vendor directory.
install -d %{buildroot}%{_datadir}/containers/systemd
install -pm0644 containers/llm.network containers/tika.container \
  containers/open-webui.container %{buildroot}%{_datadir}/containers/systemd/

# HTTP-only testing front door, inserted into Fedora nginx's default server.
install -Dpm0644 nginx/bc250-llm-server.conf \
  %{buildroot}%{_sysconfdir}/nginx/default.d/bc250-llm-server.conf
install -Dpm0644 nginx/websocket-map.conf \
  %{buildroot}%{_sysconfdir}/nginx/conf.d/00-bc250-websocket-map.conf

# Editable package configuration. No model is enabled by default.
install -d -m0755 %{buildroot}%{project_config}
install -pm0644 models/model-sources.sh \
  %{buildroot}%{project_config}/model-sources.sh
install -pm0644 experiments/experiment-sources.sh \
  %{buildroot}%{project_config}/experiment-sources.sh
install -Dpm0644 maintenance/owui-maintenance.env \
  %{buildroot}%{project_share}/examples/maintenance.env.example

# Main-package implementation scripts.
install -d %{buildroot}%{project_libexec}
install -pm0755 models/fetch-models.sh \
  %{buildroot}%{project_libexec}/fetch-models.sh
install -pm0755 models/pull-embedding-model.sh \
  %{buildroot}%{project_libexec}/pull-embedding-model.sh
install -pm0755 experiments/fetch-experiments.sh \
  %{buildroot}%{project_libexec}/fetch-experiments.sh
install -pm0755 experiments/compare-experiments.sh \
  %{buildroot}%{project_libexec}/compare-experiments.sh
install -pm0755 experiments/run-mtp-llamacpp.sh \
  %{buildroot}%{project_libexec}/run-mtp-llamacpp.sh
install -pm0755 benchmark/compare-models.sh \
  %{buildroot}%{project_libexec}/compare-models.sh
install -pm0755 benchmark/log_sensors.sh \
  %{buildroot}%{project_libexec}/log_sensors.sh
install -pm0755 monitoring/check-temp.sh \
  %{buildroot}%{project_libexec}/check-temp.sh
install -Dpm0755 monitoring/llm-run-diagnose.sh \
  %{buildroot}%{_bindir}/llm-run-diagnose
install -pm0755 system/install-cu-manager.sh \
  %{buildroot}%{project_libexec}/install-cu-manager.sh
install -pm0755 system/install-ollama.sh \
  %{buildroot}%{project_libexec}/install-ollama.sh
install -pm0755 system/ollama-profile.sh \
  %{buildroot}%{project_libexec}/ollama-profile.sh
install -pm0755 system/memory-profile.sh \
  %{buildroot}%{project_libexec}/memory-profile.sh
install -pm0755 system/swap-profile.sh \
  %{buildroot}%{project_libexec}/swap-profile.sh
install -pm0755 system/cu-status.sh \
  %{buildroot}%{project_libexec}/cu-status.sh
install -pm0755 verify.sh %{buildroot}%{project_libexec}/verify.sh
install -pm0755 verify-lan.sh %{buildroot}%{project_libexec}/verify-lan.sh
install -pm0755 raspi-wol/enable-wol.sh \
  %{buildroot}%{project_libexec}/enable-wol.sh
for script in backup-config.sh backup-users.sh restore-config.sh restore-users.sh \
  prune-uploads.sh warmup.sh safe-suspend.sh; do
  install -pm0755 maintenance/$script %{buildroot}%{project_libexec}/$script
done

install -d %{buildroot}%{project_libexec}/coding-agent
install -pm0755 coding-agent/coding-agent.sh \
  coding-agent/commit-agent.sh coding-agent/gitea-review.sh \
  %{buildroot}%{project_libexec}/coding-agent/

# Stable user-facing commands, including the operator-triggered 40-CU helper.
install -d %{buildroot}%{_bindir}
install -pm0755 packaging/wrappers/* %{buildroot}%{_bindir}/

# Pinned live CU manager. It is installed but never invoked by an RPM scriptlet.
install -pm0755 live-manager-src/bc250-cu-live-manager.sh \
  %{buildroot}%{_bindir}/bc250-cu-live-manager
install -d %{buildroot}%{project_share}/cu-live-manager
install -pm0644 live-manager-src/README.md \
  %{buildroot}%{project_share}/cu-live-manager/README-upstream.md
printf '%s\n' '%{live_manager_commit}' > \
  %{buildroot}%{project_share}/cu-live-manager/SOURCE-REVISION

# Optional 40-CU payload. No module or modprobe changes occur here.
install -d %{buildroot}%{project_libexec}/40cu %{buildroot}%{project_share}/40cu
install -pm0755 unlock-src/scripts/bc250-enable-40cu-fedora.sh \
  %{buildroot}%{project_libexec}/40cu/bc250-enable-40cu-fedora.sh
install -pm0644 unlock-src/patch/bc250-40cu-amdgpu.patch \
  %{buildroot}%{project_share}/40cu/bc250-40cu-amdgpu.patch
install -pm0644 unlock-src/README.md \
  %{buildroot}%{project_share}/40cu/README-upstream.md
printf '%s\n' '%{unlock_commit}' > \
  %{buildroot}%{project_share}/40cu/SOURCE-REVISION

# Reviewed Ollama runtime profiles. The balanced profile is the packaged default.
install -d %{buildroot}%{project_share}/ollama-profiles
install -pm0644 system/ollama-profiles/*.conf \
  %{buildroot}%{project_share}/ollama-profiles/

# Services and optional timers. Maintenance and suspend timers remain disabled.
install -d %{buildroot}%{_unitdir}
install -pm0644 maintenance/*.service maintenance/*.timer \
  %{buildroot}%{_unitdir}/
install -pm0644 raspi-wol/bc250-enable-wol.service \
  raspi-wol/bc250-night-shutdown.service \
  raspi-wol/bc250-night-shutdown.timer %{buildroot}%{_unitdir}/

# Model and experiment examples.
install -d %{buildroot}%{project_share}/models \
  %{buildroot}%{project_share}/experiments
install -pm0644 models/*.Modelfile %{buildroot}%{project_share}/models/
install -pm0644 models/model-sources.sh \
  %{buildroot}%{project_share}/models/model-sources.example.sh
install -pm0644 experiments/*.Modelfile %{buildroot}%{project_share}/experiments/
install -pm0644 experiments/experiment-sources.sh \
  %{buildroot}%{project_share}/experiments/experiment-sources.example.sh
install -pm0644 experiments/mtp-sources.example.sh \
  %{buildroot}%{project_share}/experiments/

# Optional operator-side examples.
install -d %{buildroot}%{project_share}/examples/task-model \
  %{buildroot}%{project_share}/examples/coding-agent \
  %{buildroot}%{project_share}/examples/raspi-wol
install -pm0644 task-model/README.md task-model/Modelfile \
  %{buildroot}%{project_share}/examples/task-model/
install -pm0755 task-model/setup-gemma-1b-task.sh \
  %{buildroot}%{project_share}/examples/task-model/
install -pm0644 coding-agent/README.md coding-agent/Modelfile \
  coding-agent/gitea.env.example \
  %{buildroot}%{project_share}/examples/coding-agent/
install -pm0755 coding-agent/setup-coding-agent.sh \
  %{buildroot}%{project_share}/examples/coding-agent/
install -pm0644 raspi-wol/bc250-wake.service raspi-wol/bc250-wake.timer \
  raspi-wol/bc250-wake.env.example raspi-wol/bc250-wol.env.example \
  %{buildroot}%{project_share}/examples/raspi-wol/
install -pm0755 raspi-wol/wake-bc250.sh \
  %{buildroot}%{project_share}/examples/raspi-wol/

# Documentation.
install -d %{buildroot}%{_docdir}/%{name}
install -pm0644 README.md licenses/THIRD_PARTY_NOTICES.md \
  openwebui-settings.md %{buildroot}%{_docdir}/%{name}/
install -pm0644 docs/*.md %{buildroot}%{_docdir}/%{name}/
install -pm0644 packaging/README.md \
  %{buildroot}%{_docdir}/%{name}/PACKAGING.md
install -pm0644 benchmark/README.md \
  %{buildroot}%{_docdir}/%{name}/BENCHMARK.md
install -pm0644 experiments/README.md \
  %{buildroot}%{_docdir}/%{name}/EXPERIMENTS.md
install -pm0644 coding-agent/README.md \
  %{buildroot}%{_docdir}/%{name}/CODING-AGENT.md
install -pm0644 nginx/https-example.conf \
  %{buildroot}%{_docdir}/%{name}/
install -pm0644 system/GOVERNOR.md system/kernel-cmdline.md \
  %{buildroot}%{_docdir}/%{name}/

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
No chat model is downloaded until you edit /etc/bc250-llm-server/model-sources.sh.
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
/var/llm, /var/lib/open-webui, /var/backups/bc250-llm-server,
operator-added HTTPS/CU/task-model/coding-agent files, memory/swap and
Ollama profile overrides, firewalld/SELinux changes and .rpmsave files. Ollama installed separately is not removed.
EOF_POSTUN
fi

%files
%license licenses/LICENSE governor-src/LICENSE licenses/40CU-LICENSE-NOTICE
%{_bindir}/cyan-skillfish-governor-smu
%{_bindir}/cyan-skillfish-performance-mode
%{_bindir}/bc250-benchmark
%{_bindir}/bc250-check-temp
%{_bindir}/bc250-code
%{_bindir}/bc250-code-commit
%{_bindir}/bc250-compare-experiments
%{_bindir}/bc250-40cu
%{_bindir}/bc250-cu-live-manager
%{_bindir}/bc250-fetch-experiments
%{_bindir}/bc250-fetch-models
%{_bindir}/bc250-gitea-review
%{_bindir}/bc250-install-cu-manager
%{_bindir}/bc250-install-ollama
%{_bindir}/bc250-memory-profile
%{_bindir}/bc250-ollama-profile
%{_bindir}/bc250-pull-embedding-model
%{_bindir}/bc250-run-mtp
%{_bindir}/bc250-setup-coding-agent
%{_bindir}/bc250-setup-task-model
%{_bindir}/bc250-swap-profile
%{_bindir}/bc250-cu-status
%{_bindir}/bc250-uninstall-info
%{_bindir}/bc250-verify
%{_bindir}/bc250-verify-lan
%{_bindir}/llm-run-diagnose
%dir %{project_libexec}
%{project_libexec}/fetch-models.sh
%{project_libexec}/pull-embedding-model.sh
%{project_libexec}/fetch-experiments.sh
%{project_libexec}/compare-experiments.sh
%{project_libexec}/run-mtp-llamacpp.sh
%{project_libexec}/compare-models.sh
%{project_libexec}/log_sensors.sh
%{project_libexec}/check-temp.sh
%{project_libexec}/install-cu-manager.sh
%{project_libexec}/install-ollama.sh
%{project_libexec}/ollama-profile.sh
%{project_libexec}/memory-profile.sh
%{project_libexec}/swap-profile.sh
%{project_libexec}/cu-status.sh
%{project_libexec}/verify.sh
%{project_libexec}/verify-lan.sh
%{project_libexec}/enable-wol.sh
%{project_libexec}/backup-config.sh
%{project_libexec}/backup-users.sh
%{project_libexec}/restore-config.sh
%{project_libexec}/restore-users.sh
%{project_libexec}/prune-uploads.sh
%{project_libexec}/warmup.sh
%{project_libexec}/safe-suspend.sh
%{project_libexec}/coding-agent/
%{project_libexec}/40cu/
%dir %{project_share}
%{project_share}/40cu/
%{project_share}/cu-live-manager/
%{project_share}/models/
%{project_share}/experiments/
%{project_share}/examples/
%{project_share}/ollama-profiles/
%{_datadir}/containers/systemd/llm.network
%{_datadir}/containers/systemd/tika.container
%{_datadir}/containers/systemd/open-webui.container
%{_unitdir}/cyan-skillfish-governor-smu.service
%dir %{_unitdir}/ollama.service.d
%{_unitdir}/ollama.service.d/50-bc250-llm-server.conf
%{_unitdir}/ollama.service.d/60-bc250-runtime-profile.conf
%{_unitdir}/owui-*.service
%{_unitdir}/owui-*.timer
%{_unitdir}/bc250-enable-wol.service
%{_unitdir}/bc250-night-shutdown.service
%{_unitdir}/bc250-night-shutdown.timer
%{_tmpfilesdir}/bc250-llm-server.conf
%{_presetdir}/90-bc250-llm-server.preset
%{_modulesloaddir}/99-bc250-sensors.conf
%{_modprobedir}/99-bc250-sensors.conf
%dir %{_sysconfdir}/cyan-skillfish-governor-smu
%config(noreplace) %{_sysconfdir}/cyan-skillfish-governor-smu/config.toml
%dir %attr(0755,root,root) %{project_config}
%config(noreplace) %{project_config}/model-sources.sh
%config(noreplace) %{project_config}/experiment-sources.sh
%ghost %config(noreplace) %attr(0600,root,root) %{project_config}/maintenance.env
%config(noreplace) %{_sysconfdir}/nginx/default.d/bc250-llm-server.conf
%config(noreplace) %{_sysconfdir}/nginx/conf.d/00-bc250-websocket-map.conf
%{_docdir}/%{name}/
%{_datadir}/dbus-1/system.d/com.cyanskillfish.Governor.conf

%changelog
* Sat Jul 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.4.4-0.1.testing
- Publish the cleaned public repository

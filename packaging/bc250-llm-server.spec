%global governor_version 0.4.12
%global governor_commit be9537fc36f24b17570088cafa8c79365f80fee8
%global unlock_commit 6c3969ddee40e894297869e6ca30537f274619cb
%global live_manager_commit a929085d791f126ce76a60eb609610820fb08066
%global source_date_epoch_from_changelog 1
%global project_libexec %{_libexecdir}/bc250-llm-server
%global project_share %{_datadir}/bc250-llm-server
%global project_config %{_sysconfdir}/bc250-llm-server
%global payload_filelist %{_builddir}/%{name}-%{version}.files
%global bc250_units ollama.service ollama-task.service ollama-embedding.service ollama-agent.service cyan-skillfish-governor-smu.service owui-backup-config.timer owui-backup-users.timer owui-prune.timer owui-warmup.timer bc250-night-shutdown.timer bc250-enable-wol.service

Name:           bc250-llm-server
Version:        0.12.1
Release:        0.5%{?dist}
Summary:        Local LLM server integration for AMD BC-250 hardware
License:        GPL-2.0-only AND MIT
URL:            https://github.com/Kieni1/amd-bc-250-llm
Source0:        %{name}-%{version}.tar.gz
# filippor/cyan-skillfish-governor, SMU branch, pinned release v0.4.12
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
Requires:       poppler-utils
Requires:       policycoreutils
Requires:       procps-ng
Requires:       python3
Requires:       python3-huggingface-hub
Requires:       sqlite
Requires:       systemd
Requires:       tar
Requires:       util-linux
Requires:       util-linux-script
Requires:       umr
Requires:       vulkan-loader
Requires:       vulkan-tools
Requires:       xfsprogs
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
model and experiment templates, maintenance tools, benchmarks and separated
production, task, embedding and exclusive coding-agent Ollama workflows. Open
WebUI can be initialized through its supported admin APIs without storing the
operator credential. The live CU manager and experimental 40-CU source helper
are installed, but the RPM never changes CU routing automatically. The Ollama binary remains an upstream payload installed by the guided helper; the RPM owns the complete four-lane systemd topology. Model weights, users,
operator-created Open WebUI state, HTTPS and CU changes remain operator-controlled.

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
secret_env=/var/lib/bc250-llm-server/secrets/open-webui.env
if [ ! -s "$secret_env" ]; then
  umask 077
  python3 -c 'import secrets; print("WEBUI_SECRET_KEY=" + secrets.token_hex(32))' > "$secret_env"
fi
chmod 0600 "$secret_env"
systemctl daemon-reload >/dev/null 2>&1 || :
echo "BC-250 package installed. Run: sudo bc250-install"

%preun
if [ "$1" -eq 0 ]; then
  systemctl stop open-webui.service tika.service \
    ollama.service ollama-task.service ollama-embedding.service ollama-agent.service \
    >/dev/null 2>&1 || :
  systemctl disable --now %{bc250_units} >/dev/null 2>&1 || :
  rm -f /etc/containers/systemd/open-webui.container.d/90-enable.conf
  rmdir /etc/containers/systemd/open-webui.container.d >/dev/null 2>&1 || :
  systemctl daemon-reload >/dev/null 2>&1 || :
fi
%systemd_preun %{bc250_units}

%postun
%systemd_postun_with_restart %{bc250_units}
systemctl daemon-reload >/dev/null 2>&1 || :
systemctl reload nginx.service >/dev/null 2>&1 || :
if [ "$1" -eq 0 ]; then
  cat <<'EOF_POSTUN'
BC-250 LLM server package removed. Persistent data was not deleted.
Review /etc/bc250-llm-server, /etc/cyan-skillfish-governor-smu,
/var/lib/bc250-llm-server, /var/cache/bc250-llm-server,
/var/lib/open-webui, /var/backups/bc250-llm-server,
operator-added HTTPS/CU/task/embedding/coding-agent files, memory/swap and
Ollama profile overrides, firewalld/SELinux changes and .rpmsave files. Ollama installed separately is not removed.
EOF_POSTUN
fi

%files -f %{payload_filelist}
%license licenses/LICENSE governor-src/LICENSE licenses/40CU-LICENSE-NOTICE
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server
%ghost %dir %attr(0700,root,root) /var/lib/bc250-llm-server/revalidation
%ghost %dir %attr(0700,root,root) /var/lib/bc250-llm-server/revalidation/results
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/gguf
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/production
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/experiments
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/mtp
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/task
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/agent
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/gguf/embedding
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/production
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/experiments
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/task
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/agent
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/modelfiles/embedding
%ghost %dir %attr(0750,root,ollama) /var/lib/bc250-llm-server/ollama
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/main
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/task
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/embedding
%ghost %dir %attr(0750,ollama,ollama) /var/lib/bc250-llm-server/ollama/agent
%ghost %dir %attr(0750,root,root) /var/lib/bc250-llm-server/swap
%ghost %dir %attr(0750,root,ollama) /var/cache/bc250-llm-server
%ghost %dir %attr(0750,ollama,ollama) /var/cache/bc250-llm-server/huggingface
%ghost %dir %attr(0750,ollama,ollama) /var/lib/ollama
%ghost %dir %attr(0750,root,root) /var/lib/open-webui
%ghost %dir %attr(0710,root,bc250-backup-export) /var/backups/bc250-llm-server
%ghost %dir %attr(0750,root,bc250-backup-export) /var/backups/bc250-llm-server/config
%ghost %dir %attr(0750,root,bc250-backup-export) /var/backups/bc250-llm-server/users
%ghost %dir %attr(0700,root,root) /var/backups/bc250-llm-server/rollback
%ghost %dir %attr(0700,root,root) /var/backups/bc250-llm-server/rollback/config
%ghost %dir %attr(0700,root,root) /var/backups/bc250-llm-server/rollback/users

%changelog
* Wed Sep 23 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.12.1-0.5
- Fix local RAG preparation to use Ollama chat output with separated native thinking, fail closed on truncated/empty/fenced/reasoning-contaminated final content, and score source fidelity only against validated final Markdown.
- Preserve unique source identifiers during normalization, reject reasoning markers during working/active validation, and distinguish expected OCR/oversize deferrals from real preparation errors with clearer review/status UX.
- Fix bc250-revalidate status --raw argument forwarding and advance the harness to v4.4 without changing its qualified phases/bundle semantics.
- Make healthy live 40-CU routing primary in installer/dashboard wording, clarify the optional persistent boot module, and make the initial kernel plan explicitly defer repository update evaluation to step 2.
- Strengthen the GPT-OSS Deep system prompt to prefer fewer accurate facts over plausible list-filling without changing sampling, context, residency or model runtime policy.

* Wed Sep 23 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.12.1-0.4
- Promote device-qualified Ollama 0.34.2 with exact release-payload URL/SHA verification while preserving package-owned service topology.
- Add the local bc250-rag DE/FR/bilingual preparation, human-review, activation and ingestion lifecycle while retaining the legacy rag-import compatibility route.
- Remove obsolete historical kernel-version warnings, qualify IOMMU as outside the supported baseline rather than hardware-broken, and improve live TTM conflict diagnostics.
- Normalize Markdown-escaped deterministic RAG markers and keep established Open WebUI/model/40-CU runtime policy otherwise unchanged.

* Mon Sep 21 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.12.1-0.3
- Improve converged installer UX by hiding the long optional-model catalogue until an operator explicitly chooses to review additional models.
- Add a small redacted bc250-support-bundle command that reuses existing appliance authorities and emits manifest/checksum evidence without collecting user content or credentials.
- Advance package revalidation to harness v4.3 with manifest/checksum bundle integrity, explicit expected inactive-agent raw evidence, clearer policy-aware diagnostics, and diagnostic counts in completion/status summaries.
- Make bc250-status distinguish Open WebUI unit activity from HTTP readiness and query the active Ollama server version through its API; clarify successful verifier output when optional authenticated checks are skipped.

* Mon Sep 21 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.12.1-0.2
- Fix bc250-revalidate package-version gating so it reads the package-owned installed VERSION authority instead of hard-coding the obsolete 0.11.3 target.
- Install VERSION under the package share and fail closed if the revalidation target version is missing or malformed.
- Keep the 0.12.1 Open WebUI behavior unchanged; this release bump is limited to revalidation compatibility and its focused regression coverage.
- Keep Git-only development memory outside release validation, move pre-v1 patch notes under development/patchnotes, and remove duplicate documentation/version checks already owned by existing validation gates.

* Mon Sep 21 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.12.1-0.1
- Grant authenticated users read access to the six production Open WebUI roles and their six hidden implementation/task records while preserving unrelated grants.
- Unload the Deep Reasoning GPT-OSS model after each response so title/tag task-model cold loads retain safe memory headroom on the 16 GiB UMA appliance.
- Verify curated presets and hidden base-model overrides through their correct Open WebUI v0.11.3 API views, with narrow API-shape guarding and accurate diagnostics.
- Correct the CU live-manager third-party revision notice and validate the carried RPM patch against the exact pinned source before RPM preparation.
- Fold the durable Open WebUI regressions into the established test suite, including exact production IDs, active/hidden state, additive ACL semantics, Deep keep-alive drift and credential-output hygiene.

* Sun Sep 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-2.4
- Patch the pinned CU live manager CPU-core-unlock reboot prompt to use `/usr/sbin/reboot` instead of the BC-250 device-proven unreliable `systemctl reboot` invocation; keep its existing interactive/no-reboot-under-`--yes` contract unchanged.
- Record exact installed 0.11.3-2.3 targeted operations acceptance: clean RPM verification, topology/status/verifier UX, identity restore with the existing FK baseline, Tika restart semantics, supported reboot reconstruction and healthy live 40/40 all passed.
- Extend package-owned Open WebUI convergence through existing supported APIs: Arena off, local/offline application policy persisted, upload limits/extensions owned, and production/task implementation models active but hidden behind curated office roles.
- Make authenticated Open WebUI status detect drift in those persisted settings and hidden-model metadata while preserving unrelated operator-owned state and order-insensitive extension semantics.
- Document pinned Open WebUI v0.11.3 OpenAI-style adapter limitations rather than carrying an appliance-specific container fork; package-owned hard generation caps use nested `options.num_predict`, and exclusive-agent output clarifies that normal OWUI roles may remain listed but unavailable.
- Close 2.4 as a source-validated release; exact installed RPM/device acceptance remains a separate gate.

* Sun Sep 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-2.3
- Improve operations UX without changing appliance architecture: actionable operator-overlay recovery guidance, separate local-maintenance and Pi/companion installer decisions, topology-aware status summary, clearer agent transitions and an idempotent `bc250-agent-mode normal` convergence alias.
- Keep safe-power behavior unchanged while identifying protected local SSH/service ports in defer messages without exposing peer addresses.
- Make verifier degradation output root-cause-aware by marking lane-dependent checks unavailable/skipped; expose skipped authenticated Open WebUI checks explicitly without counting them as pass/fail.
- Make degraded status directly actionable with the normal convergence command, include skipped checks in verifier headline totals, and keep agent-mode transition guidance aligned with that public recovery path.
- Align runtime swap-directory creation with the packaged/tmpfiles 0750 root:root contract so normal convergence does not intentionally create RPM mode drift.
- Clarify maintenance timer history and DRY_RUN pruning output while preserving current-invocation journaling, backup privacy, and non-destructive defaults.
- Make selective identity restore compare baseline/new FK sets while keeping integrity_check strict, and report concise integrity/FK/rollback outcomes to the operator.
- Treat Tika exit status 143 as successful only for the expected SIGTERM/container-stop path so routine restarts do not leave misleading failed-unit telemetry.
- Replace package-controlled persistent 40-CU `systemctl reboot` calls with the BC-250 compatibility invocation `/usr/sbin/reboot`, preserving the existing automatic-reboot contract while avoiding the invocation path shown unreliable on target hardware.
- Source validation closes this release; RPM/SRPM build and exact installed 2.3 device acceptance remain separate external gates.

* Sun Sep 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-2.2
- Encode the completed MTP package selection in the existing catalog: Qwen3.5 9B 16K/draft-2 as primary fast, YMQ Qwen3.8 27B 8K/draft-1 as primary general 27B, and HauhauCS Qwen3.8 27B 8K/draft-2 as the specialist alternative.
- Retire Qwen3.6 27B from active MTP discovery while preserving its positive historical definition/evidence in the source-only graveyard; keep the 35B-A3B stock-envelope failure retired.
- Add only thin MTP role/recommendation metadata to the existing catalog and surface it in list output; keep every MTP entry disabled/download-only and outside installer/Open WebUI/Ollama convergence.
- Remove ambiguous 27B convenience aliases instead of silently retargeting them after the preferred 27B changed; exact 27B IDs remain the evidence/operator contract.
- Record the corrected final RAG conclusion: Gemma E4B remains the document/RAG default at 94/96 corrected overall versus Qwen 9B at 93/96, with no production-role change or reopened model tournament.
- Speed repeated local package regeneration without weakening validation: preserve the normal source cache, default local Podman builds to pull=missing, and allow a complete prebuilt Fedora builder image to skip repeated dependency installation.

* Sun Sep 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-2.1
- Carry the 1.8 support/power safety fixes forward unchanged while moving the current source release to 2.1; no service-topology, production-model, power-policy, governor, CU, hard-memory-floor or MTP-default change.
- Finish the RAG qualification integration: expose language measurability separately from language acceptance, document numeric/unit fixture composition, and clarify chronological session memory telemetry without adding another benchmark framework.
- Record the final Qwen3.8 27B IQ3_XXS 16K RAG follow-up: five early cited answers were correct, but MemAvailable fell to about 0.28 GiB before safety abort; keep the same verified model identity at the safer 8K experimental default.
- Keep Gemma E4B / bc250-office-documents as the 16 GiB production RAG default; Qwen 9B remains the separate higher-quality office role and no broad RAG model tournament is reopened.
- Fix secondary model-manager documentation drift: the operator template now teaches canonical category experiments, and the durable CLI contract no longer carries a stale per-release target header.
- Apply the existing private Open WebUI credential-file boundary to benchmark --token-file inputs instead of accepting permissive files.
- Deliberately do not add a first-class long-residency benchmark, a second telemetry/watchdog stack, global 512 MiB failure semantics or a new unit-policy schema because the current shared helpers and deterministic fixture primitives already cover the maintained product needs.

* Sun Sep 20 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.8
- Fix safe-power established-connection parsing so active local SSH/UI/Ollama endpoints actually defer shutdown; request power actions non-blocking so the decision unit can complete cleanly.
- Keep Pi shutdown fail-safe by exempting only its authenticated forced-command SSH connection while every other protected connection still defers poweroff.
- Fix healthy live 40-CU status/verify returning rc=1 when persistent boot activation is intentionally disabled.
- Harden operator model discovery and CLI guidance: reject visible non-.Modelfile overlay files, clarify combined-category versus all-selection syntax, and correct the legacy install --all hint.
- Make installer MTP inventory use standalone source vocabulary without a duplicate heading; improve protected-state, agent-mode, maintenance-policy and prune-size operator UX.
- Bound the existing ISTA Qwen3.8 IQ3_XXS experiment to 8K context after sustained 16K low-memory evidence; reuse the same verified GGUF/model identity rather than creating a duplicate 8K entry.
- Record exact installed 1.7 support/maintenance findings and keep remaining destructive/power qualification blocked until this safety release is installed.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.7
- Correct operator topology reporting by deriving normal/degraded/stopped/agent from the existing agent-mode classifier instead of treating agent inactivity as proof of normal mode.
- Enforce private non-empty regular-file permissions for explicit RAG/Open WebUI and Hugging Face token-file inputs.
- Fail closed on outer Markdown fences in raw/structured bc250-code output contracts, while keeping review/document Markdown-capable.
- Make installer completion distinguish core verification from Open WebUI applied/skipped/retry-required state; keep Open WebUI setup failures nonfatal.
- Keep safe-power conservative on protected TCP activity while making the message truthful, and remove the upload-pruner dependency on an assumed 50-item Open WebUI page size.
- Allow repository bootstrap help without root and simplify current-facing documentation.
- Show standalone MTP state read-only in installer Stage 7; drain Ollama residency before MTP launch, restore it after direct operator runs, and keep comparison/qualification explicitly drain-only.
- Correct the repeated task tags-en OCR-synonym evaluator gap without changing the model/prompt/threshold, and record exact installed 1.6 full revalidation including successful Jina restoration.
- No production model, MTP draft default, service topology, hard resource threshold or power-policy default changes.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.6
- Close the current MTP qualification lane in package/development state without changing runtime defaults: record YMQ Phase-1 qualification, corrected draft-depth sweep conclusions, measured noise floor, and optional confirmation-only follow-up.
- Keep qwen3.5 draft depth 3 as the packaged default pending confirmation-grade depth-2 evidence; retain depth 2 for qwen3.6-27b, HauhauCS qwen3.8 and YMQ qwen3.8.
- Move the active hardware focus to support/maintenance qualification; no service topology, resource threshold, production-role or MTP runtime behavior changes.
- Preserve the reviewed MTP execution methodology and reference-kit validation transcript as source-only development material; the benchmark kit remains outside the runtime RPM payload.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.5
- Fix embedding-only RAG residency restoration by using a non-empty /api/embed probe while preserving each lane's normal keep-alive policy
- Make all-current installer model reconciliation concise and remove redundant processed-count output
- Clarify the installer setup-plan reboot status label
- Record exact installed 1.4 installer success and the fail-closed revalidation restoration defect without relabelling partial evidence as qualification

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.4
- Record final BC-250 RAG finalist evidence and keep Gemma E4B / bc250-office-documents as the production document/RAG default for the 16 GiB profile; Qwen 9B remains a separate heavier general-office option.
- Restore benchmark residency sets with each Ollama lane's normal keep-alive policy instead of forcing 30m, and rename the resident-session swap metric to the precise swap_peak_delta_mib.
- Reconcile current source-validation, main-lane wording and RAG evidence documentation without changing runtime topology, model bytes, hard resource policy or MTP behavior.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.3
- Restore the starting Ollama model residency set after direct RAG qualification and fail closed when set restoration cannot be verified.
- Expose RAG resident-session MemAvailable start/min/end/delta plus swap start/peak/end/peak delta in canonical summaries.
- Carry forward the 1.2 Ruff/executable-mode fix and all 1.1/WIP installer, RAG, Open WebUI and MTP changes unchanged.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.2
- Fix model-manager installer output helper closure binding so Ruff B023 passes without suppressions or behavior changes.
- Preserve models/modelctl.py as an executable source file; the RPM install manifest continues to install the model controller as mode 0755.
- Carry forward the 1.1 RAG/Open WebUI/MTP and unpublished 0.5 installer/maintenance refinements unchanged.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-1.1
- Carry forward the unpublished 0.5 installer/diagnostic refinements and strengthen direct RAG qualification without changing runtime topology or model defaults.
- Make RAG acceptance boundary-aware for dates/numbers/IDs/currency, add explicit semantic-alternative and numeric-value fixture contracts, and report language-neutral answers without false language failures.
- Separate RAG retrieval/fact/language/citation/abstention checks and add exact expected-case completeness reporting so partial result streams cannot appear complete.
- Resolve Open WebUI RAG benchmarks through the live active preset/base-model mapping before creating temporary Knowledge state, and use bounded HTTP readiness rather than service state alone.
- Harden MTP comparison cleanup so process-group signals require verified SID/PGID ownership; fall back to signaling only the launched child when ownership cannot be proven.

* Sat Sep 19 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-0.5
- Gate optional maintenance/Pi setup behind one default-No installer question, separate local maintenance from Pi integration, and verify selected maintenance/SSH/export state after setup.
- Group post-install guidance into concise validation, models/runtime-lanes and further-setup blocks; surface installed documentation and key configuration/state/evidence paths on the appliance.
- Keep revalidation thresholds unchanged while surfacing tight (<512 MiB) MemAvailable headroom and accepted output-budget exhaustion as non-failing Diagnostics.
- This 0.5 source line is still in progress; packaging/archive and external qualification remain pending.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-0.4
- Harden the experimental MTP lane before first BC-250 qualification: exact-ID candidates, protected-state verification, safe llama-server privilege drop, launch resource/port/stale-process preflight, and same-model no-MTP versus MTP comparison evidence.
- Expand the disabled MTP catalog to Qwen3.5 9B, Qwen3.6 27B control, Qwen3.8 27B HauhauCS IQ2_M and Qwen3.6 35B-A3B while keeping MTP outside generic convergence and production roles.
- Refine installer model reconciliation without changing Release: honor catalog suppression, summarize fully current required models, shorten current/deferred picker rows, skip the inactive agent registration probe, bound other registration probes, and make combined apply/refresh exclude MTP unconditionally.
- Keep MTP qualification fail-closed on completion integrity, kernel-journal capture, draft-acceptance evidence and severe GPU/kernel faults; move the reviewed external llama.cpp starting baseline to b10964/v0.4.1 for the Qwen3.8-capable funnel; no production model or runtime topology changes.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-0.3
- Restore state-rich installer model selection through compact shared model-state inspection while keeping bc250-model list catalog-only.
- Tighten the package-owned Open WebUI tag-generation prompt so broad and specific tags share one array and exactly one raw JSON object is emitted.
- Improve model status auditability with explicit online-check guidance plus source repository/revision/SHA output, and make bounded context-truncation diagnostics concise while preserving qualification policy.
- Record the installed 0.11.3-0.2.fc44 v4.2 revalidation as historical device evidence for this new source release; production roles/topology and benchmark thresholds remain unchanged.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-0.2
- Fix the public bc250-fetch-mtp dispatcher for the 0.11.3 lifecycle grammar and make it an explicit opt-in path for disabled MTP experiments without changing generic convergence policy.
- Keep MTP display indexes globally stable between category and combined views, and enforce one-model revision/checksum overrides before combined selections are split by category.
- Make the MTP preparation/run workflow operationally coherent and document the remaining real-device llama.cpp qualification boundary; no MTP model is promoted or enabled by default.
- Reconcile secondary lifecycle surfaces: use unprivileged catalog discovery in the installed-assets check and align current handover/model guidance with the 0.2 MTP route.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.3-0.1
- Redesign bc250-model around explicit catalog/status/apply/refresh/unregister/remove lifecycle operations and a shared read-only model-state inspector.
- Improve model-manager guidance for incomplete and legacy command forms while preserving strict source provenance, checksum and registration safety.
- Migrate active package callers and current-facing documentation to the new lifecycle vocabulary; historical release/campaign evidence retains the commands it actually used.
- Advance package revalidation to v4.2 for the 0.11.3 target, surface bounded context-truncation diagnostics, avoid duplicate GPT-OSS edge performance work, and use lightweight successful intermediate checkpoints while retaining full high-value snapshots.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.2-0.6
- Make task/revalidation quality diagnostics non-cascading and case-addressable while preserving the same qualification thresholds and return-code semantics.
- Harden the local coding helper around Ollama chat completion integrity: separate thinking from final content, refuse nonterminal/truncated/reasoning-contaminated output, and keep file replacement atomic.
- Add compact Qwen3.5 4B and Gemma 4 E4B agentic challengers without changing the Ornith default or promoting/retiring candidates.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.2-0.5
- Fix installed Open WebUI translation qualification so packaged fixtures resolve from /usr/share/bc250-llm-server instead of the nonexistent /usr/examples tree.
- Centralize benchmark package-resource resolution across category and Open WebUI checks, preserving explicit overrides while preventing source tests from silently consuming stale installed fixtures.
- Carry forward hermetic jq coverage for installer tests and the Ruff import-order cleanup; production model/runtime policy remains unchanged.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.2-0.4
- Ensure every model behind an active package-owned Open WebUI role is installed before application setup, and verify active role base registrations explicitly.
- Advance revalidation to harness v4.1 with an explicit 2048-token direct translation contract, authenticated production-role translation coverage and clearer mixed-quality summaries.
- Accept the observed French task title adjective in the semantic fixture, add verbose Open WebUI desired-state reporting, and record the installed 0.11.2-0.3 appliance evidence without changing production model/runtime policy.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.2-0.3
- Keep the maintainer-approved Translate-Gemma production switch and reconcile development/docs so the source policy no longer describes LFM as the current production translator.
- Make historical quality scripts source-only after carrying forward their still-useful lifecycle lessons into the supported task/translation screens.
- Make Open WebUI translation evidence final-RC recording authoritative if archive creation changes the final result.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.2-0.2
- Normalize task/translation catalogs: keep LFM2.5 1.2B as the sole active task model, promote Translate-Gemma as the production DE↔FR base, retain former LFM translation as an experiment, and retire superseded task/translation identities safely.
- Restore embedding-lane coverage in task survival/recovery and authoritative translation evidence exit-status handling.
- Refresh operator documentation, desired Open WebUI roles, validation/development memory and model lifecycle records; retire duplicated dated specialist handovers.

* Fri Sep 18 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.2-0.1
- Start the 0.11.2 line with the Stage-2E translation integration retained from the unpublished 0.11.1-0.11 candidate.
- Resolve Ruff findings in the translation benchmark, package-owned Open WebUI direction filter and its focused regression tests without changing the tested Stage-2E prompt/wrapper contract.
- Advance the package qualification target from 0.11.1 to 0.11.2; historical 0.11.1 campaign evidence remains unchanged.

* Thu Sep 17 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.11
- Integrate the Stage-2E selected Translate-Gemma configuration as explicit DE-to-FR and FR-to-DE candidate Open WebUI roles using the exact tested v1 system/user contract, 2048 output budget and no forced thinking policy while retaining LFM as the production/default translation role.
- Package one reviewed non-global Open WebUI direction Filter, reconcile it through supported Function APIs, verify its source/state and package model-preset fields through desired-state status, and preserve unrelated operator Functions.
- Correct one-decimal locale numeric parsing in translation evaluation and record the bounded final integration gate plus known protected-format/completeness caveats without reopening broad model discovery.
- Harden task-model qualification around cheap screening, warm-main survival and post-failure recovery; record current active-model task measurements while retaining LFM2.5 1.2B Q6_K as the production task model.
- Record the current German/French translation campaign, add explicit translation thinking-policy control and richer runtime provenance, and keep the saturated canonical short screen as a gate rather than promoting any challenger before harder-corpus/product-path qualification.
- Keep role-specific campaign evidence in MODELS.md and Git-only development records rather than runtime Modelfiles; print evidence archive SHA-256 without creating checksum sidecar files, and keep experiment archive/privacy handling separate from package source-integrity checks.
- Make the post-OOM task recovery probe actively reload the warm main by default, fail only on new recovery-time OOM/GPU faults, and avoid direct-translation privacy false positives from the harness's own HOME-prefixed result paths.

* Mon Sep 14 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.10
- Make the quick MTP comparison fail closed on backend completion-integrity failures, require a non-empty usable content/reasoning completion, and align reserved-token corruption detection with the repeated-run semantics used by the main generation benchmark.
- Keep missing draft-acceptance counters distinct from corrupt inference: report them as insufficient MTP qualification evidence without failing otherwise valid completion.
- Replace MTP source-string assertions with a focused fake-backend behavior regression covering valid completion, missing terminal state, repeated reserved-token corruption, empty completion, reasoning-only output and acceptance-rate reporting.

* Mon Sep 14 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.9
- Strengthen main-model generation evidence with backend-aware completion integrity, effective Ollama runtime/KV metadata, optional 4K/16K context targets, optional minimum-duration thermal runs, CU-state capture and best-effort GPU-kernel journal checks.
- Improve the external llama.cpp/MTP evidence path by printing exact runtime/build/flags, keeping gfx1013 UBATCH=384 strictly opt-in, and reporting draft accepted/proposed counts plus acceptance rate instead of treating throughput alone as success.
- Record the evidence-first main-model qualification funnel without changing production GPT-OSS, Ollama 0.34.0, KV defaults, governor/CU policy or any promoted model.

* Sun Sep 13 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.8
- Revalidate retained Open WebUI pruning API keys before they can be kept during interactive maintenance setup; invalid stored values now require a replacement instead of surviving setup.
- Let optional read-only backup export independently install/verify openssh-server through the same bounded installer helper used by Pi maintenance, so selecting export cannot fail merely because the earlier Pi SSH branch was skipped.
- Refresh current-source validation/development guidance for 0.8 without changing model, firewall, retention or power-policy defaults.

* Sun Sep 13 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.7
- Fix the installed maintenance-contract path after the documentation hierarchy change.
- Improve interactive local-maintenance and Pi-companion wording, including an explicit power-action menu and detected WOL interface/address display.
- Re-prompt invalid maintenance answers locally instead of aborting the entire setup; explain IP-address versus Linux-interface-name mistakes.

* Sun Sep 13 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.6
- Replace the backup-export directory permission source-string regression with hermetic behavior coverage for the installed reserved-group 0750 path and the source/direct-execution 0700 fallback.
- Keep documentation validation focused on durable package contracts: public command names, runnable-command privilege examples, revalidation lifecycle, retired-Qwen distinction, source/installed links, and canonical active-model equality; drop brittle prose-content assertions.
- Record review/release discipline in Git-only development memory: after implementing a review, report changes, deliberate deferrals, validation actually run, and residual risk; prefer observable behavior tests over implementation-string assertions.

* Sun Sep 13 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.5
- Fix backup producers so config/users export directories retain the package-owned 0750 root:bc250-backup-export contract instead of being reset to private 0700 on each backup run.
- Reconcile current-facing installer, model, Open WebUI and command documentation; make revalidation lifecycle and privilege examples explicit without changing runtime/model defaults.
- Preserve source-relative documentation layout in the installed RPM and validate installed Markdown links, while consolidating duplicate maintainer/layout documents and keeping development bookkeeping out of the binary payload.
- Add Git-only development decision/model-run records so negative experiment results and retest conditions survive future documentation cleanup.

* Sat Sep 12 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.4
- Define a versioned BC-250/Pi maintenance contract with HTTP :80 office readiness, Wake-on-LAN, and a stable safe-shutdown request that preserves the appliance idle/session policy.
- Add optional restricted Pi maintenance access over SSH :22 plus read-only rrsync backup export, keeping internal Open WebUI/Ollama ports closed and private keys off the BC-250.
- Publish new config/users backups with export-group read rights only after the export account is explicitly enabled, while keeping rollback data private and reserving stable backup-directory group ownership across boots.
- Offer maintenance/WOL, Pi companion access and optional backup export after core verification during full interactive installation; non-interactive and models-only runs leave maintenance policy unchanged.

* Sat Sep 12 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.3
- Make targeted model cleanup concise and show exact interactive cleanup effects, including keep-GGUF retention, without changing cleanup semantics.
- Limit manual maintenance output to the current systemd invocation and preflight upload-prune credentials before launching the unit, without exposing the key.
- Refresh README/operator command documentation, including privileged examples and root-owned token-file invocations, and remove small duplicate/noisy output paths.

* Sat Sep 12 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.2
- Update the package runtime baseline to Ollama 0.34.0 and keep the existing BC-250 Vulkan/UMA topology, cloud-off policy, and real-device requalification requirement.
- Add four large main-lane challengers plus a packaged sequential GPT-OSS comparison matrix; retain source GGUFs by default and document lower-quant fallbacks for BC-250 memory pressure.
- Fix schema-3 model-state reconciliation so ordinary drift checks preserve dedupe bookkeeping, explain registration drift, improve inactive-agent/quiet model-manager UX, and retain the prior support-ops retirement/storage safeguards.
- Batch all conservative 16 MiB XFS dedupe ranges for each source/blob pair into one xfs_io process, exclude unreferenced Ollama import blobs from dedupe targets, report those transient blobs separately, and retain source GGUFs for no-redownload recovery.
- Include the translation/catalog lint corrections and package the standalone main-model quality-check directory.

* Sat Sep 12 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.1-0.1
- Promote LFM2.5 1.2B Q6_K to the default dedicated Open WebUI task role after direct, live-OWUI, and true-concurrency BC-250 qualification; retain Gemma 3 1B as an optional fallback.
- Own the title/tag/retrieval-query prompt templates in desired state and reuse that exact policy in the direct task benchmark so production and benchmark prompt contracts cannot silently diverge.
- Move completed/exhausted task candidates to the source-only graveyard with evidence notes, synchronize default wiring/quality assets/docs/tests, and preserve evaluator thresholds plus warm-main/task-unload policy.

* Sat Sep 12 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.15
- Repair authenticated translation candidate testing through Open WebUI provider allow-lists while keeping complete provider credentials out of evidence, preserving HTTP failures, and verifying exact/effective restoration.
- Accept the demonstrated valid French formal-office wording "confirmer avoir reçu" without weakening language, identifier, date, amount, or source-leakage requirements; add deterministic provider-transaction/redaction coverage and translation run provenance/manifests.
- Add explicit package-retired model metadata plus safe `bc250-model cleanup-retired`, canonical model identity in storage output, schema-3 state identity, and recorded-success dedupe skipping while retaining the measured 16 MiB XFS dedupe strategy.
- Make protected storage accounting fail visibly instead of returning false zeroes, improve source-prune/dedupe previews, and keep production model defaults, residency policy, harness-4.0 semantics, and quality thresholds unchanged.

* Fri Sep 11 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.14
- Harden standalone translation screening: use the 1024-token specialist contract, candidate-specific prompt profiles, numeric-value preservation, quality rc=3 propagation, Open WebUI telemetry, selected-field preset-delta verification, and exact restoration/credential checks.
- Make task candidate screening deployment-faithful by benchmarking baseline and challenger on task Ollama 11435, recording the effective request contract, preserving rc=3, refusing unknown pre-existing task registrations, and cleaning temporary registrations on exit.
- Harden support operations by preserving uploads with uncertain metadata from automatic pruning, verifying exclusive agent/normal service topology, and making model cleanup honor explicit host/destination overrides.
- Retire exhausted Granite 8B, Ling 3.0 Tiny, and Defiant-Fable Qwen3.5 comparisons to the source-only graveyard, synchronize active-catalog documentation, and keep all production model/runtime defaults unchanged.

* Thu Sep 10 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.13
- Add checksum-pinned experimental compact task candidates for LFM2.5 1.2B, MiniCPM5 2B, Qwen3 1.7B, and Qwen3.8 2B without changing the packaged Gemma 3 1B task default.
- Add experimental Hunyuan-MT 7B Q4_K_M and Translate-Gemma 4 Sub E4B Q4_K_XL translation candidates; retain LFM2.5 8B-A1B as the production translation model pending real-device comparison.
- Package the recent task/translation quality evidence scripts plus separate reusable task, direct-translation, Open WebUI integration, and installed-asset checks outside harness-4.0.
- Keep package-build validation minimal: syntax/discovery/install-manifest coverage only; candidate quality and hardware behavior remain opt-in real-BC-250 checks.

* Wed Sep 09 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.12
- Keep the proven 20-minute main-model residency and 15-minute optional warm-up so interactive chat remains warm instead of paying a large-model cold-load penalty on every turn.
- Retain the compact Gemma 3 1B Open WebUI task default after hardware/UX review; Qwen3.8 4B Distill remains opt-in because concurrent residency with GPT-OSS caused a real task-service OOM and safe serialization would make subsequent chat cold-start again.
- Promote Ornith 1.5 9B to the exclusive coding/agent role with temperature 0 and 3072-token Bash/Python agent budgets.
- Make German/French translation direction explicit by default and strengthen complete-source-word translation while preserving document invariants.
- Preserve the harness/evaluator architecture and previously corrected translation, task-language, RAG, agent and dashboard evaluators without adding package-build test cases.

* Tue Sep 08 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.11
- Accept semantically equivalent public-cloud prohibition wording and avoid redundant question-ID requirements in direct RAG while preserving retrieval and citation gates.
- Correct DE-to-FR translation fixtures for invariant names/references, locale-safe currency ordering, and formal prohibition wording without weakening semantic checks.
- Require language compliance for the German tag task fixture and add multilingual task-language regressions.
- Use final-state dashboard wording and clear stale TTY rows after completed revalidation runs without changing failed-run diagnostics or harness semantics.
- Report unavailable model registration probes explicitly instead of the ambiguous setup-unknown catalog label.

* Mon Sep 07 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.10
- Fix harness-v4 run_step execution for declared internal Bash functions by exporting the harness function set into a bounded child Bash while retaining the special sanitized benchmark path.
- Close the real Phase-3 rc=127 failure for production-sanity, GPT-OSS sanity, Jina residency and recent-device-error helpers without changing qualification policy.
- Add deterministic coverage for successful and failing internal-function execution under GNU timeout.

* Mon Sep 07 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.9
- Fix harness-v4 benchmark execution so the sanitized qualification shell wrapper runs GNU timeout internally instead of being passed to timeout as a nonexistent executable.
- Preserve the original failed phase/stage and failing-step log in dashboard, status, error context and bundles, with sudo-safe operator guidance and console-tail diagnostics.
- Make source executable-mode validation Git-safe while retaining exact installed 0755 manifest policy, and add deterministic regressions for the real rc=127 revalidation failure path.

* Mon Sep 07 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.8
- Preserve canonical benchmark evidence when harness SIGINT/timeout interrupts an initialized category, generation, runtime, or Open WebUI benchmark.
- Require complete per-measurement Phase-3 resource evidence instead of silently dropping missing context, residency, memory, temperature, or short-decode telemetry.
- Restore source executable-mode consistency for the Open WebUI benchmark, clean current RAG wording, and add deterministic interruption/resource-evidence regressions.

* Mon Sep 07 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.7
- Finalize canonical infra-failure evidence for initialized benchmark runs across category, generation, runtime, and Open WebUI entry points.
- Tighten Phase-3 qualification so every successful load must retain the required context floor and missing thermal telemetry fails qualification instead of becoming 0 C.
- Surface incomplete/partial revalidation state to operators, correct installer revalidation guidance, document gross-edge threshold provenance, and clean stale current-facing wording.
- Add deterministic adversarial coverage for failure finalization, context reload masking, thermal evidence, partial coverage UX, and installer guidance.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.6
- Finish Round 2C-2 canonical evidence: category aggregates, complete generation summaries, shared package/kernel/runtime/model/fixture metadata, and precise output-vs-thinking budget diagnostics.
- Split runtime/coexistence workflows from Open WebUI lifecycle/tuning workflows and remove stale revalidation compatibility/reboot-era helpers.
- Polish harness v4 operator wording and designate rag-quality --think true/false as the canonical thinking-policy comparison outside revalidation.
- Add deterministic coverage for metadata, aggregate summaries, budget diagnostics, workflow responsibility boundaries, and stale-code removal.
- Correct final quality-cause category mapping, chronological UMA swap aggregation, and explicit max-case-p95 temperature wording.
- Make embedding aggregate evidence canonical, preserve per-model quality causes, complete effective metadata/runtime association, remove legacy agent correctness aliases, and clean failed launch state.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.5
- Make revalidation role scope immutable and restrict Phase 3 to the exact packaged production roster.
- Add measurement-versus-qualification result semantics and aggregate benchmark quality causes.
- Add gross resource-edge qualification gates, secure pre-state OWUI token validation, and final health gates.
- Verify Open WebUI setting restoration and temporary KB/file cleanup; classify RAG residency loss as infrastructure failure.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.4
- Finish the common benchmark-result migration for generation, OCR, RAG, coexistence and Open WebUI tuning workflows with one isolated result-directory layout.
- Remove legacy benchmark aliases and the implicit generation default; public benchmark use is canonical subcommands only.
- Remove the private revalidation tuning helper and expose coexistence and tuning work as explicit benchmark commands while harness v4 remains qualification-only.
- Keep CSV as an optional export while results.jsonl, summary.json, summary.txt, meta.json and copied fixtures form the canonical benchmark evidence.
- Improve generation UMA reporting and multi-cause RAG diagnostics without treating VRAM/GTT counters as additive memory pools.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.3
- Advance bc250-revalidate to harness v4.0: six package-qualification phases, one explicit quality/infrastructure RC path, machine-readable progress events, and separate run/infrastructure/quality/restoration outcomes.
- Remove tuning and hardware A/B decisions from routine revalidation; it now exercises only promoted package defaults while preserving systemd ownership, exclusive agent restoration, snapshots and final bundles.
- Replace heartbeat-as-progress UX with worker state, stage elapsed time and last real event age; add live complete SPI/WGP routing-table health to preflight without hard-coding a universal CU count.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.2
- Close the remaining agent-evaluator false positives: ignore nested Python definitions, require static duplicate-removal evidence, associate range bounds with ValueError branches, and tighten Bash missing-argument/no-match handling.
- Clarify embedding JSONL semantics by keeping per-query Top-3 status as an observational metric; only the explicit aggregate Jina qualification record controls embedding quality status.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.1
- Fix production-usecase common-record serialization, reset reused benchmark sidecars, and make canonical summary parsing fail visibly on malformed schema-managed JSONL.
- Tighten static agent contracts with function-scoped Python AST checks and fixture-specific Bash requirements without executing generated code.
- Move embedding qualification to explicit Jina aggregate thresholds, separate translation source leakage from language failures, and add deterministic graveyard-isolation coverage.
- Clarify that the common result envelope is an initial staged migration and that the active comparison catalog may retain measured controls independently of the source-only graveyard.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.11.0-1.0
- Begin the pre-1.0 benchmark/revalidation redesign: add a common benchmark result schema and human/machine summaries while preserving existing CSV/CLI compatibility.
- Tighten task, translation, production-usecase, agent and OCR evaluator semantics; separate static agent format/syntax/requirements checks and normalize OCR text fidelity independently from structure.
- Add embedding separation-margin and hard-case diagnostics plus start/peak/end swap telemetry so BC-250 UMA evidence is easier to interpret.
- Retire measured non-promotion candidates from normal Modelfile discovery into a source-only graveyard that is excluded from package/model lists.

* Sun Sep 06 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-1.3
- Reuse Hugging Face authentication once per model operation, suppress duplicate catalog/Xet noise, and make Ollama/Podman reconciliation no-op aware.
- Report live 40-CU routing as the availability signal while keeping kernel/RADV CU numbers explicitly diagnostic; align concise appliance status wording with verification semantics.
- Use compact installer verification, keep detailed parity diagnostics explicit, and accept --owui-token-file as an Open WebUI token-file alias.

* Sat Sep 05 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-1.2
- Improve installer API-key/Hugging Face/40-CU wording and no-op behavior, report an already-installed live CU manager, and finish with concise useful commands.
- Advance revalidation to v3.9 with a live dashboard, human-readable status separated from --raw script output, recorded run-harness attribution, and quieter startup/preflight output.
- Treat missing standard cpufreq interfaces as informational when the BC-250 SMU governor is healthy; add protected Open WebUI API-key-file verification and per-lane model counts.
- Add Gemma 4 12B Fable5/Tau2 agentic, GPT-OSS 20B Unsloth UD-Q4_K_XL, and Qwen3.8 4B Empero Q6_K comparison Modelfiles without changing production defaults or routine benchmark scope.

* Sat Sep 05 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-1.1
- Recreate Open WebUI/Tika after application-network reconciliation and avoid unnecessary firewalld reloads so Podman DNS/host-gateway connectivity remains valid after updates.
- Add protected Open WebUI token-file setup/verification, early revalidation network preflight, and foreground revalidation progress with optional --detach.
- Split verifier diagnostics for private Tika DNS/HTTP and host-gateway Ollama connectivity; keep static parity checks model-neutral.

* Sat Sep 05 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-1.0
- Stabilize whole-appliance revalidation control flow: child benchmarks/samplers cannot own global recovery, finished workers no longer remove/reload themselves, and failure bundles include worker error context plus the harness journal.
- Run Open WebUI RAG tuning through the package workspace preset, classify tuning outcomes accurately, and skip authenticated A/B work when package-owned OWUI state is drifted.
- Improve RAG-quality diagnostics for thinking-budget exhaustion, add a default-vs-nonthinking diagnostic A/B, and give the direct grounded-answer lane a larger explicit answer budget.
- Keep noninteractive generation benchmarking production-scoped unless experimental models are explicitly requested, so catalog growth cannot silently widen automated runs.
- Let structurally valid experimental catalog additions coexist with a documented experiment subset instead of making prose inventory lag fail package validation.
- Add Qwen3.8 9B, Qwythos 9B and TIR Qwen3.5 9B non-thinking experimental definitions without changing production roles.
- Retain completed revalidation state for status/inspection until cleanup or the next run, report the current run bundle, propagate authenticated OWUI infrastructure errors only after recording outcomes, and improve agent validation diagnostics.

* Fri Sep 04 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.7.testing
- Preflight custom Ollama /etc service overrides before the pinned upstream installer and reject modified upstream-like units.
- Remove pre-1.0 installer-history bookkeeping and simplify full reset to a declared appliance-owned-state contract.
- Add idempotent memory/swap ensure operations and make the guided installer delegate component-state reconciliation.
- Make one packaged Open WebUI desired-state file authoritative for persisted providers, task, embedding and RAG application settings.
- Simplify agent-mode switching around the static systemd conflict topology.
- Correct remaining command privilege/RAG benchmark documentation and make dedupe restoration exception-safe without a blind catch.
- Refresh runtime/source pins to Ollama 0.33.3, Apache Tika 4.0.0-full and the current CU live-manager revision; keep Open WebUI 0.11.3 and governor 0.4.12.

* Fri Sep 04 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.6.testing
- Package the complete main/task/embedding/agent Ollama service topology; the upstream installer now supplies the binary only.
- Keep Open WebUI dormant across the primary reboot and enable its Quadlet only after baseline task/Jina registration.
- Make unified model operations mode-aware so normal and agent registrations can share one selection safely.
- Add a lightweight fresh-install lifecycle acceptance test covering the reboot boundary and model-before-Open-WebUI order.

* Thu Sep 03 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.5.testing
- Preserve quality-fail benchmark continuation while propagating real revalidation infrastructure failures; recover normal Ollama after num_batch sweeps.
- Replace fixed 40/40 CU success semantics with full live routing-table reporting and problem-cell diagnostics.
- Make XFS dedupe service quiescing/restoration fail visibly, simplify the repository bootstrap, and refresh installer planning/docs.
- Restore source-tree model setup executability and clarify the packaged 4K embedding context cap.

* Thu Sep 03 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.4.testing
- Ship bc250-install from the RPM, reduce the external bootstrap, and make normal setup use one primary reboot with unified model selection.
- Skip genuinely current Ollama registrations and warn on low model-storage headroom.
- Add explicit verified XFS model dedupe/source-prune reporting plus obsolete 40-CU cache pruning; keep all destructive storage actions opt-in.
- Keep RPM post-install integration small and move service/firewall/SELinux provisioning into the explicit installer.
- Package bc250-revalidate as an opt-in reboot-safe benchmark harness; retain only final result bundles after automatic work-state cleanup.

* Thu Sep 03 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.3.testing
- Bound dedicated embedding Modelfiles to 4K context, matching the service policy and reducing avoidable UMA/GTT pressure before GPT-OSS coexistence revalidation.
- Persist the Open WebUI signing secret across container recreation and fix static-vs-enabled agent verification.
- Make task/agent benchmark acceptance return quality-fail status and improve translation equivalence/direction diagnostics.

* Wed Sep 02 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.2.testing
- Preserve the original installer stdin mode across transcript pseudo-terminals so unattended model/Open WebUI setup never blocks on a read.
- Keep agent restoration and legacy network-policy ownership hardening, Open WebUI response-shape validation and Ruff cleanup from the release review.
- Pin and verify the official Ollama v0.33.2 installer script by release commit and SHA-256; document the remaining HTTPS trust boundary for downloaded binary assets.
- Refresh Fedora 44 kernel guidance for 7.1.12: retain the measured TTM/governor baseline while noting the intervening AMDGPU devcoredump fixes and 7.1.12 network panic fix.

* Tue Sep 01 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.10.0-0.1.testing
- Harden failure restoration, legacy network-policy ownership, non-TTY model setup, Open WebUI response validation and the Ollama installer source pin.
- Separate normal production/task/embedding Ollama lanes and make coding/agent mode explicitly exclusive.
- Upgrade the digest-pinned Open WebUI baseline to v0.11.3 and configure package-owned state through supported admin APIs.
- Add interactive/noninteractive Open WebUI initialization, additive model presets, local/offline defaults and optional desired-state drift checks.
- Keep Fedora Mesa, Ollama 0.33.2, TTM-only memory policy, 1850-MHz busy-flag governor and deferred RAG-system-context tuning unchanged.

* Mon Aug 31 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.11.testing
- Simplify the measured BC-250 fresh-machine boot profile to TTM limits only and clean legacy AMDGPU overrides.
- Keep 350-1850 MHz busy-flag governor defaults, harden verification, and document the measured 2000-MHz performance-mode override.
- Add opt-in translation, grounded RAG, OCR-structure, multilingual task and warm-prefix benchmark coverage without adding hardware/model work to build validation.
- Refresh model benchmark conclusions, Open WebUI tuning guidance, installer behavior and operator documentation.

* Mon Aug 31 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.10.testing
- Upgrade the digest-pinned Open WebUI baseline to v0.11.2 and declare local-only Ollama connections.
- Make the full BC-250 GTT/TTM/ppfeaturemask profile first-class on fresh machines and add setup hazard checks.
- Add RAG upload hardening, dynamic catalog validation, centralized runtime pins and GGUF-preserving model cleanup.

* Mon Aug 31 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.9.testing
- Standardize the BC-250 runtime and benchmark request baseline on Ollama 0.33.2.
- Keep prefill/context benchmark points cold across the 0.33.x prompt-cache changes.
- Refresh Vulkan, rollback and Granite 4.2 context-safety guidance without changing production sampling.

* Mon Aug 31 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.8.testing
- Fix task JSON compatibility, LFM latency budgeting and agent reasoning-starvation diagnostics.
- Add harder multilingual retrieval fixtures and retain the operator comparison model pool.
- Add Qwen3.8 4B, Granite 4.2 3B/8B, Ling 3.0 Tiny, LFM2.5 2.6B task and Qwen2.5 Coder 7B comparison Modelfiles.

* Sun Aug 30 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.7.testing
- Give reasoning-capable latency runs enough shared num_predict budget to reach final content.
- Remove semantic request-id prompt noise and record answer/thinking presence explicitly.
- Persist context-truncation diagnostics in JSONL and clarify qualitative chat capture semantics.

* Sun Aug 30 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.6.testing
- Pin Open WebUI v0.11.1 and retain the tested Tika 3/local RAG architecture.
- Expose 0.11.1 task parameters without speculative tuning and keep knowledge retention off.
- Refresh Open WebUI task/RAG documentation and upgrade smoke-test guidance.

* Sun Aug 30 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.5.testing
- Harden model/source integrity, cold benchmark state and RAG provenance validation
- Debloat compatibility commands, rename MTP quick comparison and add CI linting
- Harden RAG error handling, manifest source containment and cache-free source archives

* Sun Aug 30 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.4.testing
- Fix Jina embedding metadata source, complete upload pruning pagination and agent unload policy.
- Bind benchmark telemetry to the selected AMD DRM device and improve OCR hallucination scoring.
- Align task fixtures with Open WebUI 0.11.0 behavior and harden fresh-install privacy defaults.
- Add focused cleanup/dimension/reasoning regressions and clarify production-configuration benchmarking.

* Sun Aug 30 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.3.testing
- Add a compact agent/coding correctness benchmark on the isolated agent service.
- Harden benchmark telemetry cleanup and add OCR key-field reading-order scoring.
- Refresh model/install/benchmark documentation and add the pre-1.0 MODEL.md guide.

* Sun Aug 30 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.7-0.2.testing
- Split benchmarking into neutral/production generation, embedding, OCR and task suites.
- Add request-time thermal/UMA telemetry, model digests and JSONL response sidecars.
- Align benchmark request shapes with Ollama 0.32.15 and model-specific think policies.
- Correct Qwen3.6 FableVibes sampling and the production Qwen3.5 multilingual SYSTEM prompt.
- Add a source-grounded Open WebUI RAG template and model-specific OCR prompts.

* Thu Aug 27 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.7.testing
- Standardize the tested Ollama runtime on 0.32.15 while retaining explicit comparison overrides.
- Overhaul model benchmarking with moderate/conservative profiles, prefill/context/headroom metrics and embedding-specific tests.
- Make the moderate Open WebUI RAG baseline 1500/200/Top-K-8 and disable retrieval-query rewriting for the measured baseline.
- Clean temporary Ollama-HF backing registrations and allow explicit pruning of an emptied generated RAG language lane.

* Wed Aug 26 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.6.testing
- Add metadata-aware incremental RAG import for the public/confidential COLLECTION/active layout.
- Route authoritative German originals and French translations into separate Open WebUI knowledge bases.
- Verify Markdown source PDF checksums locally; keep remote pruning explicit.

* Tue Aug 25 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.5.testing
- Add a privacy-oriented Open WebUI/Tika RAG baseline for German/French/English office documents
- Package deterministic chunking/retrieval defaults and Jina query/document prefixes for fresh installs
- Report RAG embedding/extraction configuration without loading the embedding model
- Add a document-free pilot evaluation template and explicit full-backup/hardening guidance

* Tue Aug 25 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.4.testing
- Fix OCR alias validation and rename the GLM experiment to reflect its ggml-org source
- Explicitly disable llama.cpp idle-slot prompt caching for MTP when supported
- Harden CPU sysfs diagnostics and make multi-command temperature examples one-shot
- Keep Chandra provenance aligned with the current upstream dotted GGUF filename

* Tue Aug 25 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.3.testing
- Add compact experimental office OCR workflows for GLM, dots.ocr, OvisOCR2 and Chandra
- Report CPU topology, cpufreq and C-state availability without enabling extra CPU cores
- Disable llama.cpp RAM prompt cache for MTP when supported and flag context truncation in benchmarks
- Make temperature watching the default and align diagnostics with governor v0.4.12 / 1850 MHz

* Tue Aug 25 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.2.testing
- Restore GGUF provenance matching while preserving Modelfile-only reuse
- Let clean installs log before util-linux-script arrives and fix guided MTP selection
- Restore free-space warnings and tighten model-instance and active-zone firewall status
- Pin Ornith Q5_K_M to the upstream commit matching its exact checksum

* Mon Aug 24 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.6-0.1.testing
- Streamline model handling and reuse validated GGUF bytes unless refresh is explicit
- Extend guided model selection with experiments and MTP without duplicating setup logic
- Consolidate appliance storage, memory, cache cleanup and network visibility
- Report stale CU preparation after kernel changes and validate upstream pin/spec alignment

* Mon Aug 24 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.5-0.3.testing
- Add one fast maintenance setup, status, manual-run and disable command
- Serialize persistent backups and keep deletion and model warm-up opt-in
- Make after-hours poweroff or suspend safe without requiring Wake-on-LAN
- Harden upload pruning against disabled rules and incomplete file metadata

* Mon Aug 24 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.5-0.2.testing
- Split guided model setup into sequential list, selection and installation phases
- Verify the selected RPM NEVRA and complete both post-install diagnostic reports

* Mon Aug 24 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.5-0.1.testing
- Discover embedding GGUFs through the same strict Modelfile workflow as chat models
- Make task, agentic and embedding downloads explicit model selections
- Refresh the recommended office and tooling model set without removing alternatives
- Normalize the operator-supplied Modelfiles and correct the pinned Jina GGUF digest

* Mon Aug 24 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.4-0.1.testing
- Detect optional dedicated GFX1013 compute queues without bundling the patch stack
- Fail verification when a selected custom Mesa ICD lacks its matching patched kernel
- Report the exact Ollama version and recent Vulkan or AMDGPU failure signatures
- Document smoke testing for new Ollama Vulkan releases and kernel-bound patch rebuilds

* Sun Aug 23 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.3-0.1.testing
- Pin Open WebUI v0.11.0 by OCI index digest for clean-install testing
- Document the required complete data snapshot before an existing UI is migrated
- Keep kernel-devel and 40-CU checks tied to the running kernel rather than a NEVRA
- Retain governor v0.4.12, busy-flag usage, fix-freq false and the 1850 MHz maximum
- Make repository validation independent of the optional /dev/fd mount

* Fri Aug 21 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.2-0.1.testing
- Update the Cyan Skillfish governor to v0.4.12 at its pinned release commit
- Keep busy-flag usage detection and make the new fix-freq option explicitly false
- Report running kernel, matching kernel-devel tree and AMDGPU module vermagic
- Warn when AMDGPU belongs to another kernel and 40-CU preparation must be repeated
- Report the installed governor version and effective fix-freq setting

* Thu Jul 23 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.1-0.1.testing
- Add a concise read-only appliance status command
- Report Ollama instances, live CUs, governor, memory, storage and sensors together
- Add an optional reversible swappiness setting to the existing swap profile
- Expand zram, fan and PWM visibility without installing another control stack
- Set the fresh-install governor range to 350-1850 MHz
- Credit the upstream and community projects that make the appliance possible

* Wed Jul 22 2026 Kieni1 <213498859+Kieni1@users.noreply.github.com> - 0.9.0-0.1.testing
- Discover Ollama models directly from strict long-name Modelfiles
- Add an operator models.d drop-in directory with package-overriding precedence
- Remove duplicate production, experiment, task and agentic TOML catalogs
- Retain MTP TOML only for download-only runtime metadata
- Keep model revisions flexible and checksums optional for pre-production testing
- Put binary and source RPM outputs together in dist
- Add the missing util-linux-script runtime dependency for visible download progress
- Document the installed filesystem and the Modelfile-only extension workflow

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

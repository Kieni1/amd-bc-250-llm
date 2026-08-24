# Changelog

## 0.9.4-testing - 2026-08-24

`bc250-verify` now reports dedicated Vulkan compute queue families and detects
the optional external GFX1013 kernel/Mesa patch stack without packaging it. A
custom `/opt/bc250-gfx1013` Mesa ICD selected without the project's patched
boot marker and matching kernel-specific `updates/amdgpu.ko` is a failure. The
documentation keeps this experimental module workflow separate from the
package's existing 40-CU replacement helper and requires a rebuild after every
kernel update.

The verifier now prints the exact Ollama version and scans recent Ollama and
kernel journal entries for `ErrorDeviceLost`, command-submission memory errors
and AMDGPU compute-ring timeouts. Ollama Vulkan updates are documented as
reviewed smoke-test candidates rather than automatic recommended baselines; a
smaller per-model `num_batch` is documented only as a diagnostic for the
reported long-prompt timeout case.

The Fedora kernel, governor and existing 40-CU upstream inputs remain unpinned
from runtime kernel versions and otherwise unchanged.

## 0.9.3-testing - 2026-08-23

This integration update pins Open WebUI v0.11.0 by its OCI index digest while
retaining the existing Ollama, private Tika, persistent-data, loopback and
privacy settings. Clean installations initialize the current schema directly.
Because v0.11.0 includes database schema changes, existing installations must
take a complete offline snapshot of `/var/lib/open-webui` before upgrading.

The Fedora kernel workflow remains tied to the kernel actually running, not to
a release number. Installation and 40-CU preparation use `uname -r` and the
matching kernel-devel tree; verification reports the AMDGPU module path and
vermagic and warns when the module must be rebuilt after a kernel update. The
governor remains pinned to v0.4.12 with `fix-freq = false`,
`method = "busy-flag"` and the fresh-install 1850 MHz maximum.

The shell validation entry point no longer depends on `/dev/fd`, allowing the
same checks to run in restricted build environments without changing the test
scope.

## 0.9.2-testing - 2026-08-21

This focused hardware-maintenance update pins Cyan Skillfish governor v0.4.12
at commit `be9537fc36f24b17570088cafa8c79365f80fee8`. Fresh installations keep
the existing conservative usage policy, now expressed as `fix-freq = false`
and `method = "busy-flag"`. Operators should enable `fix-freq` only for the
eight-core GPU-frequency reporting problem; the optional `kernel` usage method
still requires a separately patched compatible kernel.

`bc250-verify` now reports the running kernel, matching kernel-devel/build tree,
AMDGPU module path and vermagic, installed governor version and effective
`fix-freq`/usage-method settings. A kernel/module mismatch produces an explicit
warning to rebuild and reapply the 40-CU module after a Fedora kernel update.
No Fedora kernel release is hard-coded, and the existing Vulkan-oriented Ollama
configuration remains unchanged.

## 0.9.1-testing - 2026-07-23

This operational update adds `bc250-status`, a concise read-only overview of
the kernel, live CU report, governor, all three Ollama instances, web services,
memory, swap, storage and sensors. The existing verifier remains the detailed
pass/fail tool.

The swap profile now reports `vm.swappiness` and accepts an optional
`SWAPPINESS=0..200` override. It records the previous runtime value so profile
removal and full purge can restore it. If the variable is unset, existing
system policy is left alone. Sensor checks now include fan readings and
available PWM controls without installing an experimental fan-control stack.

Fresh installations use a 350–1850 MHz governor range. The 2000 MHz curve point
remains available for deliberate operator overrides, and `%config(noreplace)`
continues to preserve an existing governor configuration during upgrades.

## 0.9.0-testing - 2026-07-22

This update removes duplicated Ollama catalogs and makes each strict
`.Modelfile` the complete discoverable model definition. Packaged templates are
read from `/usr/share`; operator additions and same-name overrides are read
from `/etc/bc250-llm-server/models.d`. Production and experiment downloads
still require an explicit selection, while task and agentic setup keep their
dedicated Ollama instances on ports 11435 and 11436.

MTP retains its TOML because its llama.cpp context and draft-token fields do
not belong in an Ollama Modelfile. Revisions remain flexible and SHA-256
metadata is optional; downloaded files are still hashed and recorded locally.
The build now places source and binary RPMs together in `dist/`, declares the
Fedora `util-linux-script` dependency needed for visible Hugging Face progress,
and includes an installed-files overview.

## 0.8.1-testing - 2026-07-22

This maintenance release adds a bounded, explicit full-purge path, retains
live model-download progress and integrates default-off 40-CU preparation.

### 40-CU preparation

- The guided installer installs development files for the exact running kernel
  and prepares the replacement AMDGPU module without enabling additional CUs.
- Kernel source is cached, repeated builds are skipped, and the module embedded
  in the rebuilt initramfs is inspected before preparation succeeds.
- `status` now distinguishes the on-disk module, initramfs copy and actually
  loaded driver instead of reporting an on-disk patch as active.
- Secure Boot/signature enforcement is detected before an unsigned replacement
  is installed. Activation remains one explicit command and reboot.
- Corrected module verification so `pipefail` cannot misclassify a valid built
  module, and activation now skips the redundant preparation pass when the
  installed and initramfs copies are already verified.
- Added `install --models-only` to resume optional production, task, agentic and
  embedding setup after a reboot or interrupted system-setup run.

### Uninstall

- Added `sudo bc250-uninstall`, guarded by a destructive confirmation phrase.
- The purge removes package-owned configuration, all appliance model/UI/cache/
  backup data, isolated Ollama instances, official Ollama installed by this
  setup, containers, network, profiles and generated services.
- It removes CU live-manager persistence and restores verified stock AMDGPU
  module backups for every affected installed kernel before rebuilding module
  metadata and initramfs.
- The guided installer records packages that were absent before its own package
  transactions. Purge removes only that recorded set; it never guesses on an
  upgraded installation without a record.
- Pre-install firewalld HTTP access and the SELinux network boolean are
  recorded and restored instead of being silently reset.
- Filesystem growth and ordinary Fedora upgrades remain irreversible.

## 0.8.0-testing - 2026-07-22

This is the first cleanup step toward 1.0. It keeps the appliance features and
current model set while reducing the two most costly maintenance areas.

### Build

- The source manifest now records pinned commits, URLs and archive names only.
  Per-archive SHA-256 and required-member bookkeeping were removed.
- `make sources` reuses non-empty cached inputs and fetches only missing ones.
- `make clean` preserves the source cache. `make sources-check`,
  `make clean-sources` and `make distclean` make cache handling explicit.
- Release RPM checksums are still generated in `dist/SHA256SUMS`.
- The guided installer excludes Fedora's older Ollama package, verifies safe
  removal of an existing copy, and no longer sends `latest` as a version query
  to the official Ollama installer.
- The RPM now carries a sysusers declaration and provides its own `ollama`
  account capabilities, eliminating the dependency on Fedora's Ollama RPM.

### Models

- Consolidated model fetching, validation, state, registration and cleanup in
  one focused `modelctl.py`; the public command and TOML catalogs remain.
- Model selection accepts stable ids and Ollama display names as well as the
  existing numeric indices and ranges. Invalid selections now fail clearly.
- Minimal source/checksum state is reused for commits, tags, branches and
  `latest`; use `--refresh` when a moving revision should be fetched again.
- Hugging Face authentication is resolved only when a download is required.
  `HF_TOKEN` or `--token-file` is validated as `ollama`; an invalid or missing
  token falls back to anonymous downloads. Tokens are no longer written to
  operator shell files.
- Model-manager messages are line-buffered and Hugging Face downloads retain a
  pseudo-terminal, keeping status and live byte progress ordered in installer
  transcripts.
- Low-space installation now stops with an explicit cleanup command instead of
  offering destructive cleanup in the middle of a download workflow.
- Cleanup is explicit, asks for confirmation, removes local artifacts and
  registrations, and never edits `%config(noreplace)` catalogs.

### Preserved

- All current production, experiment, task, agentic and MTP catalog entries and
  Modelfiles.
- Strict Modelfile name/source/revision/GGUF/path validation and BC-250
  `num_gpu 99` / `num_keep 256` parameters.
- Main Ollama on 11434, task Ollama on 11435 and agent Ollama on 11436.
- Pinned governor, 40-CU unlock and CU live-manager sources.

## 0.7.1-testing - 2026-07-22

This update focuses on operational stability during model installation on a
pre-production BC-250 appliance.

### Why

- Model fetches were brittle when Hugging Face rate limits or private/gated
  access required a token: the previous prompt was one-shot and not clearly
  validated as the `ollama` service account.
- Operators could select models interactively, but nonstandard sudo/TTY setups
  could fall back poorly and make it hard to trust what would be installed.
- State-file reuse is useful, but testing moving revisions sometimes needs a
  single explicit command to force a new GGUF, hash and Ollama registration.
- Low disk space is common on local LLM appliances. The manager should offer a
  safe cleanup path before failing a large download.

### Changed

- `bc250-model install` now validates `HF_TOKEN` with `hf auth whoami` using the
  `ollama` account.
- If no valid token is available and a TTY exists, the installer offers:
  `[P]ersist`, `[T]his run only` and `[S]kip`.
- Persisted tokens are written to the invoking sudo user's `.bashrc` instead of
  silently targeting root when `SUDO_USER` is available.
- Added `--refresh` to force GGUF download, SHA-256 calculation and Ollama
  registration even when the state file matches.
- Added a low-space cleanup prompt. The default threshold is 30 GiB, or a higher
  explicit/catalog minimum if one is configured; it can be overridden with
  `--cleanup-threshold-bytes` or `BC250_CLEANUP_FREE_BYTES`.
- Added `bc250-model cleanup` for explicit cleanup of enabled production and
  experiment Ollama models.
- Cleanup removes the Ollama registration, source GGUF and adjacent
  `.bc250.json` state file, then disables the installed TOML catalog entry when
  possible.
- If automatic catalog editing is unavailable or fails, cleanup prints the exact
  `sudoedit` command and model id to disable manually.

### Preserved

- Existing command-line arguments remain supported.
- TOML catalogs remain the only model catalog format.
- State files, Modelfile rendering, strict metadata validation and ordinary
  Ollama registration behavior are preserved.
- Production and experiment downloads remain disabled by default.
- Existing `%config(noreplace)` package behavior is unchanged.

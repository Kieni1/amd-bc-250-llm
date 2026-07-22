# Changelog

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

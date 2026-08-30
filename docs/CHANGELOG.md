# Changelog

## 0.9.7-0.7.testing - 2026-08-30

Correct generation-latency interpretation for reasoning-capable models after the
first full JSONL review. Keep the existing 96/64-token latency cap for explicit
non-thinking profiles, but use 512/384 for policies where reasoning can consume
the shared Ollama `num_predict` budget. Preserve `NUM_PREDICT_LATENCY` as a global
override and add an optional `NUM_PREDICT_LATENCY_THINKING` split override.

Remove the semantic `[reqid ...]` cache-busting text in favor of harmless leading
blank-line prompt variants. Record whether a streamed final answer actually
started plus answer/thinking character counts, warn when a latency request reaches
`done_reason=length` without final content, and persist context-truncation warnings
and near-limit notes in JSONL. Clarify that streamed `/api/chat` records are the
preferred qualitative source for families whose raw `/api/generate` output may
contain native reasoning markers. Generation benchmark metadata is now 7.2.

## 0.9.7-0.6.testing - 2026-08-30

Upgrade the digest-pinned Open WebUI baseline from v0.11.0 to v0.11.1 for its
security/access-control, RAG/knowledge, streaming and native Ollama reasoning-history
fixes while retaining the existing three-Ollama/Tika architecture. Keep Tika on
major version 3 and explicitly leave knowledge-file retention disabled.

Expose the new `TASK_MODEL_PARAMS` control at `{}` rather than introducing an
unmeasured task-sampling profile. Refresh the task benchmark compatibility labels,
RAG/upgrade documentation and smoke-test guidance without changing the compact task
prompts or enabling ORJSON/new agentic Open WebUI features.

## 0.9.7-0.5.testing - 2026-08-30

Harden manager-owned GGUF reuse with schema-2 state metadata: unchanged size,
mtime and ctime use the fast path; changed/legacy state is SHA-256 verified before
reuse. Model cleanup now retains local source files when an Ollama registration
cannot be removed.

Require confirmed model unload before measurements labelled cold, normalize
scheme-less Ollama hosts, and let agent benchmarks inherit deployed sampling by
default (`AGENT_TEMPERATURE` remains an explicit deterministic override).

Make RAG front matter a strict documented YAML subset, require `source_file` to
remain inside its collection's `sources/` directory, and reject active/source
symlink escapes. Protect reusable RPM source archives and the generated Cargo
vendor archive with local SHA-256 sidecars; `sources-check` now verifies them.

Remove the dead sensor logger and obsolete `install-cu-manager` /
`pull-embedding-model` compatibility commands. Rename the narrow speed-only
experiment helper to `bc250-compare-mtp`. CI now runs on pushes and pull requests
and adds Fedora Ruff/ShellCheck before the RPM build. Follow-up hardening catches
malformed Open WebUI sync response types cleanly, rejects tab-indented RAG metadata,
keeps install-manifest sources inside the source tree, and excludes Ruff/Python caches
from handoff/source archives.

## 0.9.7-0.4.testing - 2026-08-30

Fix the reviewed Jina embedding source to the upstream Q4_K_M GGUF carrying
`pooling_type` metadata, paginate the complete Open WebUI upload inventory before
pruning, and make the agent benchmark respect the isolated service residency
policy with guaranteed immediate unload.

Bind benchmark thermal/GPU/VRAM/GTT sampling to one selected AMD DRM device,
use its edge/on-die temperature for the 80/83/85 C thresholds, and bump generation
benchmark metadata to 7.1 for the changed telemetry semantics. Add embedding
dimension validation and exception-safe per-model unload cleanup.

Make OCR quality scoring penalize hallucinated output with token precision/F1 and
normalized character similarity while retaining exact required-field/order checks.
Align compact task fixtures with Open WebUI 0.11.0 message-window/tag/query
behavior, remove the legacy experiment helper's global `think:false`, and set a
fresh-install Open WebUI privacy baseline for sharing, code execution/interpreter
and memories. Clarify that `BENCH_MODE=production` remains a generic
production-configuration comparison; role-specific use-case benchmarking stays
deferred.

## 0.9.7-0.3.testing - 2026-08-30

Add a compact `bc250-benchmark agent` lane for the isolated port-11436 service.
The deterministic fixtures validate Bash/Python syntax and required structured
output without executing model-generated code. This keeps coding correctness
visible without adding a separate benchmark framework or dependency.

Harden embedding/OCR telemetry cleanup so sampler threads are stopped on request
errors. OCR now also reports required-field reading-order score. Task telemetry
and lighter category metadata remain intentionally unchanged.

Refresh benchmark, model and installation documentation, correct the source-tree
benchmark link, add `MODEL.md`, and document the pre-1.0 green-field installer
policy and intentionally flexible model revisions.

## 0.9.7-0.2.testing - 2026-08-30

Refactor `bc250-benchmark` into a thin dispatcher with stdlib-only Python suites
for generation, embeddings, OCR and the isolated Open WebUI task model. Generation
now separates a neutral cross-model mode from production Modelfile behavior, uses
model-family `think` policies compatible with Ollama 0.32.15, records response
JSONL and model digests, and treats short `done_reason=stop` separately from a
normal `length` limit.

Add request-time BC-250 telemetry for peak/p95 temperature, time at 80/83/85 C,
GPU busy/clock range, AMDGPU VRAM/GTT counters, minimum `MemAvailable`, maximum
swap use and Ollama allocation. `RUN_THERMAL=1` adds sustained decode windows.
Resource values are documented as overlapping UMA signals rather than independent
pools.

Add multilingual office fixtures and quality metrics for Jina/Qwen embeddings,
GLM/dots/Ovis/Chandra OCR and Open WebUI 0.11-style title/tag/retrieval-query
tasks. OCR prompts are model-specific and preserve source language.

Correct Qwen3.6 FableVibes to upstream `1.0 / 0.95 / 20` sampling, replace the
production Qwen3.5 stale experimental SYSTEM with the multilingual office prompt,
and add a source-grounded Open WebUI RAG template that reports insufficient
document evidence instead of silently falling back to model knowledge.

## 0.9.6-0.7.testing - 2026-08-27

Make Ollama **0.32.15** the package-standard runtime for BC-250 smoke tests; the
official installer helper now requests that version unless an operator deliberately
sets `OLLAMA_VERSION`. Verification and diagnostics warn, rather than fail, when a
different Ollama runtime is being compared.

Overhaul `bc250-benchmark` around useful BC-250/office measurements instead of a
single generation tok/s figure. The default `moderate` profile now separates cold
model-switch latency, warm latency, loaded decode throughput, document-prefill
throughput, context-capacity/truncation behavior, loaded Ollama allocation and host
memory/swap headroom. `conservative` is a shorter lower-context pass. Optional
embedding benchmarking uses `/api/embed` with a multilingual office batch; OCR
remains a real-page quality test through `bc250-ocr`. Dedicated task/agent stores
can be measured by pointing `OLLAMA_URL` at ports 11435/11436.

Make the fresh-install RAG baseline **moderate** at 1500-token chunks, 200 overlap
and Top K 8. Keep 1000/100/5 as the documented conservative alternative. Retrieval
query generation is disabled for the baseline so embedding/chunking quality is
measured before task-model query rewriting is introduced. Documentation now
distinguishes reindexing from source re-upload/re-sync.

`modelctl.py` removes redundant temporary `hf.co/...` OCR registrations after a
friendly packaged alias is created, while retaining safe status handling if cleanup
cannot occur. `bc250-rag-import --prune` can also clear the final stale remote file
when a generated Originals/Français lane has become locally empty.

## 0.9.6-0.6.testing - 2026-08-26

Add `bc250-rag-import` for the operator-owned `/srv/bc250-documents` tree. It
validates active Markdown front matter and source-PDF SHA-256 provenance, then
incrementally syncs each collection into separate Originals and Français Open
WebUI knowledge bases while keeping public/confidential boundaries distinct.
German originals remain authoritative; French translations are intended for
French queries. Remote files removed locally are retained unless `--prune` is
explicitly requested.

The package now creates `/srv/bc250-documents` as `root:root` mode `0750` and
ships a metadata-only Markdown template. No real office documents or API keys
are packaged.

## 0.9.6-0.5.testing - 2026-08-25

Add a privacy-oriented Open WebUI/Tika RAG baseline for German/French/English
office documents without adding another retrieval service or ingesting example
business data. Fresh installs now start with deterministic 1000/100 token
chunking, Top K 5, Markdown-header splitting, vector-only search, sequential
Ollama embeddings and Jina `Query:` / `Document:` prefixes.

`bc250-verify` reports the Open WebUI embedding/extraction defaults and checks
that the configured embedding model is registered with main Ollama without
running an embedding request. The installer points operators to the new RAG
guide after an embedding selection. Documentation covers Open WebUI v0.11.0's
Native-mode knowledge behavior, DE/FR cross-language evaluation, OCR-first
scans, reindexing, confidential data paths and complete stopped-instance
backups. A blank pilot evaluation TSV is packaged; no real documents are.

## 0.9.6-0.4.testing - 2026-08-25

Correct `bc250-ocr install/show` alias validation so an unknown OCR model exits
with status 2 before invoking the model manager or Ollama. Rename the GLM OCR
experiment to `exp-glm-ocr-ggml-q8-0` so its testing name reflects the actual
`ggml-org` source. Existing registrations under the old experimental name are
left untouched and may appear as unmanaged until the operator removes them.

MTP now explicitly adds `--no-cache-idle-slots` when supported alongside
`--cache-ram 0`. CPU power-state diagnostics ignore an unexpanded sysfs CPU
glob on systems where that interface is absent. Multi-command documentation
uses `bc250-check-temp --once` so the default continuous watcher does not block
following commands. Chandra keeps the currently published dotted upstream GGUF
filename `chandra-ocr-2.Q4_K_M.gguf`.

## 0.9.6-0.3.testing - 2026-08-25

Add four compact experimental office OCR definitions (GLM-OCR, dots.ocr,
OvisOCR2 and Chandra OCR 2) plus `bc250-ocr`, a thin list/install/show/test
wrapper over the shared model manager and main Ollama instance. GLM uses a 16K
context; Chandra remains a Q4_K_M compatibility probe pending real BC-250 image
testing.

Status and verification now report CPU topology, cpufreq driver/governor and
missing cpuidle states without adding CPU-unlock behavior. MTP disables the
llama.cpp RAM prompt cache when that option is available. Benchmarks warn when
`prompt_eval_count` stops growing and label SMU power as uncalibrated. Temperature
monitoring is continuous by default, while legacy diagnostics now match governor
v0.4.12 and the 1850 MHz package default.

## 0.9.6-0.2.testing - 2026-08-25

Correct model reuse so cached GGUF bytes are accepted only when repository,
revision and filename still match their recorded provenance. Modelfile-only
SYSTEM/PARAMETER edits continue to reuse the same bytes, while a changed source
identity triggers a download. Ornith Q5_K_M is pinned to the upstream commit
matching its packaged exact checksum.

Clean Fedora installation can now start its transcript with `tee` before the RPM
provides `util-linux-script`; `/usr/bin/script` is required only when a selected
model download needs visible progress. Guided MTP selection explicitly lists
and opts into its disabled download-only entries.

`bc250-status` again warns when root free space falls below `MIN_FREE_GB`. Model
listing reports known registrations on the wrong Ollama instance, firewall
verification checks every active zone plus accepting rich rules, and cache
cleanup documentation states that journal vacuuming is system-wide.

## 0.9.6-0.1.testing - 2026-08-24

This streamlining update expands the guided model stage to production, task,
agentic, embedding, experiments and MTP through one shared installer path. The
installer checks Fedora's `script` prerequisite before changing the system and
ends with the short `sudo bc250-40cu` next step while leaving CU activation
explicit and board-specific.

Model replacement now reuses an already validated GGUF when only source
metadata changes and rebuilds the Ollama registration; `--refresh` remains the
explicit way to fetch new bytes. Model discovery, validation and Ollama host
selection share fewer code paths without renaming or removing packaged models.

`bc250-status` now combines per-instance model storage, Hugging Face cache,
Podman, journal, memory pressure, zram, disk swap and swappiness visibility.
`bc250-maintenance clean-cache` is an explicitly confirmed rebuildable-cache
cleanup that retains GGUFs, Ollama models and Open WebUI data. Verification
checks the internal Ollama listener shape/firewall policy, CU status reports
stale kernel preparation, and deterministic validation cross-checks upstream
pins against the RPM spec.

## 0.9.5-0.3.testing - 2026-08-24

The optional maintenance stack now has one `bc250-maintenance` command for a
fast backup-only baseline, guided office scheduling, storage/backup status,
manual runs and clean schedule disabling. Local backups persist across missed
timer events and are serialized with idle I/O priority.

Upload pruning retains its safe dry-run default, treats zero as “disable this
rule” instead of “delete everything,” and preserves files whose age or size is
not trustworthy. Warm-up is still opt-in, now follows the current standard
office model and keeps it resident for only 15 minutes by default.

The former suspend-only helper is now an explicit `poweroff` or `suspend`
action. It covers HTTP as well as HTTPS/SSH/Ollama sessions, no longer fails
merely because Wake-on-LAN was not configured, and can require verified WOL
before acting. Documentation distinguishes same-disk recovery points from an
encrypted complete off-machine backup.

## 0.9.5-0.2.testing - 2026-08-24

The guided model stage is divided into four complete phases: production, task,
agentic and embedding. Each phase now lists, prompts and installs before the
next begins, while Hugging Face authentication is prepared only once. The
installer also distinguishes a same-NEVRA reinstall from a different-version
RPM transaction, verifies that the selected RPM is the one installed, avoids
repeating the 40-CU helper's activation message, and runs both verification
reports before returning a failure.

## 0.9.5-0.1.testing - 2026-08-24

Embedding models now use the same strict Modelfile discovery, Hugging Face
download, checksum and Ollama registration path as the chat categories. The
guided installer presents explicit selections for production, task, agentic
and embedding models; it no longer silently installs every discovered model in
a tooling category. Existing compatibility commands remain available.

The current operator-supplied model folder is retained and normalized to the
repository's strict metadata and storage rules. The Jina v5 small retrieval
GGUF is pinned to its verified upstream revision and corrected SHA-256. Current
recommended roles now point to Gemma 4 E2B/E4B, LFM 2.5, GPT-OSS 20B, Jina v5,
Gemma 3 1B and Ornith 1.5 while all other Modelfiles remain selectable for
testing.

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

# BC-250 LLM appliance: quick sheet

This is the common-path operator sheet. Use [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
for the complete command reference and the topic docs for rationale/recovery details.

Current release source: `bc250-llm-server-0.14.1-1.7.1` — stock Fedora AMDGPU/Mesa clean-core baseline, Ollama 0.40.8, Open WebUI 0.12.3, Tika 4.1.0-full, governor 0.4.14; GitHub/Fedora 44 selected workflow-dispatch artifacts are release authority.

Release 1.7.1 is a structural cleanup over the 1.7 source/behavioral regression baseline: `bc250 document` is the document lifecycle surface, specialist agent/MTP/benchmark/qualification/coding controls live under `bc250 advanced`, ordinary model discovery defaults to the combined catalog, and duplicated release/build policy has been reduced. Runtime/model/retrieval tuning and the SRPM-first authority path are unchanged; exact 1.7.1 build/device binding is required.

## Install

Keep the binary RPM beside the repository bootstrap:

```bash
sudo ./install
```

The bootstrap installs the RPM and invokes `bc250 install`, which owns Fedora update
and appliance provisioning policy. After the requested primary reboot, resume with:

```bash
sudo bc250 install
```

Use `sudo bc250 install --models-only` to reconcile runtime topology, models and Open
WebUI without system/kernel setup. The task and Jina embedding models are baseline
infrastructure; the additional-model prompt accepts indexes/ranges/names or
`recommended`, `production`, `all`, and Enter skips extras. Unattended selection uses
`BC250_MODEL_SELECTION`.

Full interactive installs verify the core appliance first, then present local maintenance
and Raspberry Pi/companion integration as separate optional choices. Pi/companion setup
remains default-No, and selected setup is verified before completion. Models-only and noninteractive runs do not silently enable those features. Legacy
full-unit task/embedding/agent overrides are rejected rather than mixed with the
package-owned four-lane topology.

## Verify and open the UI

```bash
sudo bc250 status
sudo bc250 status --json
sudo bc250 health
bc250 version
sudo bc250 verify
sudo bc250 support-bundle   # redacted support evidence archive
sudo bc250 storage status
sudo bc250 storage dedupe
```

`dedupe` keeps both logical files but shares verified identical XFS extents; `df`
reflects reclaimed capacity even when `du` counts both names. Open
`http://SERVER_IP/` from the trusted LAN. If Open WebUI initialization was skipped:

```bash
sudo bc250 advanced openwebui init
```

When an RPM upgrade changes Open WebUI with existing persistent state, RPM `%pre` unconditionally requests Open WebUI stop, proves `ActiveState=inactive`, and holds boot enablement before the new Quadlet can restart. The guided installer then creates a verified stopped-state rollback archive before allowing the new image to start. See
[`docs/OPERATIONS.md`](docs/OPERATIONS.md) for the supported restore procedure.

Qualification evidence can be reviewed with `sudo bc250 advanced qualification list`;
`sudo bc250 advanced qualification clean` only previews old terminal package-gate/resilience
evidence unless `--apply` is explicitly supplied.

For managed documents, keep operator sources under `/srv/bc250-documents`; batch preparation stops at a human review gate:

```bash
sudo bc250 document status
sudo bc250 document validate public COLLECTION
sudo bc250 document ingest --token-file /var/lib/bc250-llm-server/secrets/openwebui-admin.key
```

Document/knowledge synchronization is loopback-only by default and token-file symlinks are rejected. `document status` reports review/currentness/fidelity state plus lifecycle validation health. Remote Open WebUI requires explicit opt-in, with a separate override whenever confidential-scope knowledge state could participate in the sync. See [`docs/RAG.md`](docs/RAG.md) before bulk ingestion. HTTP is not encrypted; use [`docs/HTTPS.md`](docs/HTTPS.md) if HTTPS is required.

## Models

```bash
bc250 model list                    # ordinary combined catalog view
bc250 advanced agent list           # specialist agent view
bc250 advanced mtp list             # specialist MTP view
sudo bc250 advanced mtp prepare qwen3.5-9b-mtp  # explicit opt-in MTP preparation
LLAMACPP=/opt/llama.cpp/build/bin/llama-server bc250 advanced mtp compare qwen3.5-9b-mtp

# Generic installer / `apply all` selection never includes MTP; use bc250 advanced mtp prepare explicitly.
sudo bc250 model install
sudo bc250 advanced agent status MODEL
sudo bc250 advanced agent status MODEL --verbose
sudo bc250 model apply production
sudo bc250 model apply experiments
sudo bc250 model apply task
sudo bc250 model apply agentic
sudo bc250 model apply embedding

# Deliberately fetch source bytes again
sudo bc250 model refresh experiments MODEL

# Remove registration only; retain verified GGUF/state
sudo bc250 model unregister experiments MODEL

# Remove registration plus manager-owned GGUF/state
sudo bc250 model remove experiments MODEL
```

Selections accept a full name, displayed index, ranges such as `0,2-4`, or `all`.
`list` is catalog-only; use `sudo bc250 model status` when you need downloaded,
registration or Modelfile-drift state. `--verbose` also shows source repository/revision,
verified SHA-256 when available and resolved paths; `--online` checks moving upstream state. Enter cancels an interactive selection. Preserve
downloaded GGUFs where practical; use package lifecycle commands rather than deleting
`/var/lib` content manually.

## Profiles and hardware

```bash
sudo bc250 status
sudo bc250 verify
bc250 advanced ollama-profile status
sudo bc250-cu-live-manager
sudo bc250-40cu status
```

Memory/TTM and swap safety profiles are package-managed by `bc250 install`; use status/verify for normal checks.

Configure/save live routing with `sudo bc250-cu-live-manager`; verify it with `sudo bc250-40cu status`. See [`docs/HARDWARE.md`](docs/HARDWARE.md).

## Operations and maintenance

```bash
bc250 advanced benchmark generation --profile compare
bc250 advanced benchmark generation --profile edge --mode production
bc250 advanced benchmark embeddings
bc250 advanced benchmark ocr
bc250 advanced benchmark task

sudo bc250 advanced agent enter
bc250 advanced benchmark agent
bc250 advanced code run review path/to/file review.md
sudo bc250 advanced agent leave   # `normal` is the explicit convergence alias

sensors
sudo bc250 advanced benchmark parity --no-load
sudo bc250 advanced revalidate status

sudo bc250 maintenance setup --defaults
sudo bc250 maintenance companion status
sudo bc250 maintenance contract
sudo bc250 maintenance run backup
sudo bc250 maintenance run prune
sudo bc250 maintenance clean-cache
```

`setup --defaults` enables verified local backups only. Guided maintenance can also
configure dry-run upload pruning, optional warm-up and optional after-hours safe power.
Pi integration uses office HTTP :80 and restricted SSH :22 only; Wake-on-LAN is an
Ethernet magic packet and opens no host firewall port.

Installed operator documentation is under `/usr/share/doc/bc250-llm-server/`; start with
`TLDR.md`, `docs/OPERATIONS.md`, `MODELS.md` and `docs/FILESTRUCTURE.md`. Runtime
configuration is under `/etc/bc250-llm-server/`, package state/evidence under
`/var/lib/bc250-llm-server/`, and installer output under `/var/log/bc250-llm-install.log`.

## Services

```bash
sudo systemctl status \
  cyan-skillfish-governor-smu.service \
  ollama.service ollama-task.service ollama-embedding.service \
  open-webui.service tika.service nginx.service
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:11437/api/tags
```

Normal mode uses main `11434`, task `11435` and embedding `11437`. Agent `11436` is
exclusive and disabled at boot. Open WebUI is enabled by `bc250 install` only after
baseline model registration. Keep `11434`–`11437` blocked from untrusted networks.

## Remove

```bash
# Keep models and persistent application data
sudo dnf remove bc250-llm-server.x86_64

# Explicit greenfield appliance reset
sudo bc250 reset
```

Reset preserves `/srv/bc250-documents` and does not undo Fedora upgrades/filesystem
growth. Read
[`docs/RESET.md`](docs/RESET.md) before reset.

## Full qualification

```bash
sudo bc250 advanced revalidate start
```

It is opt-in/root-only, includes authenticated production translation-role and RAG
checks when an Open WebUI key is supplied, and stores final bundles under
`/var/lib/bc250-llm-server/revalidation/results/`. See `docs/BENCHMARKING.md`
(installed at the same relative path under `/usr/share/doc/bc250-llm-server/`) for
result directories, tuning commands, RAG qualification and thermal profiles.

> **0.20.0-6 exact-DEVICE gates (new, 2026-11-09):** Upstream Open WebUI 0.13.3 fixes issue #33933/PR #33936 (`ad95407`), but integration into the new RPM is not yet DEVICE-proven. Block 33 r1 under Open WebUI 0.12.5 observed an API attachment-reference request accepted by a translation role (C3 **FAIL at tested API boundary**, without evidence that file content reached the model). Test real filter wiring and API/browser paths with synthetic files before closure. Block 33's one truncated output withheld is bounded PASS, while general H1 truncation remains REVIEW. Block 32 r2's FR→DE translation oracle remains REVIEW, and managed-document end-to-end citations/absence of superseded revisions and explicit supersede CLI remain NOT_TESTED. Two administrator-private DE/FR RAG choices are included as opt-in recipes; initial stored Knowledge metadata was insufficient for effective live chats, and FR binding requires independent proof. Test runtime migration/reboot, source provenance, Ollama Vulkan and governor cold-boot separately. Do not copy private DEVICE corpus or IDs into repository artifacts. Last fully accepted DEVICE: 0.20.0-3.

> **Current follow-up 2026-11-09 — 0.20.0-6 SOURCE:** Open WebUI 0.13.3 (upstream `ad95407` for escaped punctuation), Ollama 0.40.15 and governor 0.4.15 with packaged GPU udev alias are staged but not built or DEVICE-qualified. Acceptance checks: stopped-state OWUI schema/migration and rollback, Knowledge pagination/permissions and chat-level attachment, `Art\. 40` vs `Art. 40`, Tika empty-response guard, translation and K6 effective behavior, Persisted Automations/Calendar disablement after apply/reboot, Ollama four-lane cold-load plus task/embedding/Agent, Vulkan q8/q4 KV, timeouts/streaming, Deep residency, governor cold boot and service device binding. Ollama prompt-cache cross-request privacy and embedding cancellation are targeted RESEARCH/DEVICE checks, not assumed fixed. Kernel/Mesa/ROCm upgrades and unreleased llama.cpp changes are deferred. 0.20.0-5 provisional K6 DEVICE findings are *not* full DEVICE acceptance.

# Open findings — deferred after 0.20.0-5 SOURCE (2026-11-06)

This page lists review findings that were **consciously not fixed** in `bc250-llm-server-0.20.0-5`.
They are kept here so a later batch can pick them up. None of them blocks the 0.20.0-5 BUILD.
Each entry gives what happens, why it was deferred, and a minimal fix.

IDs refer to the 0.20.0-5 reviews:
- `B*`: release blocking;
- `N*`: nice-to-have;
- `T*`: test suite;
- older `H/M/L/C/MW` IDs: 0.20.0-4 code and model reviews.

The decisions are recorded in `DECISIONS.md` DEC-054.

Remove an entry when it is fixed. A DEVICE observation that settles an item belongs in `VALIDATION-MATRIX.md`.

## Fixed in 0.20.0-5 (for orientation, not open)

| Finding | Fix |
|---|---|
| B1 | Pi pull: mirror plus hardlinked dated snapshots; skip incomplete pairs; Pi units shipped |
| N1 | Prune dry run reads the Knowledge inventory |
| N2 (partly) | Document backup: space check, unchanged-skip with freshness marker, retry on change, stale-stage cleanup |
| N3 | Staging outside the export scopes; sidecar published last |
| N5 | Pi example polish |
| N6 | Unused share copy of the Ollama profiles removed |
| N11 | Installer verify loop includes the documents timer, plus an agreement test |
| T5.1–T5.3, T5.5–T5.7 | Hermetic behaviour tests |
| T1 (partly) | The MC5 staging and export-rights string tests became behaviour tests |

## Accepted during development

### B2 — Upgrades do not enable newly added backup timers
- **What happens:**
  - Maintenance timers are enabled only by `bc250 maintenance setup` / `setup --defaults`.
  - The preset keeps them disabled.
  - So a host that enabled backups on 0.20.0-3/-4 does **not** start `owui-backup-documents.timer` after upgrading to 0.20.0-5.
  - The only signals are `maintenance status` (`WARNING: no Documents backup found`) and the 0.20.0-5 upgrade note.
- **Decision:** acceptable while in development (owner, 2026-11-06). Rerun `sudo bc250 maintenance setup` after upgrading.
- **It recurs:**
  - for **every** timer later added to `BACKUP_TIMERS`;
  - see the note at `cmd/maintenance/maintenance.sh` `BACKUP_TIMERS`.
- **Fix before v1.0:**
  - In `bc250 install` convergence (or a `%posttrans` helper): when any existing backup timer is enabled, enable the missing members of `BACKUP_TIMERS` and print what was added.
  - Alternative: `maintenance status` names the disabled members explicitly.
  - Add an installer test for the upgrade case.

### B3 — Secrets escrow is documentation-only
- **What happens:**
  - `WEBUI_SECRET_KEY` and the package secrets are not in any backup artifact.
  - `docs/OPERATIONS.md` instructs a manual, encrypted, off-device escrow.
  - Without it, a disaster restore loses Open WebUI encrypted fields: MFA, encrypted settings and valves.
- **Decision:** documentation only for now (owner, 2026-11-06). DEC-054 supersedes the MC3 "root-only local secrets backup" variant.
- **Later option:**
  - A root-only `backup-secrets` producer under `rollback/secrets/` (0600, never exported, small KEEP).
  - `maintenance status` reporting "secrets escrow: present/absent".
  - Keep the manual off-device copy step either way.

## Maintenance and companion (maintenance-companion component)

### N2 (rest) — No shared lock between document lifecycle and backup
- **What happens:** `bc250 document activate/supersede` can run during the 18:05 corpus backup. The maintenance `flock` serializes only maintenance tasks.
- **Mitigation now:** `backup-documents.sh` compares a corpus manifest before and after the archive. It retries up to 3 times and publishes only a consistent state.
- **Fix:** have the lifecycle write commands take the same lock (`/run/lock/bc250-llm-maintenance.lock`, or a dedicated documents lock).

### N4 — `reset` leaves Pi access in place
- **What happens:** `reset.sh` keeps these, so an old Pi keeps shutdown and export access after a reinstall:
  - the `bc250-power-control` and `bc250-backup-export` accounts;
  - their `authorized_keys`;
  - `/etc/sudoers.d/bc250-power-control`.
- **Fix:** remove them in `reset`, or list them in the reset summary. This is the boundary-active `reset` component.

### N8 — Open-tab shutdown rule undecided (product decision)
- **What happens:** any established :80/:443 connection, including an idle Open WebUI tab, defers all five night power attempts.
- **Next step:** decide after a DEVICE week shows whether office tabs actually prevent shutdown, then record it in DECISIONS.md.

### N9 — Document restore is manual
- **What happens:** the corpus is restored with a documented `tar` into an empty directory.
- **Fix:** a small `restore-documents.sh` (verify the sidecar, refuse a non-empty target, extract with member validation, test the round trip), matching the other two restores.

### N12 — Upgraded `maintenance.env` keeps old keys
- **What happens:**
  - Existing files keep their old `SAFE_POWER_PORTS` and lack `KEEP_DOCUMENTS` and `DOCS_OUT_DIR`.
  - The runtime compensates: 8090 is force-added and defaults are used.
- **Fix:** `maintenance status` hint "config predates 0.20.0-5 keys; rerun setup to review".

### Pi side (examples only)
- The Pi pull trusts the BC-250 retention set, so the mirror follows deletions. Snapshots keep removed archives for `BC250_PI_BACKUP_KEEP` pulls.
- There is no off-Pi copy, which is in line with "simple, not military grade".

## Other components

### N7 — `coding-agent` (frozen): Gitea token in argv
- **What happens:** `gitea-review.sh` passes `Authorization: token …` on the curl command line, so it is visible in `ps` while running.
- **Fix:** `curl -H @file` or `--config` with a 0600 temp file. This needs a bounded thaw; low priority on a single-admin appliance.

### N10 — Orphan GGUF sources are only reported (MW1, by design)
- **Option:** `storage prune-sources --orphans` with confirmed removal of exactly the reported paths. Never auto-delete.

### N13 — Ruff rule set is not pinned (CI owner)
- **What happens:**
  - There is no `ruff.toml` or `[tool.ruff]`, so the blocking lint uses the distribution's default rules.
  - Local Ruff 0.16.9 reports I001 in 6 files and SIM117 in `tests/test_mc_02005.py`; the same findings passed GitHub CI.
  - A Fedora Ruff update can turn the gate red with no code change.
- **Fix (CI workstream):** an explicit `select`.

### Earlier review residuals (details in the 0.20.0-4 review handovers)
- **H1 (residual):**
  - The translation guard cannot see runtime truncation, because the outlet sees only the final text.
  - Number words are withheld conservatively rather than compared.
- **L2:** `BC250_OWUI_DESIRED_STATE` is an environment-only alternate authority. Benchmarks and campaign tooling do not all honor it.
- **M7 (residual):** Knowledge bases of collections without an `active/` directory are not enumerated, so they can stay as orphans.
- **C3:** the translation roles accept attachments, but the guard compares only typed text. This is a UX and documentation item; confirm on DEVICE.
- **MW2:** `storage prune-sources` followed by a required-baseline apply re-downloads the pruned source. This is a DEVICE confirmation item.
- **MW9:** the MTP catalog in `/etc` is `%config(noreplace)`, so package updates arrive only as `.rpmnew`. Document this, or split it like `models.d`.
- **Licensing:**
  - Jina v5 small is CC BY-NC 4.0; commercial use needs authorization or a qualified Apache-2.0 alternative with a reindex.
  - LFM Open License v1.0 needs review against the deployment.
- **Apertus 1.5 instruct:** GGUF/Vulkan verification deferred (DEC-052).

## Test suite (before v1.0)
- **T1 (rest):** source-string assertions still pin implementation in about 24% of tests. Examples:
  - `test_mc7_mc8_wol_and_firewall_safety`;
  - the restore-users WAL source check;
  - several `test_maintenance.py` schedule checks.

  Convert those that guard a safety property into behaviour tests, and delete the rest.
- **T2:** documentation prose pins (about 42 tests). Keep the structural doc checks and a few safety phrases; drop the wording pins.
- **T3:** separate governance tests (workbench state, handover names, release continuity) from product tests with a marker or module, and keep them in `--preflight`.
- **T4:** fold the review-named modules (`test_review_wip.py`, `test_mc_02005.py`, `test_mw_rt_02005.py`, `test_experiment_model_review.py`, `test_backup_roundtrip_02005.py`, `test_unit_lists_02005.py`) into domain modules.
- **T5.4:** an upgrade-path test for B2, once the B2 fix exists.

## DEVICE checks still open for 0.20.0-5
These are not SOURCE findings. They are the minimum exact-RPM trial list for this release:

1. Upgrade 0.20.0-3 → 0.20.0-5, then rerun `sudo bc250 maintenance setup` and confirm that `owui-backup-documents.timer` is enabled (B2).
2. Run `sudo bc250 maintenance run prune` with `DRY_RUN=1` against the real Open WebUI 0.12.5 Knowledge API. Confirm the `Knowledge protected=` count and that no linked file appears as `WOULD delete`.
3. Run one backup round:
   - check that `/var/backups/bc250-llm-server/.stage` exists and no `.backup-stage.*` remains in the export directories;
   - run the documents backup twice with no change in between; the second run must skip.
4. Pi:
   - pin host keys;
   - install `bc250-pull-backups.timer`;
   - do two pulls and confirm hardlinked snapshots (`du -sh` grows only by new archives);
   - do one pull during the 18:05 backup (in-progress pair skipped).
5. Restore drill: run `restore-config.sh` and `restore-users.sh` on a scratch replacement. The corpus is restored manually.
6. Night power: check WOL wake and the 18:30 deferral while a Pi pull runs. Observe the open-tab behaviour (N8).
7. Model and runtime items carried from DEC-052/053 (MW2, LFM3 task-lane candidate, Gemma 12B QAT): no promotion without DEVICE evidence.

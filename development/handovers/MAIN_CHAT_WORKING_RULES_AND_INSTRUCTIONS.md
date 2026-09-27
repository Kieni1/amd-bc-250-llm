# BC-250 main integration — working rules and operating instructions

## Authority

When facts disagree, use this order:

1. current explicit user instruction;
2. newest supplied source/package and exact installed identity;
3. exact-device evidence from that exact revision;
4. current build/test evidence;
5. current durable handovers/decision records;
6. older logs, patches, chats and community reports.

Never transfer qualification between NVRs automatically.

## Current source

```text
VERSION       0.12.2
RPM Release   0.5
NVR           bc250-llm-server-0.12.2-0.5
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full / TIKA_SERVER_VERSION=4
Governor      0.4.13
Revalidation  v4.6
```

The four source batches are implemented. Source/static success does not qualify device behavior.

## Implemented current contracts

- Advanced: request-scoped `think=true`, current candidate `max_tokens=6144`; the preceding exact-device run proved the same supported OWUI adapter path at 4096 -> Ollama `options.num_predict=4096`, and 0.5 must verify exact 6144 -> `options.num_predict=6144`, samplers `temperature=0.7`, `top_p=0.8`, `top_k=20`, `min_p=0`, `presence_penalty=0`, `repeat_penalty=1`.
- Deep: before either curated or raw Deep starts, evict and verify absence of embedding/task residency; fail/defer if that cannot be proven; use exact bounded `keep_alive=2m`; preserve separate lanes and `OLLAMA_MAX_LOADED_MODELS=1`.
- Qwen3.6 35B is retired from active candidates. Qwen3.8 Unsloth and ISTA IQ3_S are admin/testing-only; ISTA IQ3_XXS is the ordinary-user deployability comparison.
- CU verification compares the configured saved `BC250_WGP_MASKS` profile/layout with live SPI routing when a profile exists. `--` is intentionally unselected, not a fault; `D!` is inconsistent. 40/40 is one valid device profile, not universal health.
- The optional package maintenance key is `/var/lib/bc250-llm-server/secrets/openwebui-admin.key`, directory `0700`, file `0600`, root-owned, atomically created without silent overwrite and verified against OWUI before `CONFIGURED`. Explicit token-file options override it. Token contents never enter logs, support bundles, evidence or handovers.
- Revalidation separates run completion, Infrastructure, Quality, Restoration and Coverage; reasoning-only ceiling exhaustion without a visible answer is `INCOMPLETE` (including the production contract); repetitive/degenerate reasoning remains a quality defect.
- Installer final state is verifier-derived and reports PASS/WARN/FAIL, final reboot state, OWUI readiness/URL, Ollama, CU profile consistency, revalidation state, authenticated maintenance and optional-component state.

## Validation ownership

```text
main integration  focused changed-boundary tests/static/source checks
workstation        Ruff/developer lint
GitHub/Fedora      authoritative full deterministic suite + RPM/SRPM build
BC-250             exact installed browser/model/UMA/CU/migration/restoration acceptance
```

Release/source-package artifacts remain opt-in. A **workbench continuity checkpoint** is the sole exception: after each meaningful completed source batch, create a small source checkpoint ZIP plus SHA-256. The checkpoint must carry its continuity state metadata inside the same archive so the ZIP is self-describing; it is not a release artifact.

## Workbench continuity

Transient `/mnt/data/...` worktrees are scratch space only and are never authoritative. The canonical integration state is, in order, an exact Git commit SHA when available or the newest explicit workbench checkpoint SHA-256.

After each meaningful source batch:

1. run the focused source/static checks owned by main integration;
2. remove caches/build residue;
3. create a `*-workbench-<batch>.zip` checkpoint and record its SHA-256;
4. embed `WORKBENCH-STATE.json` (or Markdown equivalent) in that checkpoint with the predecessor SHA, release/NVR, completed batch, changed files, validation performed and open work; keep this workbench-only metadata out of release/source-package payloads;
5. on the next batch, reconstruct only from that exact checkpoint and verify its SHA before editing;
6. diff against the predecessor and explicitly review deleted tests/guards as well as changed source.

If the newest checkpoint cannot be recovered, do not silently rebuild from an older release archive. Stop the integration batch until the exact checkpoint is restored or the user explicitly authorizes a different base.

Known Ruff regressions that must be avoided even when Ruff is unavailable locally: `F821` undefined names, `RUF100` unused `noqa`, `TRY004` wrong exception type for invalid types, `SIM114` adjacent `if`/`elif` branches with identical bodies, and `SIM117` directly nested `with` contexts. `scripts/validate.py` carries repository-specific guards for these known failures; workstation Ruff remains authoritative.

## Evidence closures / remaining investigation

Closed from exact-device evidence:

- Deep residency architecture is qualified and unchanged: task/embed pre-eviction, `keep_alive=2m`, reuse, expiry and cold reload.
- Genuine LibreOffice DOCX testing attributes `· item` list serialization to Tika 4; heading/table/list content and retrieved facts remain intact, so no package rewrite is justified.
- Repeated single-model and Advanced+Deep title/tag tests persisted both reliably; do not change task topology unless a future release reproduces the old isolated event.

Still evidence-first: BTF/kernel-build warning presentation remains unchanged until harmlessness/correctness impact is established.

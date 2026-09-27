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
RPM Release   0.4
NVR           bc250-llm-server-0.12.2-0.4
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full / TIKA_SERVER_VERSION=4
Governor      0.4.13
Revalidation  v4.6
```

The four source batches are implemented. Source/static success does not qualify device behavior.

## Implemented current contracts

- Advanced: request-scoped `think=true`, `max_tokens=4096` -> effective Ollama `options.num_predict=4096`, samplers `temperature=0.7`, `top_p=0.8`, `top_k=20`, `min_p=0`, `presence_penalty=0`, `repeat_penalty=1`.
- Deep: before either curated or raw Deep starts, evict and verify absence of embedding/task residency; fail/defer if that cannot be proven; use exact bounded `keep_alive=2m`; preserve separate lanes and `OLLAMA_MAX_LOADED_MODELS=1`.
- Qwen3.6 35B is retired from active candidates. Qwen3.8 Unsloth and ISTA IQ3_S are admin/testing-only; ISTA IQ3_XXS is the ordinary-user deployability comparison.
- CU verification compares the configured saved `BC250_WGP_MASKS` profile/layout with live SPI routing when a profile exists. `--` is intentionally unselected, not a fault; `D!` is inconsistent. 40/40 is one valid device profile, not universal health.
- The optional package maintenance key is `/var/lib/bc250-llm-server/secrets/openwebui-admin.key`, directory `0700`, file `0600`, root-owned, atomically created without silent overwrite and verified against OWUI before `CONFIGURED`. Explicit token-file options override it. Token contents never enter logs, support bundles, evidence or handovers.
- Revalidation separates run completion, Infrastructure, Quality, Restoration and Coverage; reasoning-only non-production budget exhaustion is `INCOMPLETE`/review rather than semantic quality failure.
- Installer final state is verifier-derived and reports PASS/WARN/FAIL, final reboot state, OWUI readiness/URL, Ollama, CU profile consistency, revalidation state, authenticated maintenance and optional-component state.

## Validation ownership

```text
main integration  focused changed-boundary tests/static/source checks
workstation        Ruff/developer lint
GitHub/Fedora      authoritative full deterministic suite + RPM/SRPM build
BC-250             exact installed browser/model/UMA/CU/migration/restoration acceptance
```

Do not generate ZIP/RPM/SRPM/tar/release artifacts unless explicitly requested.

## Open investigations

Do not change package defaults yet for:

- Tika 4 bullet-list Markdown until a normal LibreOffice/Word DOCX is tested end-to-end;
- intermittent missing multi-model tags until launch/persistence/overwrite/timing is reproduced;
- BTF/kernel-build warning presentation until harmlessness or correctness impact is established.

# BC-250 release testing handover — 0.13.1-1.3

## Purpose

Qualify the exact RPM after the closed Sidechat 15–19 optimization program. This is a focused release delta, not a new model/runtime tournament.

## Build gate

Record source/workbench SHA, RPM/SRPM NEVRA and hashes. Require:

```text
python3 scripts/validate.py
python3 development/scope.py check
ruff check .  # mandatory external gate; local source removed known default-rule violations without suppressions
ShellCheck/package shell gate
rpmlint -c packaging/rpmlint.toml dist/*.rpm
actual-RPM payload contract
Source0 recursively contains no `.pytest_cache`, `.ruff_cache`, `__pycache__`, `*.pyc` or `*.pyo` developer cache artifacts
```

Target:

```text
bc250-llm-server-0.13.1-1.3.fc44.x86_64
```

## Frozen runtime decisions

Require the installed package to retain:

```text
OLLAMA_CONTEXT_LENGTH=32768
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_PARALLEL=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_MAX_LOADED_MODELS=1
main/task/embedding keep_alive = 20m / 0 / 10m
Deep keep_alive=2m and package pre-eviction
Advanced max_tokens=6144
Translation num_predict=2048
```

q4_0 is rejected. Do not create another q4 acceptance arm.

## RAG promotion gate

Package desired state must be:

```text
Documents model  prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl
Embedding        embed-jina-v5-small-retrieval-q4-k-m
Chunk            1500 / overlap 200
TOP_K            4
Hybrid search    off
Tika             package pin
```

Run bounded direct and Open WebUI RAG smoke. Preserve answer grounding/citations and normal restoration. Do not reopen the model tournament.

## Evaluator/tooling regressions

Require:

- office-draft `4 September 2026`, `4. September 2026` and `04.09.2026` to compare semantically when unambiguous;
- `10 AM` and `10:00` to compare as the same time where a case requests that value;
- numeric acceptance to check the required value rather than selecting a later explanatory number;
- grouped citations to be parsed by member source identity rather than literal complete-bracket substring matching;
- `INV-2026-0441` and `Invoice 2026-0441` to compare as the same unambiguous invoice identifier;
- semantic substitution only when the complete required value is a standalone date/time/invoice token; compound requirements such as `deadline 4 September 2026` must not pass from the date alone;
- clean Advanced/RAG hidden-reasoning exhaustion with empty visible answer => INCOMPLETE/retry when no independent defect exists;
- repetition at the exhausted reasoning budget => quality failure;
- task title/tag success to be based on the persisted result/contract, not mandatory capture of a transient task-model residency sample.

External/reference OWUI qualification tooling is not installed by this RPM. When `bc250_owui_release_qualification_v2.4.1.py` (or its successor) is used for the focused device gate, consume its structured run state/journey verdicts rather than treating only `rc == 0` as success: `--behavior-only` may intentionally finish `COMPLETE_WITH_GAPS` / rc 4. Deep cleanup consumers must accept the journey's multi-resource cleanup fields, and long child execution/finalization must not depend on a fragile stdout pipe that can turn a lost parent consumer into `BrokenPipeError` before cleanup.

## Model-state gate

Required defaults are checked by identity. Additional operator registrations are INFO and remain untouched.

```text
embed-qwen3-0.6b-q8-0 absent       -> OPTIONAL — not installed
cached but unselected              -> OPTIONAL — source cached, not registered
explicitly selected/current        -> CURRENT
selected then broken               -> DRIFT + repair guidance
```

No exact total-registration-count requirement is allowed.

## Readiness gate

Exercise boot/startup timing and distinguish:

```text
nginx listener ready
Open WebUI backend ready
usable front door ready
```

HTTP 502 proves only a listener/proxy state and must not count as usable application readiness. `bc250 verify` should require `/api/version` on the backend and through nginx.

## Benchmark/revalidation gate

Generation benchmark automation must expose explicit non-interactive context/thermal/board-note controls and must not unexpectedly prompt when `--non-interactive` is used.

Canonical benchmark metadata must include starting:

```text
MemAvailable
SwapUsed
memory PSI
Ollama residency by lane
```

Revalidation snapshots/checkpoints must retain memory PSI evidence.

## zram verification

If `/etc/systemd/zram-generator.conf.d/90-bc250-llm-server.conf` exists but no `/dev/zramN` is present in the active swap set, `bc250 verify` must warn. An initialized/configured zram device that is absent from `swapon --show` is not active swap. Also require actual failed systemd unit rows to be parsed rather than inferring zero failures from command exit status. Do not change the qualified 2 GiB zram/disk-swap/swappiness policy in this release.

## Swap lifecycle and firewall verification

Exercise the managed disk-swap failure path with controlled/mocked active-state query and deactivation failures: if active-swap state cannot be determined, or the swap file is active and `swapoff` fails, resize/removal must stop before unlinking/replacing the backing file or removing its configuration. This is lifecycle hardening only; do not change the qualified 16 GiB disk swap, 2 GiB zram or swappiness policy.

For the LAN-boundary verifier, include at least one protected internal port inside a direct numeric range and one protected port supplied by an active custom firewalld service. Both must fail verification. Accepting rich rules with protected ports/services must be treated the same way, and inability to inspect an active zone/service definition must not produce a clean result. Exact HTTP publication remains the intended external service.

## Final restoration

Require normal topology, Open WebUI desired state, CU saved/live consistency, no failed units, package model registrations plus operator additions preserved, expected residency restored, secret scan clean and `rpm -V` clean.

## Stop rule

If the focused delta passes, stop. Do not replay Sidechat 15–19, model selection, structured-output discovery, Agent baseline qualification, MTP/OCR campaigns or broad dependency work.

## 1.2 corrective verifier gates

Require:

- HTTP publication recognized through standard `http`, direct `80/tcp`, a numeric TCP range containing 80, a custom active service containing `80/tcp`, or an accepting rich rule;
- reject/drop-only rules and ranges that do not contain 80 remain not-open;
- active custom-service definition lookup failure is UNVERIFIED, never a clean/open PASS;
- `swapon` query success with no entries is a known-empty active-swap set;
- `swapon` query failure is reported as unavailable/unknown, not `no active swap`;
- destructive resize/removal still refuses mutation on active-state query failure or `swapoff` failure.

## 0.13.1-1.3 focused delta gate

Do not replay Sidechats 15–19. Build qualification should prove Source0 reproducibility across timezone/mode/cache perturbations, Ruff/ShellCheck, actual RPM payload, rpmlint, and the generated-SRPM self-contained rebuild gate. Device qualification should focus on installer wording/state transitions, live SPI-routed CU reporting, bounded TOP_K=4 product smoke, readiness/firewall/swap checks, then one final whole-appliance revalidation and `rpm -V`.

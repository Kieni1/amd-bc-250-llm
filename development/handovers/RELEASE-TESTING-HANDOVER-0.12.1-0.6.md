# BC-250 0.12.1-0.6 focused release testing handover

## Scope

Test the exact installed `bc250-llm-server-0.12.1-0.6` package only after the authoritative RPM/SRPM build succeeds. Reuse the broad runtime/model evidence already established on 0.4/0.5; do not replay whole-appliance qualification unless this focused round exposes a crossed runtime boundary.

Target identity:

```text
VERSION       0.12.1
RPM Release   0.6
NVR           bc250-llm-server-0.12.1-0.6
Ollama        0.34.2
Open WebUI    0.11.3
```

## What changed

0.6 is an application-policy/observability release. It does not change normal/service topology, `OLLAMA_MAX_LOADED_MODELS=1`, Deep `keep_alive=0`, TTM thresholds, production RAG/task/embedding choices or the live 40-CU policy.

Changed boundaries:

1. all models actually registered on normal main `11434` and task `11435` are synchronized into package-managed visible testing records with additive ordinary-user read access;
2. embedding `11437` and exclusive agent `11436` remain outside normal chat selection;
3. stale dynamic cleanup is limited to `bc250_managed=testing-discovery` records from lanes successfully inventoried in the same run;
4. Advanced/Qwen3.5 uses the qualified request policy: `think=false`, temperature `0.7`, `top_p=0.8`, `top_k=20`, `min_p=0`, `presence_penalty=0`, `repeat_penalty=1`;
5. selected experimental Qwen models carry testing/qualification metadata and request defaults without Modelfile `think` parameters or template repacking;
6. DE↔FR translation withholds high-confidence modality/literal-integrity mismatches for review;
7. `bc250-status` reports current `/api/ps` residency and `not checked` reboot recommendation when the optional helper is absent;
8. `bc250-revalidate` is harness v4.5 and reports exact installed NEVRA separately from target version;
9. `bc250-support-bundle` has bounded captures and verifies its checksum/archive before success;
10. authenticated verbose OWUI status reports admin-owned multi-model-chat state when the API exposes it, without changing that permission.

## Focused device acceptance

### A. Package and baseline

Record exact NEVRA, kernel, boot ID, `rpm -V`, Ollama/Open WebUI versions, normal topology, TTM `4194304/4194304`, live CU routing and authenticated verifier. Final package integrity and verifier state must be clean except for an explicitly understood external/environment diagnostic.

### B. Effective ordinary-user selector

Use an ordinary `role=user` account, not only administrator/provider inspection.

Capture actual inventories from:

```text
11434 /api/tags
11435 /api/tags
```

Then refresh the ordinary-user Open WebUI model surface. Acceptance requires:

- every current main/task registration intended for chat testing is selectable;
- six curated Office roles remain present;
- 11436 agent and 11437 embedding models are absent from normal chat selection;
- raw GPT-OSS remains selectable and retains `keep_alive=0`;
- experimental models show useful testing/qualification descriptions/tags where package policy exists;
- an unrelated administrator-created model record/grant survives `bc250-openwebui-setup apply`;
- if practical, temporarily make one provider inventory unavailable during a controlled source/API simulation and prove existing records from that uninspected lane are not removed. Do not disrupt the real appliance merely to force this condition if source coverage already proves it.

If model counts differ, record exact missing/extra IDs. Do not abort the rest of the evidence run solely on the mismatch.

### C. Advanced request-policy propagation

Through the real Open WebUI Advanced role, capture downstream Ollama/request evidence sufficient to prove the effective policy is:

```text
think=false
temperature=0.7
top_p=0.8
top_k=20
min_p=0.0
presence_penalty=0.0
repeat_penalty=1.0
```

Authenticated `bc250-openwebui-setup status --verbose` should render the nested effective values. Do not infer request policy from the Modelfile alone.

### D. Translation integrity

Run short deterministic DE→FR and FR→DE cases covering:

- recommendation: `sollte` / `devrait`;
- obligation: `muss` / `doit`;
- explicit prohibition/negation;
- one date;
- one CHF amount;
- one unique alphanumeric identifier.

Correct translations must pass unchanged. A clearly strengthened/weakened modality or lost protected literal must be withheld with a review message rather than silently returned. This is a safety/integrity guard, not permission for the package to rewrite the translation automatically.

### E. Operator diagnostics

Confirm:

- `bc250-status` shows resident model IDs or `empty` for each active lane;
- absence of optional `needs-restarting` is reported as `Reboot recommendation: not checked`, not unknown/failure;
- `bc250-revalidate status --raw` includes `installed_nevra`, `target_version` and `harness_version=4.5`;
- human revalidation status displays Installed NEVRA separately;
- `bc250-support-bundle` completes mode 0600, its internal SHA256 set verifies after extraction, and its evidence does not contain user prompts/chats/documents/tokens;
- if a harmless test command can be made to exceed a deliberately short `BC250_SUPPORT_CAPTURE_TIMEOUT`, the evidence records `TIMEOUT` and the bundle still finalizes. Do not induce a harmful service hang.

### F. Compare/Deep regression

Do not add a scheduler or disable compare. If multi-model chat is enabled by the administrator, record its effective reported state and run one bounded Advanced + Deep comparison using natural title/tag activity. Confirm no OOM/GPU fault, GPT-OSS unload after completion and final topology/residency restoration. Treat runtime/memory safety and factual-content quality as separate observations.

### G. Final state

Required final state:

```text
normal topology
agent intentionally inactive
Open WebUI ready
failed units = 0
no fresh OOM/AMDGPU/Vulkan critical events
main/task/embedding residency restored to starting state (or explicitly empty if test started empty)
rpm -V clean
authenticated verifier clean
```

## Qwen/template items that are evidence, not 0.6 product changes

Do not repack GGUFs with froggeric v22.5. Existing paired testing found no demonstrated benefit. `think` remains request-level. If standalone llama-server/template qualification is repeated later, capture/reuse the actual Ollama runner Vulkan environment and retain the strict prompt-prefix/history and named-effort-consumption checks in that dedicated harness; they are not new runtime policy in 0.6.

## Acceptance-harness semantics

Record mismatches and continue independent evidence collection. A product mismatch is evidence, not a reason to make later observations disappear. Skip only the unsafe/dependent subtest whose prerequisite is not satisfied. Reserve a nonzero overall harness exit for unsafe final appliance state or mechanical harness failure that invalidates the run.

Return to main integration with separate classifications for `PRODUCT_DEFECT`, `UX_DEFECT`, `ENVIRONMENT`, `EVIDENCE_GAP`, `HARNESS_DEFECT` and clean observations.

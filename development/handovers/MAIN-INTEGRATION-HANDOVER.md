# AMD BC-250 LLM appliance — main integration handover

Release target: `bc250-llm-server-0.13.1-1.0`  
Current handover date: 2026-10-03

## Purpose

This is the primary continuity handover for the main engineering/integration chat.

It records:

- the current source/package architecture;
- what has been fixed and intentionally removed;
- model/product decisions that are closed;
- current validation boundaries;
- remaining exact-device/release work;
- rules for coordinating specialist chats without reopening completed campaigns.

## 1. Authority and evidence boundaries

Current source checkpoint:

```text
bc250-llm-server-0.13.1-1.0 source tree
derived from predecessor workbench:
  amd-bc-250-llm-0.12.2-0.6-workbench-greenfield-clean-final.zip
  SHA-256 399bc99b57e54528a94bfc3fc2a49e1959b8c8bbd767c6b29807b42ce654157c
```

Current source validation:

```text
511/511 deterministic tests PASS module-by-module
development/scope.py check PASS
scripts/validate.py / RPM preflight PASS
bash syntax PASS
Python compileall PASS
JSON parse PASS
make help / payload-contract dry-run PASS
Ruff, ShellCheck, configured rpmlint execution and rpmbuild external in this artifact environment
```

Do not transfer exact-device qualification across source revisions.

The supplied 0.12.2-0.6 RPM build completed successfully with 495/495 tests. An initial 0.7 RPM build then exposed generic rpmlint findings: most were intentional hardened appliance permissions/ownerships, while seven were genuine packaging defects. The current 0.7 source fixes those seven defects and uses a narrow documented rpmlint policy for the intentional findings; no exact post-fix 0.7 RPM/device acceptance exists yet. The final 0.7 delta includes:

- replacement-kernel 40-CU path removed;
- public command surface reduced;
- RAG promoted to product-relevant;
- candidate-screen install footprint removed;
- documentation hierarchy consolidated;
- EuroLLM challenger moved to graveyard.

Therefore the final greenfield RPM needs one final exact build/install/device closure.

## 2. Runtime/service identity

Current pins:

```text
Ollama       0.34.4
Open WebUI   0.11.4
Tika         4.0.0-full
Governor     0.4.13
```

Normal topology:

```text
11434  ollama.service            main/product
11435  ollama-task.service       task
11436  ollama-agent.service      exclusive optional Agent; inactive in normal mode
11437  ollama-embedding.service  embedding
3000   Open WebUI private
80     nginx office-facing HTTP
```

`OLLAMA_MAX_LOADED_MODELS=1` remains important.

Normal mode expects main/task/embedding active and Agent inactive.

## 3. Current curated roles

Production/current roles:

```text
Office - Standard
  -> prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl

Office - Documents / RAG
  -> prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl

Office - Translation DE -> FR
Office - Translation FR -> DE
  -> prod-translate-gemma4-sub-e4b-17s-q4-k-xl

Office - General / Higher Quality
  -> prod-qwen35-9b-unsloth-q6-k

Office - Advanced Structured
  -> same Qwen3.5 base
  -> think=false

Office - Deep Reasoning
  -> prod-gpt-oss20b-ggml-org-mxfp4

Embedding
  -> embed-jina-v5-small-retrieval-q4-k-m

Task
  -> task-lfm25-1.2b-instruct-liquidai-q6-k

Optional Agent
  -> agentic-ornith15-9b-ornith-q5-k-m
```

Current Qwen3.8 large comparison profiles remain non-production experiments/testing-only where retained.

Retired/rejected candidates belong in the retired/graveyard catalog, not ordinary product selection.

## 4. Greenfield command architecture

The 0.12.2 greenfield cleanup intentionally removed the generated per-command compatibility alias forest.

Canonical interface:

```bash
bc250 COMMAND [ARGUMENTS...]
```

Current command groups:

```text
Core:
  bc250 install
  bc250 status
  bc250 verify
  bc250 support-bundle
  bc250 storage
  bc250 reset

Product/model:
  bc250 model
  bc250 rag
  bc250 ocr
  bc250 openwebui-setup
  bc250 ollama-profile

Validation/maintenance:
  bc250 benchmark
  bc250 revalidate
  bc250 maintenance
  bc250 agent-mode

Optional specialist:
  bc250 code
  bc250 code-commit
  bc250 gitea-review
  bc250 compare-mtp
  bc250 fetch-mtp
  bc250 run-mtp
```

Deliberate standalone public commands:

```bash
sudo bc250-cu-live-manager
sudo bc250-40cu status
llm-run-diagnose
```

Do not restore compatibility aliases merely because old documentation or scripts use names such as:

```text
bc250 benchmark
bc250 model
bc250 storage
bc250 revalidate
bc250 openwebui-setup
bc250 agent-mode
bc250 maintenance
```

Update callers to the dispatcher instead.

Private helpers now belong under `/usr/libexec/bc250-llm-server/`.

Examples:

```text
install-ollama
memory-profile
swap-profile
cu-status
status helper
verification helper
```

The public/private split is intentional.

## 5. Live-CU-only architecture

The package no longer carries the archived replacement-AMDGPU module workflow.

Removed product architecture:

```text
fduraibi/duggasco bc250-40cu-unlock source pin
replacement amdgpu patch
module build/prepare
initramfs enable/disable/restore
legacy mask/unmask/live-* command family
kernel-patch license/package assets
```

Current supported workflow:

```bash
sudo bc250-cu-live-manager
sudo bc250-40cu status
```

The live manager configures the actual WGP routing and can save/restore its table at boot.

Internal status/installer/benchmark tooling may use the private CU status helper.

Do not use kernel/RADV numeric CU counters as the sole active-routing authority. The BC-250 can have healthy 40/40 live routing while diagnostic topology counters differ.

One final exact-RPM fresh/upgrade test must prove the live-manager-only installation on the final source.

## 6. Hardware/memory policy

BC-250 memory is shared UMA.

Do not add reported CPU RAM + VRAM + GTT as independent physical pools.

Current policy includes:

```text
zram               2 GiB, priority 100
disk swap          16 GiB, priority 10
vm.swappiness      60

hard safety floor  128 MiB MemAvailable
tight diagnostic   512 MiB
```

TTM settings remain part of the current hardware policy where present in the package.

The 512 MiB boundary is diagnostic/qualification headroom, not an automatic product failure.

## 7. Open WebUI convergence and authentication

The convergence/publication contract remains fail-closed.

Important boundaries:

- Open WebUI service is generated through Quadlet.
- Never `systemctl enable open-webui.service` directly.
- Desired-state convergence and boot-link verification must succeed before nginx publication is considered complete.
- Temporary signin/signup JWTs are convergence bootstrap credentials only.
- Durable package maintenance auth is the verified Open WebUI API key:

```text
/var/lib/bc250-llm-server/secrets/openwebui-admin.key
```

Expected protection:

```text
parent 0700 root:root
file   0600 root:root
content real sk-... Open WebUI API key
```

Do not put credential contents into evidence archives/logs.

## 8. Open WebUI parameter-resolution conclusion

Source-level investigation is closed.

The installed OWUI path already supports the needed translation:

```text
workspace/model params
  -> model_info.params
  -> merge_model_params()
  -> request params override correctly when injected into the same merge path
  -> form_data["params"]
  -> apply_model_params_to_body_ollama()
```

Effective precedence in the investigated path:

```text
request/model params
  >
workspace/model params
  >
global defaults
```

provided the value enters the correct model-parameter merge path.

`custom_params` is unpacked into effective parameters.

Ollama mapping:

```text
root:
  think
  format
  keep_alive

options:
  max_tokens -> num_predict
  temperature
  top_p
  top_k
  min_p
  repeat_penalty
  ...
```

OpenAI-style `response_format` maps separately to Ollama `format`; it does not itself define product thinking policy.

No payload-translation patch is required.

Product policy belongs in explicit request construction / curated presets, not generic payload translation.

## 9. Structured-output findings and final policy

### Advanced

Exact causal/native evidence:

```text
think=false exact-prompt campaign: 30/30
think=true exact-prompt campaign:  27/30
```

Five-case native:

```text
think=false 25/25
think=true  23/25
```

Production OWUI Advanced stress, effectively think=true:

```text
42/50 visible correct
8/50 no-visible failures
```

All eight matched the heavy-reasoning/6144-ceiling pattern.

Real OWUI authoritative nothink diagnostic:

```text
25/25 strict valid structured
0 reasoning
0 budget exhaustion
0 invalid/schema
0 infrastructure failure
```

Conclusion:

```text
Normal Advanced:
  think=true
  max_tokens=6144

Strict Advanced machine-consumed structured:
  explicit "Office - Advanced Structured"
  think=false
```

Do not disable Advanced reasoning globally.

### Standard

Structured investigations localized the failure to formatting/temperature behavior, not a need to disable thinking.

Final confirmation:

```text
exact schema format
temperature=0.0
normal/default thinking

200/200 strict exact
0 fenced
0 semantic mismatch
0 invalid
reasoning present 200/200
```

### Documents

Schema-enforced focused evidence:

```text
25/25 strict PASS
```

Final testing handover updated the policy to align with the robust Standard path:

```text
exact schema format
temperature=0.0
normal/default thinking
```

No larger Documents repetition campaign is required.

### Deep

Focused five-case qualification:

```text
25/25 strict PASS
contract PASS
adapter PASS
ACL PASS
no budget-exhaustion pattern
```

Deep has no explicit think override and remains unchanged.

Deep residency policy remains its separate established contract:

```text
pre-evict competing task/embed lanes
verify absence
keep_alive=2m
verify reuse
verify expiry
cold-reload task/embed
restore normal mode
```

Do not introduce Deep `think=false`.

## 10. Translation conclusion

Current production model remains Translate-Gemma.

Known raw-model defect:

```text
German:
Die Belegungsvorschriften bei Neuvermietungen sollten beachtet werden.

Observed French:
Les règles d'occupation doivent être respectées lors de nouvelles locations.
```

This strengthens recommendation to obligation.

The product guard must fail closed on recommendation/obligation strengthening and related protected modality.

EuroLLM challenger Round 1:

```text
sollten -> devraient anchor     2/2
ordinary office                 6/6
muss nicht -> English output    0/2
```

That regression met the stop rule.

Decision:

```text
keep Translate-Gemma
accept/document raw-model limitation
retain fail-closed product guard
EuroLLM -> graveyard
no Round 2
```

The reported production failure on `ist erforderlich` is likely an evaluator false negative; the cited French wording `est nécessaire` preserves required semantics.

Do not reopen translation model selection merely to improve one anchor.

## 11. RAG is now product-relevant

RAG/Tika is ACTIVE, not frozen.

Canonical product interface:

```bash
bc250 rag ...
```

The legacy public `the former public RAG importer` alias and plan/sync compatibility surface were removed.

The importer engine remains internal because `bc250 rag ingest` uses it.

Current architecture:

```text
Documents answer role:
  prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl

Embedding:
  embed-jina-v5-small-retrieval-q4-k-m

Extraction:
  Tika 4.0.0-full
```

Historical model decision remains useful:

- Gemma E4B is the production RAG answer default.
- The larger Qwen alternative was not promoted for a 16 GiB long-lived RAG role because continuous residency/memory headroom was worse.
- Arbitrary-document product acceptance still deserves final exact-source smoke on the final RPM.

RAG qualification must cover the product command path, extraction, embedding lane, retrieval, answer behavior, cleanup and restoration.

Do not revive the old broad RAG tournament.

## 12. Agent is optional add-on coverage

The package-default Agent is not a mandatory install baseline.

Revalidation semantics:

```text
Agent not installed:
  SKIPPED / PARTIAL / optional coverage unavailable
  core revalidation can still pass

Agent installed but broken:
  real staged runtime/topology/infrastructure failure
```

Do not collapse missing optional model state into generic failure.

## 13. Benchmark improvements integrated

Generation benchmark reporting was improved based on the multi-device campaign.

Current useful summary data includes:

- cold request wall time;
- actual `cold_load_s`;
- decode mean/CV;
- prefill;
- selected deep-context lanes;
- 4K/16K target vs actual prompt tokens;
- thermal window count/mean/min/max/first/last/drift;
- selected-lane completeness;
- resident size;
- MemAvailable/swap evidence;
- runtime/GPU journal diagnostics.

No synthetic board score or package-specific A/B/C board ranking was introduced.

Historical hardware campaign conclusion:

- all three tested devices were healthy 40/40;
- one board was modestly faster, especially prefill;
- no product/runtime defect was found;
- board ranking is not package policy.

Do not reopen the campaign simply to increase the denominator.

## 14. Documentation cleanup

The installed package documentation is now operator-oriented instead of mirroring repository paths.

Canonical docs:

```text
README / TLDR / MODELS / CHANGELOG
INSTALLATION
HARDWARE
OPERATIONS
OPENWEBUI
OLLAMA
RAG
QUALITY-CHECKS
BENCHMARKING
SECURITY
HTTPS
FILESTRUCTURE
UNINSTALL
```

Merged/removed standalone docs include:

```text
COMMANDS
MEMORY
SENSORS
GOVERNOR
DEPLOYMENT
MAINTENANCE
MAINTENANCE-CONTRACT
openwebui-settings
benchmark README mirror
kernel-cmdline standalone
GFX1013-COMPUTE-QUEUES
packaging README from installed docs
```

Unique operational content was folded into the canonical guides rather than discarded.

The obsolete GFX1013 compute-queue verifier was removed with the document.

## 15. Installed filesystem design

The top-level Linux/FHS split is intentionally retained:

```text
/usr/bin/                       small public CLI
/usr/libexec/bc250-llm-server/  private implementation
/usr/share/bc250-llm-server/    immutable product assets
/usr/share/doc/bc250-llm-server docs
/etc/bc250-llm-server/          operator configuration
/var/lib/bc250-llm-server/      persistent package state/models/secrets
/var/cache/bc250-llm-server/    disposable cache
/var/backups/bc250-llm-server/  package backups
/var/lib/open-webui/            Open WebUI-owned state
/srv/bc250-documents/           operator document area
```

The cleanup target was what lives inside those locations, not replacing normal Linux hierarchy with a custom tree.

## 16. Candidate screens and engineering tooling

Engineering model-selection/candidate screens remain in source where useful.

They are no longer installed onto every production appliance.

Production validation interfaces are:

```text
bc250 verify
bc250 revalidate
bc250 benchmark
current package-specific focused harness when justified
```

Do not treat source-only candidate matrices as normal operator commands.

## 17. Development scope

Current active:

```text
installer-convergence
openwebui-product
benchmark-revalidation
model-catalog-current
rag-tika
```

Boundary-active:

```text
runtime-cu-memory
verification-diagnostics
packaging-source
global-docs-coordination
uninstall
```

Frozen:

```text
maintenance-companion
mtp
coding-agent
ocr
```

Archive-only:

```text
historical-development
quality-history
graveyard-models
```

A greenfield change may deliberately remove compatibility surfaces, but it must update the scope contract/tests/docs rather than bypassing them.

## 18. What is closed and should not be replayed

Do not rerun without a new dependency:

- Advanced think A/B campaigns;
- Standard prompt/schema/four-arm/think/temperature campaigns;
- Standard 200-request confirmation;
- Deep structured baseline;
- EuroLLM translation challenger;
- broad translation model tournament;
- multi-device board ranking;
- Tika bullet-format investigation;
- title/tag persistence investigation;
- old Qwen3.6 35B work;
- obsolete replacement-AMDGPU 40-CU path;
- broad RAG model tournament;
- old MTP broad campaign;
- historical uninstall/power campaigns unless a current boundary changed.

Preserve their conclusions; do not preserve their obsolete active instructions.

## 18A. 0.12.2-0.7 RPM polish and debloat

The 0.7 release is a packaging/UX cleanup over the greenfield 0.6 source.

Integrated changes:

- project and governor license files install under distinct basenames, eliminating the duplicate-license RPM warning;
- the redundant explicit Ollama sysusers group declaration is removed; the user entry remains the single group/user authority;
- `make rpm` now validates the actual built RPM payload, not only source intent;
- CI installs and runs `rpmlint` after the RPM build in addition to Ruff and ShellCheck, using `packaging/rpmlint.toml` to filter only documented appliance policy/known false positives;
- the first rpmlint run's genuine defects are fixed: the tmpfiles-managed RAG root is a ghost directory in the file list, prepared source archives normalize to 0644, the internal RAG importer has no executable shebang, spec comments avoid macro expansion, and the package description stays within rpmlint line limits;
- the actual-RPM contract requires the canonical dispatcher, deliberate standalone CU tools, private Ollama installer helper, product RAG documentation and both license files;
- the payload contract rejects regenerated per-route aliases, replacement-module assets, installed candidate-screen trees, stale installed-doc source mirrors and active EuroLLM payloads;
- model-manager migration-hint code and stale command grammar were removed rather than retained as compatibility scaffolding;
- active scripts/tests/current docs use only the canonical dispatcher grammar;
- help text was shortened and rewritten around user tasks rather than implementation internals.

The live-manager upstream licensing situation is intentionally unchanged; do not alter it as part of this release.


## 18B. 0.12.2-0.8 exact-device UX/reporting corrections

Exact 0.12.2-0.7 fresh installation proved the functional architecture: 53/53 core verification, Open WebUI convergence/authentication, 40/40 live CU routing with saved-profile reboot restoration, Infrastructure/Restoration PASS in revalidation, and PARTIAL coverage solely because the optional Agent add-on was absent. The same run reproduced the known raw Translate-Gemma recommendation-strengthening defect and demonstrated that the Open WebUI outlet correctly withheld it.

0.8 fixes the presentation around those successful behaviors rather than changing the qualified runtime/model policy. Revalidation v4.7 keeps run completion independent from coverage/diagnostics; OWUI translation records raw model quality separately from delivered product integrity; installer/verifier CU terminology is reduced to live routing, saved boot profile and boot-restore service; normal Agent status is phrased as an inactive optional lane; completion guidance points to management/status rather than repeat initialization. A dependency audit changes only `git` to `git-core`; Mesa/Vulkan, UMR, Poppler and Hugging Face remain because active product paths consume them.

The active verifier no longer carries the pre-greenfield patched-AMDGPU marker warning. Historical source records may describe that architecture, but current runtime code and installed docs do not support it.

## 19. Remaining release work

High-value next sequence:

1. build exact final 0.13.1-1.0 RPM/SRPM in the normal Fedora/GitHub environment;
2. fresh-install or deliberately upgrade that exact RPM on the BC-250;
3. verify the canonical command surface and absence of removed aliases/assets;
4. configure/verify 40/40 with the live-manager-only path and prove reboot restoration;
5. verify installed documentation/layout;
6. run `bc250 verify`;
7. run `bc250 revalidate start`;
8. accept Agent PARTIAL coverage if the optional add-on is absent;
9. smoke product RAG/Tika/embed;
10. verify Open WebUI convergence and curated presets;
11. run focused structured-output product-path regression if the final request-construction path changed;
12. final normal-topology/restoration check;
13. freeze/tag only after exact installed-RPM evidence is clean.

## 20. Main-chat decision rule

Do not create more work merely because a topic has history.

Ask:

```text
Did final source change the behavior?
Does exact device evidence need renewal?
Is this a current product surface?
Is there an unresolved release decision?
```

If all are no, preserve the conclusion and move on.

## 18C. 0.13.1-1.0 release hygiene

Exact 0.12.2-0.8 is now the qualified device baseline. The pre-release investigation found no product failure and two implementation issues: package Python imports could create unowned bytecode under immutable `/usr`, and intentionally unselected optional models were mislabeled `MISSING`/`DRIFT` and given repair advice. A follow-up review clarified that source-graveyard membership must remain archive metadata only, not a runtime/Open WebUI state signal.

0.13.1-1.0 fixes those findings without changing runtime/model/CU/RAG architecture. The canonical dispatcher disables Python bytecode writes, guided convergence removes stale package-tree bytecode in bounded BC-250 roots, and optional model status now distinguishes OPTIONAL from genuine DRIFT. Graveyard Modelfiles stay outside active discovery/package installation; if an operator manually registers a historical model, normal Open WebUI testing-policy visibility applies. Explicit `purge-retired` cleanup remains available.

The release test is a narrow 0.8 -> 0.13.1 upgrade/layout/model-state delta. Do not replay the full 0.8 qualification unless that delta exposes a regression.

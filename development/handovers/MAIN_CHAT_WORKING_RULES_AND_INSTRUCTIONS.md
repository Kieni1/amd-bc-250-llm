# BC-250 main integration — working rules and operating instructions

Current release target: `bc250-llm-server-0.13.1-1.0`

These rules are intentionally currentized for the greenfield-clean package.

## 1. Authority

Use:

```text
current explicit user instruction
  >
newest source/workbench archive or Git commit
  >
exact installed-device evidence for that exact revision
  >
current validation/build evidence
  >
current handovers
  >
older logs/chats/history
```

Do not let an old handover reintroduce removed compatibility interfaces.

## 2. Greenfield is a product rule

This package does not need to preserve obsolete command/API surfaces merely because older releases exposed them.

Compatibility has to justify its maintenance cost.

Current examples of deliberate removals:

- public per-command `bc250-*` alias forest;
- legacy `the former public RAG importer`;
- old RAG plan/sync compatibility commands;
- replacement-AMDGPU 40-CU module/patch workflow;
- trivial model setup wrappers;
- installed engineering candidate-screen tree;
- standalone temperature and LAN wrappers;
- redundant uninstall/reset aliases;
- duplicate installed documentation hierarchy.

If an old caller breaks, first ask whether the caller should be updated to the canonical interface rather than restoring the alias.

## 3. Canonical public/private boundary

Public:

```text
bc250 COMMAND
bc250-cu-live-manager
bc250-40cu status
llm-run-diagnose
```

Private implementation:

```text
/usr/libexec/bc250-llm-server/
```

Do not expose private helpers simply to make source code easier to call.

Source/runtime code that needs a private helper should call the package-owned libexec path or use its own internal resolution mechanism.

## 4. RAG is product-relevant

RAG/Tika is active scope.

Do not treat it as an optional historical experiment.

Canonical user path:

```text
bc250 rag
```

Retain:

- extraction;
- ingestion;
- embedding;
- retrieval;
- answer generation;
- cleanup/restoration;
- product docs;
- benchmark/revalidation coverage appropriate to the product.

Do not restore the old public importer alias.

## 5. Structured output is role-specific

Do not create one global structured policy.

Current decision:

```text
Standard:
  schema format + temperature 0.0 + normal thinking

Documents:
  schema format + temperature 0.0 + normal thinking

Advanced Structured:
  explicit preset + think=false

Advanced normal:
  think=true

Deep:
  unchanged
```

Do not implement prompt-text heuristics such as `"return JSON" -> think=false`.

## 6. OWUI payload layer is not the policy layer

OWUI already correctly supports the effective parameter types needed by the product.

Do not patch generic `payload.py` to encode BC-250 role policy.

Correctly placed request/model params can override workspace baseline in the investigated merge path.

Product policy should be explicit in the product request/preset construction.

## 7. Translation is closed unless new product evidence appears

Keep Translate-Gemma.

Keep the fail-closed modality guard.

Document the known raw-model `sollten -> doivent` limitation.

EuroLLM Round 1 met the stop criterion because `muss nicht` reproducibly switched to English.

Do not run Round 2.

Do not promote the EuroLLM model.

## 8. Agent is optional

Missing Agent:

```text
coverage unavailable / skipped / partial
```

not:

```text
core infrastructure failure
```

If installed, it must still work correctly.

## 9. CU normal workflow is only two public actions

Configure:

```bash
sudo bc250-cu-live-manager
```

Verify:

```bash
sudo bc250-40cu status
```

The old patched-module architecture is removed.

Do not restore `prepare`, `enable`, `disable`, `restore`, `mask`, `unmask`, `live-*` or module patch packaging unless a new hardware requirement justifies it.

## 10. Documentation has canonical topic homes

Do not re-fragment the installed docs.

Use:

```text
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

Repository-only packaging/development documentation should stay repository-only.

## 11. Scope first

Before broad source work:

```bash
python3 development/scope.py map <changed paths>
python3 development/scope.py check
```

Frozen/archived trees are not routine reading material.

If a greenfield cleanup intentionally crosses a frozen boundary, explicitly thaw/rebaseline it; do not silently modify the hash just to get green output.

## 12. Existing code/harness first

Before creating a new tester:

1. inspect the current package implementation;
2. inspect the existing authoritative harness/pattern;
3. determine whether the requested question is already answered;
4. extend proven auth/evidence/cleanup/archive behavior where possible;
5. write a new harness only when there is a demonstrated gap.

Do not create another HTTP client merely because writing one is easy.

## 13. Evidence taxonomy

Keep these separate:

```text
infrastructure/API
routing/parameter propagation
model behavior
product policy
harness/evaluator defect
operator/environment state
```

A model-quality failure does not automatically mean runtime failure.

A harness failure does not automatically mean product failure.

## 14. Installed evidence vs source evidence

Never say exact installed behavior is proved by source tests.

Never say source semantics are proved merely because one installed run passed.

Record exact NVR/source revision with real-device evidence.

## 15. Model-output failures should normally be evidence

For qualification runners:

```text
semantic mismatch
invalid JSON
budget exhaustion
format failure
wrong language
```

should normally be recorded as test results.

They should not kill the whole harness unless the test explicitly defines the condition as infrastructure/safety failure.

Harness/config/safety/cleanup/archive failures remain non-zero.

## 16. Preserve raw evidence

For meaningful runtime requests retain, where safe:

- timestamp;
- host/package/model/preset;
- request path;
- effective params;
- response status;
- raw response or safe raw stream;
- parsed answer/reasoning;
- usage/tokens;
- timing;
- routing/residency;
- resource telemetry;
- classification;
- cleanup state.

A later evaluator correction should be possible without rerunning the model.

## 17. Secret hygiene

Never include:

- Open WebUI admin key;
- user tokens;
- passwords;
- private environment secrets

in evidence archives.

Use exact-secret scans where the harness already supports them.

The durable Open WebUI key belongs at:

```text
/var/lib/bc250-llm-server/secrets/openwebui-admin.key
```

## 18. User artifact preferences

When the user asks for code/files:

- prefer a single directly downloadable file when one file is sufficient;
- if a change necessarily touches secondary tests/docs, provide all necessary changed files;
- do not add unrelated files;
- for a workbench/release/handover refresh, return one coherent ZIP;
- do not create RPM/ZIP/release bundles unless explicitly requested.

When the user asks for Git commits:

- return only `git commit ...` commands if requested;
- prefer fine-grained commits over broad commits;
- include functional change with its directly related tests.

When the user asks to review a script and says only return a fixed version if necessary:

- thoroughly check it;
- return a corrected file only if a functional/reliability issue exists;
- otherwise say it is okay.

## 19. No background promises

Do the work in the current response/tool execution.

Do not tell the user to wait for background work.

For a large task, provide concise progress updates while working.

## 20. Build/validation ownership

Typical ownership:

```text
Fedora/GitHub build environment:
  RPM/SRPM/package build with pinned upstream sources

Developer workstation:
  Ruff and local developer tooling

BC-250:
  hardware/CU
  services
  Ollama/models
  Open WebUI
  Tika/RAG
  exact runtime qualification
```

If a tool/environment is unavailable, state that boundary rather than claiming it passed.

## 21. Current external lint rule

Ruff remains a workstation/CI gate when unavailable in the artifact execution environment.

Known lessons include:

```text
F507 quote/% formatting mistakes
UP031 stale %-format patterns
F821 undefined names
RUF100 stale noqa
TRY004 wrong exception class
SIM117 nested with
I001 import ordering
SIM114 duplicate branches
FURB188/FURB192 modernization issues
```

Do not knowingly hand back a file with an obvious lint/syntax failure.

## 22. Release closure rule

After source changes that alter installed payload, public CLI, package sources or device behavior:

- re-run deterministic/source/package gates;
- rebuild the exact RPM;
- install that exact RPM;
- repeat only the device gates affected by the change plus final whole-appliance verification/revalidation.

Do not replay historical model campaigns unrelated to the change.

## 23. Current next main-chat objective

The source design is largely settled.

The next main-chat objective is exact final-RPM closure, not more model discovery.

Focus on:

```text
build
install/upgrade
public/private CLI
live-CU-only fresh behavior
OWUI convergence
RAG product smoke
structured policy regression where final request construction changed
revalidation
final freeze/tag
```

## 24. 0.12.2-0.7 packaging/UX rule

The 0.7 release intentionally turns the greenfield interface into a build-time contract. Do not add compatibility aliases back to satisfy an old caller. Update the caller, keep private helpers under libexec, and make actual RPM payload checks prove the installed surface. CI also owns configured `rpmlint` after build. Use the repo-local filter only for documented appliance policy/known false positives; fix new unfiltered findings instead of broadening the filter casually. The no-license-file state of the pinned live CU manager is a consciously unchanged project constraint for this release.

## 25. 0.12.2-0.8 result-semantics rule

Do not conflate execution completion, optional coverage, diagnostics, model quality and product safety controls. A six-phase revalidation that finishes normally is `completed` even when optional Agent coverage is PARTIAL. A raw translation can remain a model quality failure while the finalized Open WebUI product path passes because the integrity outlet detected and withheld unsafe output. Report both layers explicitly. Current CU UX names only live routing, saved boot profile and boot-restore service; do not revive performance-profile or patched-module terminology.

## 26. 0.13.1 release hygiene rule

Treat exact 0.12.2-0.8 as the qualified predecessor. For 0.13.1, keep `/usr` immutable during normal runtime, treat intentionally unselected optional models as OPTIONAL rather than broken, preserve DRIFT for selected models whose desired runtime state is unmet, and treat source-graveyard membership as archive metadata rather than runtime state. A historical model manually registered by an operator follows normal Open WebUI testing-policy visibility; cleanup remains explicit through `bc250 model purge-retired`. Do not broaden the release into model/CU/RAG/dependency discovery.

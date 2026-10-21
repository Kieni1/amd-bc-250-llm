# Exact-RPM device qualification baseline — 0.14.1-1.4

## Purpose and artifact binding

This file consolidates the accepted device evidence collected during Blocks 1–3 of the `0.14.1-1.4` campaign. It is retained as a regression baseline for 1.5 and later releases. It must **not** be used to claim that changed RPM bytes are device-validated.

Exact tested artifact:

```text
NEVRA:   bc250-llm-server-0:0.14.1-1.4.fc44.x86_64
SHA-256: 87e02e310023e6c9af22e30a92ad38ee8e69ebe9ed11f41019fd926663ae9525
Fedora:  44
Kernel observed after primary reboot: 7.2.11-200.fc44.x86_64
Ollama:  0.40.6
Open WebUI: 0.12.3
Tika:    4.1.0
```

The testing notes did not independently contain every GitHub workflow/source/SRPM identifier. BUILD provenance remains in the canonical release records. DEVICE evidence here is bound to the RPM hash above.

## Block 1 — expected primary-reboot checkpoint

Fresh-state installation succeeded with no prior BC-250/Open WebUI persistent state. Immediate `rpm -V` was clean and no failed systemd units were present.

`sudo bc250 install` returned the designed primary-reboot code `10`. The installer:

- expanded the root LV/filesystem from the small Fedora default to available VG capacity;
- converged the Fedora update;
- downloaded package-qualified Ollama 0.40.6 and verified its SHA-256;
- installed the package-owned runtime topology;
- wrote `ttm.pages_limit=4194304 ttm.page_pool_size=4194304` to all recorded boot entries;
- correctly kept Open WebUI/Tika held before the required reboot/migration convergence.

The board was still at factory 24/40 live routing before the explicit supported CU step, as intended.

Classification: **EXPECTED PRIMARY-REBOOT CHECKPOINT**, not a failure.

### Block 1 UX finding

At the intentional pre-reboot checkpoint, status could report:

```text
Overall: HEALTHY WITH WARNINGS — package runtime identity mismatch/unavailable
```

while Open WebUI/Tika were deliberately held. The identity check was correct but the presentation did not distinguish intentional setup incompleteness. This finding is corrected in the 1.5 source candidate through explicit convergence/publication state; the strict mismatch check remains.

## Block 2 — primary reboot, 40-CU routing and installer convergence

A real reboot occurred and the reviewed TTM arguments were active.

Using the package-supported live manager path, the already-proven board profile was enabled and saved:

```text
Live SPI-routed CUs: 40/40
Saved boot profile:  0x1f,0x1f,0x1f,0x1f
Routing profile match: exact
Boot restore service: enabled
Problem cells: 0
```

This is device evidence for configuration/persistence on this board, not a new broad 40-CU stability campaign.

After reboot, `sudo bc250 install` returned `0` and converged without source-tree intervention:

```text
61 ok / 0 warn / 0 fail / 0 skipped
Core installation: COMPLETE
Core verification: PASS
Open WebUI: WEB INTERFACE READY
Open WebUI package baseline: APPLIED + VERIFIED
Authenticated verification: PASS
BC-250 configuration reboot: NO
```

Core state after convergence:

```text
bc250 status: HEALTHY
bc250 health: PASS
bc250 verify: 61 ok / 0 warn / 0 fail / 0 skipped
rpm -V: clean
failed systemd units: none
```

Normal topology matched the package contract: main `:11434`, task `:11435`, embedding `:11437`, agent `:11436` intentionally inactive in normal mode, Open WebUI loopback `:3000`, nginx active and Tika private.

Runtime identities matched exact pins. The protected Open WebUI maintenance key existed at the package path with root ownership/mode `0600` inside a root `0700` secrets directory; no secret content was collected.

### Block 2 confirmed package UX/parser finding

During pre-reconciliation, the installer could print:

```text
Ollama desired:  0.40.6
Ollama observed: instance
0.40.6
```

The parser accepted the trailing field of more than one stdout line from `ollama --version`. Runtime convergence itself was correct. The 1.5 source candidate fixes this by extracting one normalized semantic version token and has a deterministic multiline regression fixture.

### Harness lesson: thinking budget

The original visible-answer smoke allocated `num_predict=48` to a thinking-capable Gemma request without disabling thinking. Hidden reasoning consumed the entire budget and the visible response was empty with `done_reason=length`. Raw runtime/load/generation succeeded.

Classification: **HARNESS/INCOMPLETE**, not product failure. Use an adequate budget or explicit `think=false` when visible output is the contract.

### Harness lesson: `/api/show` ordering

Across supported Ollama restart, the same `parameters` lines/values were preserved but their textual order changed. Comparing the full serialized field byte-for-byte produced a false stop.

Correct contract: compare non-empty parameter lines semantically/order-insensitively while preserving exact values and duplicate lines; keep all other semantic fields authoritative.

## Block 2 resume — accepted

With corrected harness semantics:

- main/task/embedding Ollama 0.40.6 topology: PASS;
- local-GGUF registration uniqueness across supported main restart: PASS;
- `/api/show` semantic contract across restart: PASS;
- visible default-thinking answer with adequate budget: PASS before/after restart;
- explicit `think=false` control: PASS before/after restart;
- task generation / embedding separation: PASS;
- agent lane intentionally unavailable in normal mode: PASS;
- authenticated Open WebUI package desired state: PASS;
- supported re-apply/idempotence: PASS;
- reviewed local-first policy: PASS;
- package-owned Open WebUI RAG three-turn grounding/citation/no-archive-leak smoke: 3/3 PASS;
- final status HEALTHY, health PASS, verify 61/0/0/0, `rpm -V` clean;
- 40/40 exact routing profile retained;
- Open WebUI 0.12.3 and Tika 4.1.0 identities matched.

## Block 3 — product qualification milestone

Block 3 found **no product defect**.

### Managed RAG lifecycle

PASS for:

- v1 baseline ingest convergence;
- v2 modified-state recognition;
- replacement upload before stale-copy cleanup;
- one-copy convergence;
- updated retrieval with source metadata/citation;
- unsupported/absent information not invented;
- local supersede without `--prune` preserving the remote derived copy;
- explicit `--prune` removing stale remote state;
- idempotent second prune;
- temporary Knowledge-base cleanup;
- isolated local test-root cleanup.

Earlier apparent superseded-count/root-path failures were harness issues; final source-backed expectations matched `rag.py`.

### Package-owned Open WebUI RAG benchmark

```text
bc250 benchmark owui-rag bc250-office-documents
infrastructure PASS
quality PASS
3/3 qualification cases PASS
0 incomplete
0 infrastructure failures
```

### Canonical DE↔FR translation benchmark

```text
bc250 benchmark owui-translation
infrastructure PASS
quality PASS
12/12 qualification cases PASS
0 incomplete
0 infrastructure failures
```

One DE→FR recommendation-modality case produced a raw model strengthening (`sollte` → `doit`). The product integrity guard withheld the unsafe translation and gave actionable review/retry guidance. This is a successful safety/UX outcome, not a translation failure.

### Production use-case benchmark

```text
bc250 benchmark usecase
6/6 PASS
Standard E2B:       2/2
Documents E4B:      1/1
Translation E4B:    1/1
Advanced Qwen 9B:   1/1
Deep GPT-OSS 20B:   1/1
```

### Advanced 6144 forwarding

Marker-correlated real Open WebUI → Ollama traffic proved:

```text
package Advanced preset max_tokens=6144
→ outbound Ollama options.num_predict=6144
```

This is direct device evidence, not source/adapter inference.

### Final Block 3 coherence

PASS:

- 40/40 live routed CUs, zero problem cells, exact saved/live profile;
- `rpm -V` clean;
- status HEALTHY;
- health PASS with zero warnings/failures;
- verify 61/0/0/0;
- Open WebUI/Tika runtime identities match package pins;
- normal main/task/embedding topology healthy;
- agent intentionally inactive;
- required services active;
- no OOM kill observed;
- final MemAvailable approximately 4.3 GiB.

## Boundary left open after Block 3

The campaign intentionally had not yet completed the final reboot-persistence / broader ordinary-user Open WebUI boundary. Planned coverage was:

1. record pre-reboot boot ID;
2. reboot and prove boot ID changed;
3. prove exact RPM hash, TTM args and 40/40 saved/live routing persist;
4. ordinary-user ACL/visibility;
5. uploaded-document RAG UX;
6. synthetic Tika DOCX path;
7. Advanced reasoning/structured/history paths;
8. Deep reasoning/residency sequence;
9. background task lane;
10. multi-model path;
11. cross-preset office-email UX comparison.

Package-owned RAG 3/3, canonical translation 12/12 and raw 6144 capture should not be replayed solely for duplication because they are already device-proven on the exact 1.4 hash.

## Evidence use for 1.5

The 1.4 campaign establishes a strong regression baseline for unchanged architecture/runtime surfaces and directly motivated the two 1.5 UX fixes. It does **not** transfer DEVICE-VALIDATED state to `0.14.1-1.5`.

For 1.5:

- build/select exact new GitHub artifacts;
- verify the two changed UX/parser surfaces;
- verify optional challenger catalog boundaries;
- run bounded core/RAG/runtime regression;
- complete real reboot persistence and the ordinary-user boundary;
- only then consider 1.5 DEVICE-VALIDATED/ACCEPTED.

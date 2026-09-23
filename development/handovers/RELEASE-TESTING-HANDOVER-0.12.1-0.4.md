# BC-250 0.12.1-0.4 non-RAG release testing handover

## Scope

Test only source boundaries changed since the source-qualified 0.12.1-0.3 candidate, plus a compact exact-installed appliance acceptance. Broad model tournaments, backup/reboot campaigns, translation qualification, MTP campaigns and 40-CU redesign are not release gates unless a changed boundary fails.

## Candidate

```text
VERSION       0.12.1
RPM Release   0.4
NVR target    bc250-llm-server-0.12.1-0.4
```

0.4 adds: exact Ollama 0.34.2 payload packaging, RAG lifecycle tooling, RAG marker normalization, IOMMU diagnostic correction, TTM conflict hints, and removal of obsolete historical kernel-release warning lists.

Production Open WebUI 0.11.3, Jina embedding, task model, production role IDs, Deep `keep_alive=0`, governor settings, TTM 4194304/4194304 and existing 40-CU production path are intentionally unchanged.

## Ollama 0.34.2 package acceptance

0.34.2 already has a separate clean-boot exact-device runtime qualification against 0.34.0. This release packages that accepted runtime; do not rerun the entire performance campaign merely to prove packaging.

Package metadata must resolve to:

```text
version: 0.34.2
asset:   ollama-linux-amd64.tar.zst
URL:     https://github.com/ollama/ollama/releases/download/v0.34.2/ollama-linux-amd64.tar.zst
SHA256:  e155b83589986d2c581fdbf1381ea3ebdb16549883679cd5a0627f7cdc05b12b
```

The helper must download/verify the exact payload and must not run upstream `install.sh`.

BC-250 systemd ownership remains authoritative. Verify:

```text
/usr/lib/systemd/system/ollama.service
/usr/lib/systemd/system/ollama-task.service
/usr/lib/systemd/system/ollama-embedding.service
/usr/lib/systemd/system/ollama-agent.service
```

A recognizable stale upstream-generated `/etc/systemd/system/ollama.service` may be cleaned up. A modified/custom override must be refused, not overwritten.

After package convergence in normal mode, require:

```text
127.0.0.1:11434 /api/version -> 0.34.2
127.0.0.1:11435 /api/version -> 0.34.2
127.0.0.1:11437 /api/version -> 0.34.2
11436 inactive intentionally
```

Compact runtime smoke:

1. one Standard generation;
2. one Deep generation;
3. confirm GPT-OSS unload after Deep;
4. immediately run title/tag task generation;
5. one Jina embedding probe, dimension/finite/semantic ordering;
6. one Documents/RAG marker probe (the RAG specialist may provide this evidence);
7. inspect current-boot kernel/OOM/AMDGPU/Vulkan errors;
8. finish with empty unintended residency and normal topology.

No source change should depend on exact `/api/tags` capability-array serialization or `/api/show` generated Modelfile/parameter text as immutable model identity. Model/source digests identify the resolved current artifact; moving `latest`/`main` catalog sources remain refreshable by explicit `bc250-model refresh`.

## Kernel/IOMMU diagnostics

Historical release-number warning ranges are intentionally removed. The product follows the Fedora-supported current kernel.

Do not interpret that as removal of state-based compatibility checks: matching kernel build tree, AMDGPU vermagic, optional prepared 40-CU module state and live routing remain valid operational diagnostics.

IOMMU is not required by the qualified LLM baseline. With no forced IOMMU, verifier should report the baseline cleanly. If `amd_iommu=on` is deliberately present, it should be informational/outside-baseline rather than claiming the BC-250 hardware is categorically broken. Newer BC-250 research demonstrates a functioning BIOS SVM+IOMMU/IVRS configuration, but that configuration is not promoted by this package.

Reference: https://github.com/lorek123/bc250-notes

## TTM diagnostics

Required profile remains:

```text
ttm.pages_limit=4194304
ttm.page_pool_size=4194304
```

Healthy state should remain unchanged. In a controlled temporary diagnostic case where the live value differs, verifier should point the operator toward likely `/etc/tmpfiles.d`, `/usr/lib/tmpfiles.d`, `/etc/modprobe.d` or bootloader/local-administration conflicts without creating a new configuration framework.

Restore the reviewed profile before final verification.

## Kernel warning removal

Search installed/current operator output for historical kernel-version blacklist warnings. None should remain. Exact version strings in historical changelog/evidence are not a defect; only current policy/diagnostic warnings are in scope.

## 40-CU boundary

0.4 does **not** remove the existing prepared-module path. Current upstream live-manager documentation says its UMR live dispatch workflow needs no kernel patch, which justifies a later stock-AMDGPU/live-manager-only A/B, not an untested release change.

Reference: https://github.com/WinnieLV/bc250-cu-live-manager

During ordinary 0.4 acceptance, only verify the already-supported CU state reconstructs/operates as expected. Do not conduct the simplification A/B unless explicitly assigned as a separate experiment.

## Model refresh semantics

The model manager already permits moving revisions such as `latest` and `main`. The stored SHA/digest is the identity/integrity record of the artifact currently resolved and installed; it is not a permanent prohibition on adopting a newer upstream GGUF. An explicit `status --online`/`refresh` can resolve the newer artifact and then record its new digest/provenance.

Do not refresh Jina/task/translation or other qualified special-purpose artifacts merely as a side effect of 0.4 testing. Model refresh remains an explicit separate decision because embedding changes can imply reindexing and product models can require quality requalification.

## Source/build ownership

```text
main integration       focused changed-source checks only
workstation             Ruff
GitHub/Fedora           full deterministic suite + RPM/SRPM/repository build
BC-250                   exact-installed runtime/device acceptance
RAG specialist           dedicated bc250-rag lifecycle/product acceptance
```

Development handovers/patch notes are engineering memory under `development/` and must not become release-test dependencies.

## Final expected state

With an OWUI API token and otherwise healthy appliance, target the normal authenticated verifier clean state. Record exact counts rather than assuming them if the number of checks changes legitimately.

Expected qualitative state:

```text
package integrity       clean
normal topology         main/task/embedding active; agent intentionally inactive
Ollama lanes            all 0.34.2
Open WebUI               ready and desired-state current
Deep residency           keep_alive=0 behavior retained
TTM                      4194304 / 4194304
kernel policy            Fedora current; no historical blacklist warning
IOMMU                    baseline not forced; optional enabled state informational/outside baseline
failed units             none
unintended model residency none
```

## Required handoff

```text
TESTING -> MAIN INTEGRATION
candidate:
source archive SHA-256:
RPM NEVRA:
source/deterministic result:
RPM/repository result:
Ollama exact payload/version result:
three-lane /api/version:
package-owned service result:
Standard/Deep/task/Jina smoke:
RAG specialist result/reference:
TTM/IOMMU/kernel diagnostic result:
40-CU unchanged-boundary smoke:
final topology/residency:
final authenticated verifier:
needed source fixes:
overall release acceptance:
evidence archive + SHA-256:
```

## Upstream references

- Ollama v0.34.2 release: https://github.com/ollama/ollama/releases/tag/v0.34.2
- Ollama Linux manual payload installation: https://docs.ollama.com/linux
- BC-250 IOMMU/P-state investigation: https://github.com/lorek123/bc250-notes
- BC-250 CU live manager / no-kernel-patch workflow: https://github.com/WinnieLV/bc250-cu-live-manager

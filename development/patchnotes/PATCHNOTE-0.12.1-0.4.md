# BC-250 0.12.1-0.4 development patch note

## Release identity

```text
VERSION      0.12.1
RPM Release  0.4%{?dist}
NVR          bc250-llm-server-0.12.1-0.4
```

## Scope

This is a bounded runtime/corpus-lifecycle follow-up to 0.12.1-0.3. It does not redesign Open WebUI roles, embedding policy, Deep residency, model-selection policy or 40-CU production behavior.

### Ollama 0.34.2

0.34.2 becomes the package standard because that exact payload passed a clean-boot BC-250 comparison covering normal lanes, production generation, 8192-context recall, bounded long generation, GPT-OSS Deep-to-task transition, Jina embedding, Open WebUI Documents/RAG, UMA memory and final cleanup. The package now downloads the exact `ollama-linux-amd64.tar.zst` asset, verifies its pinned SHA-256, replaces the payload under `/usr/local`, preserves RPM-owned service units, and requires :11434/:11435/:11437 to report 0.34.2.

### RAG lifecycle

`bc250-rag` adds one maintainable local workflow around the existing importer:

```text
inbox/{german,french,bilingual} -> local extraction/agent -> working -> human review -> active -> Open WebUI
```

Agent automation is proposal-only. It never activates content. Text-native PDFs within the bounded single-pass size are handled locally; scanned PDFs are left for the existing local OCR workflow and oversized documents are left for a genuine document/chapter split rather than adding an automatic chunk-reassembly subsystem. `bc250-rag-import plan|sync` remains compatible for existing corpora.

### Hardware diagnostics

The package no longer warns about historical kernel-version ranges; Fedora-current is the supported kernel policy. IOMMU is no longer labelled categorically broken: it remains unnecessary/outside the qualified appliance baseline and should not be forced without a matching BIOS/device qualification. The required TTM values remain exactly 4194304/4194304; verifier output now points at likely tmpfiles/modprobe conflicts when live values differ.

## Deliberately deferred

- Open WebUI 0.11.4 evaluation.
- MTP promotion or agent acceleration policy.
- ROCm, async-compute kernel/Mesa work, ACPI overrides or 8-core baseline.
- Removal of the patched AMDGPU 40-CU path before a stock-AMDGPU/live-manager A/B.
- Automatic OCR inside `bc250-rag`; use the existing local OCR workflow.
- Automatic large-document chunk/reassembly; split at genuine boundaries and review.

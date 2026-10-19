# Product goal and roadmap

## Product goal

BC-250 is a self-contained, privacy-oriented, open-source office AI appliance for individuals and small NGOs. It should provide excellent local RAG/document workflows, German ↔ French office translation, local conversation/document analysis, predictable maintenance and a polished ordinary-user experience while retaining an advanced-user layer.

It is not merely Fedora + Ollama + Open WebUI, and it does not claim to create GDPR compliance automatically.

## Current architecture

The supported baseline is stock Fedora AMDGPU/Mesa with the package's current stock-core runtime/model topology. The experimental GFX1013 patched-kernel/private-RADV project is closed and is not a normal package feature.

## Priority order

```text
stock-core reliability
  → bounded cleanup only where it removes real ownership/risk
  → RAG/document workflow quality and provenance/deletion correctness
  → German ↔ French translation quality and recovery UX
  → polished local assistant / office workflow
```

Repository simplification is a means, not the roadmap. Runtime/model upgrades require separate evidence and should not be bundled into low-risk release/process or RAG-safety cleanup.

## Product boundaries to preserve

- local-first operation;
- filesystem corpus as RAG source of truth;
- human review before `working/` content reaches `active/`;
- explicit `--prune` deletion boundary;
- public/confidential separation;
- one active inference user at a time is acceptable even when several accounts exist;
- `status`, `health` and `verify` remain distinct interfaces;
- ordinary users should not need Fedora/systemd/Ollama expertise;
- advanced users keep optional model/experiment flexibility.

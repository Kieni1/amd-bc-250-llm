# BC-250 0.11.3-1.2 patch note — work in progress

## Release identity

VERSION: `0.11.3`  
RPM Release: `1.2`  
Expected NVR: `bc250-llm-server-0.11.3-1.2`

This is a narrow follow-up to 0.11.3-1.1. It carries forward the unpublished 0.5
installer/maintenance refinements and the 1.1 RAG/Open WebUI/MTP hardening unchanged.

## Changes in 1.2

- Fix Ruff B023 in `models/modelctl.py` by binding the current model label and provider
  explicitly when the nested install/convergence header helper is called. This is a
  code-quality fix only; model selection, reconciliation and output semantics are unchanged.
- Preserve `models/modelctl.py` as executable mode `0755` in the source artifacts. The RPM
  install manifest already installs the controller as mode `0755`; that packaging contract is
  unchanged.

## Deliberate non-changes

- no production model, role, Modelfile or runtime-topology changes;
- no RAG evaluator, Open WebUI benchmark, MTP runtime or installer behavior changes beyond
  the code-quality fix above;
- no new package test solely for the source executable bit;
- no qualification-threshold changes.

## Validation status

This regeneration intentionally keeps validation bounded. The corrected Python file is
syntax-compiled and the generated artifacts are checked for archive integrity. Full RPM/SRPM,
Ruff/ShellCheck and BC-250 hardware qualification remain external/deferred.

The newest complete whole-appliance hardware evidence remains exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64`; it must not be relabelled as 1.2 qualification.

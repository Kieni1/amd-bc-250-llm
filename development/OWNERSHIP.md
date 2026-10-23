# Repository ownership map

This is deliberately small. New code should normally fit an existing owner rather than create a new subsystem.

| Area | Owner / responsibility |
|---|---|
| `packaging/` | RPM construction, public `bc250` dispatch, completion, package payload and upstream provenance |
| `cmd/system/` | installation/convergence and low-level appliance runtime controls |
| `cmd/monitoring/` | status, health, verify and support diagnostics |
| `cmd/maintenance/` | backup, pruning, warm-up, power and future restore implementation |
| `cmd/benchmark/` | advanced benchmark/revalidation evidence workflows |
| `cmd/qualification/` | advanced package/resilience qualification evidence |
| `models/modelctl.py` + `models/modelfiles/` | model catalog/source/registration management |
| `models/modelfiles-retired/` | intentionally visible retired Modelfiles; source-only, never installed |
| `cmd/documents/` | managed document lifecycle, importer and OCR workflow; persistent on-device document/RAG paths remain stable user state |
| `models/mtp/` | advanced MTP catalog/runtime implementation |
| `models/coding-agent/` | advanced coding-agent workflows |
| `config/` | shipped static configuration, systemd/container definitions and package-owned Open WebUI desired state |
| `development/` | Git-only engineering memory and governance, never installed appliance functionality |
| `tests/` | observable current behavior and intentional absence regressions |

Public product concepts are intentionally fewer than implementation owners. Ordinary users use `bc250 document`; `rag` remains an internal/storage term until a separate persistent-state migration is explicitly designed.

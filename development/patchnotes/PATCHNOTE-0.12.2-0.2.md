# BC-250 0.12.2-0.2 development patch note

## Release identity

```text
VERSION      0.12.2
RPM Release  0.2%{?dist}
NVR          bc250-llm-server-0.12.2-0.2
```

## Scope

0.12.2-0.2 supersedes the unqualified 0.12.2-0.1 source candidate. It keeps the same runtime/model
candidate decisions and closes logic-review defects before the first exact-installed 0.12.2 device gate.

## Translation contract closure

- French recommendation detection explicitly covers `devrais`, `devrait`, `devrions`, `devriez`,
  and `devraient`.
- French obligation detection covers `dois`, `doit`, `devons`, `devez`, and `doivent`; permission
  detection covers `peux`, `peut`, `pouvons`, `pouvez`, and `peuvent`. Prohibition checks use the
  same complete forms.
- Leading-zero decimals such as `0.125` and `0,125` remain decimal values and cannot compare equal
  to `125` in percentage or currency integrity checks.
- Benchmark numeric qualification imports the package runtime filter authority instead of maintaining
  separate parsers.
- Direct Translate-Gemma qualification imports the exact packaged system prompt and direction wrappers.
- Direct modality failures are classified as `modality`, matching the Open WebUI path.

## Open WebUI policy and migration closure

- `ordinary_user_visible`, when present, must be a JSON boolean; malformed values fail closed.
- Automatic migration rollback snapshots preserve xattrs, ACLs and numeric ownership. Operator
  documentation now includes checksum verification, stopped-state extraction, SELinux relabeling,
  SQLite integrity verification and restart steps.

## Documentation boundary

The runtime translation filter protects identifiers, currency/percentage values and bounded legal
modality. Date semantic preservation is intentionally qualification/benchmark coverage rather than a
runtime filter check.

## Validation boundary

Focused/static validation is required for these changed boundaries. The full deterministic suite is
not required for this integration closure and must not be reported as rerun unless an external gate
actually executes it. Exact-installed device/runtime acceptance remains pending.

# BC-250 release testing handover — 0.13.1-1.0

## Purpose

Qualify the exact RPM for the small release-hygiene delta over the already qualified 0.12.2-0.8 appliance.
Do not replay closed model or architecture campaigns.

## Build gate

Record exact Git/source identity, SRPM/RPM NEVRA and hashes. Require the normal source/package gates:

```text
python3 scripts/validate.py
python3 development/scope.py check
ruff check .
ShellCheck/package shell gate
rpmlint -c packaging/rpmlint.toml dist/*.rpm
actual-RPM payload contract
```

Target:

```text
bc250-llm-server-0.13.1-1.0.fc44.x86_64
```

## Upgrade bytecode gate — primary new release test

Prepare exact 0.12.2-0.8 with known residue:

```text
/usr/libexec/bc250-llm-server/__pycache__/rag_import*.pyc
/usr/libexec/bc250-llm-server/__pycache__/benchmark_common*.pyc
/usr/share/bc250-llm-server/openwebui/functions/__pycache__/bc250_translation_direction*.pyc
```

Upgrade to exact 0.13.1-1.0, run `sudo bc250 install`, then exercise the normal Python-backed paths.
Required result:

```text
stale package-tree bytecode removed
no bytecode recreated under package-owned /usr
rpm -V clean
zero unowned files under package-owned /usr
```

The cleanup must be bounded to BC-250 package roots; unrelated Python caches elsewhere must remain untouched.

## Optional-model UX gate

Qualify these states:

```text
required + installed                         -> CURRENT
optional + absent                            -> OPTIONAL — not installed
optional + source cached, no runtime state   -> OPTIONAL — source cached, not registered
optional + explicitly applied                -> CURRENT
selected optional + registration removed     -> DRIFT + repair guidance
```

No apply/refresh recommendation is allowed for intentionally unselected optional state.

## Historical-model/Open WebUI gate

Create the known zero-copy historical Qwen3.6 native registration manually.
Require:

```text
source graveyard remains absent from active model discovery/package installation
manually registered model is represented through normal testing-policy handling
ordinary role=user /api/models visibility remains false for this admin/testing-only profile
Open WebUI desired-state status converges cleanly
bc250 model purge-retired --yes detects/removes the registration when explicitly requested
```

Graveyard membership is archive metadata only; it is not inferred as runtime state.

## Regression smoke

Run:

```text
sudo bc250 verify
sudo bc250 openwebui-setup status
bounded RAG smoke if installer/Open WebUI delta crosses it
```

Preserve current reporting semantics:

```text
Run completion: completed
Coverage: partial (optional Agent not installed) when Agent is absent
raw translation quality failure separated from product-guard PASS/withheld
CU live routing / Saved boot profile / Boot restore service vocabulary
```

## Stop rule

If the exact upgrade/layout/model-status/Open WebUI delta passes and final state is restored, stop.
Do not rerun model selection, structured-output discovery, full RAG tournament, Agent baseline qualification,
MTP/OCR campaigns, or multi-device performance work.

# BC-250 current work / next-build handover — 0.12.2-0.8

## Identity

```text
VERSION       0.12.2
RPM Release   0.8
NVR target    bc250-llm-server-0.12.2-0.8
```

Source checkpoint:

```text
bc250-llm-server-0.12.2-0.8 working source
predecessor: amd-bc-250-llm-0.12.2-0.7-workbench-rpmlint-policy-fix-final.zip
predecessor SHA-256: 9ab3947b73bc4108bb1409feef480f7a894c66dd79e86a34ef6848ea05a25869
```

## Current source state

Source work is substantially integrated.

Final greenfield + 0.8 exact-device feedback batch includes:

- canonical `bc250 COMMAND` dispatcher;
- removal of generated `bc250-*` compatibility aliases;
- private helper movement to libexec;
- live-manager-only CU architecture;
- replacement-AMDGPU patch backend removed;
- RAG promoted active/product-relevant;
- legacy public RAG importer compatibility removed;
- candidate screens retained in source but no longer installed;
- rejected EuroLLM translation candidate moved to graveyard;
- compact operator-oriented installed documentation;
- structured-output role policy finalized;
- optional Agent coverage semantics;
- benchmark reporting/completeness improvements;
- distinct project/governor RPM license basenames;
- single Ollama sysusers authority;
- actual-RPM payload validation;
- configured post-build CI rpmlint with genuine findings fixed rather than filtered;
- revalidation v4.7 separates completed execution from optional coverage and reports successful translation withholding as product-integrity PASS;
- installer/verifier wording now uses live routing, saved boot profile, boot-restore service and inactive optional Agent terminology;
- Fedora runtime dependency is `git-core` rather than the larger `git` meta-package;
- current-code/docs command-surface audit and migration-shim removal.

## Current validation

Recorded final source checks:

```text
507/507 deterministic Python tests PASS
scope check PASS
RPM/source preflight PASS
bash -n PASS
Python compileall PASS
JSON parse PASS
Ruff external/not available in ChatGPT environment
```

## Important exact-device boundary

Exact 0.12.2-0.7 fresh-install evidence is now available and functionally clean: guided installation completed, core verification passed 53/53, Open WebUI converged, live CU routing reached 40/40 and restored the saved profile after reboot, and revalidation infrastructure/restoration passed. Optional Agent coverage was legitimately PARTIAL because the add-on was not installed.

That run exposed four reporting/UX defects now fixed in 0.8: completed execution was labeled `incomplete` when coverage was partial; a successful Open WebUI translation integrity withholding was counted as a second product quality failure; CU output used stale performance-profile/live-manager-not-found vocabulary; and the final installer suggested repeating already-completed setup. The fresh dependency transaction also justified replacing the `git` meta-package with `git-core`.

The next RPM must establish the exact 0.12.2-0.8 package/device state and confirm those corrected semantics without regressing the proven 0.7 appliance behavior.

## Next build sequence

1. Run workstation lint:
   ```bash
   ruff check .
   ```

2. Build exact SRPM/RPM in the normal Fedora/GitHub environment with pinned upstream sources; require `rpmlint -c packaging/rpmlint.toml dist/*.rpm` to pass.

3. Verify package manifest/content:
   - no obsolete kernel-patch source;
   - no removed compatibility aliases;
   - no installed candidate screens;
   - no EuroLLM active Modelfile;
   - RAG assets present;
   - canonical docs present;
   - private helpers under libexec.

4. Install on the BC-250.

5. Verify public interface:
   ```text
   bc250 --help
   sudo bc250-cu-live-manager
   sudo bc250-40cu status
   llm-run-diagnose
   ```

6. Ensure removed public aliases are actually absent.

7. Configure/confirm 40/40 through live manager.

8. Reboot and prove saved live-routing restoration.

9. Run:
   ```text
   bc250 verify
   bc250 revalidate start
   ```

10. Treat missing optional Agent as PARTIAL/SKIPPED coverage, not failure.

11. Smoke RAG:
   - Tika reachable;
   - embedding lane healthy;
   - ingest a small deterministic document;
   - retrieve/answer through the product path;
   - cleanup synthetic state.

12. Verify Open WebUI convergence and curated presets.

13. If the final structured request-construction implementation changed since its focused evidence:
   - Standard structured;
   - Documents structured;
   - Advanced Structured;
   - ordinary Advanced control;
   - Deep unchanged control.

14. Confirm final normal topology and no failed units.

15. Freeze/tag only after exact installed-RPM evidence is clean.

## No longer next work

Do not spend next-build time on:

- Advanced think A/B;
- Standard think/temperature matrix;
- Deep structured discovery;
- EuroLLM Round 2;
- multi-device benchmark tournament;
- replacement-kernel CU patching;
- broad RAG model selection;
- Qwen3.6 35B;
- Tika bullet formatting.

Those are closed decisions or removed architecture.

## Release-closure success definition

The final `0.12.2-0.8` candidate is closed when:

```text
source gates clean
workstation Ruff clean
RPM/SRPM build clean
exact install/upgrade clean
greenfield public API matches package design
live CU survives reboot
bc250 verify clean
bc250 revalidate clean/acceptable PARTIAL only for absent optional Agent
RAG product smoke clean
OWUI convergence clean
structured policies confirmed on final path if changed
normal topology restored
no secret/cleanup/archive regression
```

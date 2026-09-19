# BC-250 0.11.3-1.5 patch note

## Release identity

VERSION: `0.11.3`  
RPM Release: `1.5`  
Expected NVR: `bc250-llm-server-0.11.3-1.5`

This is a focused boundary-correctness and installer-UX release on top of 1.4. It does not change production model roles, RAG policy, MTP defaults, resource thresholds or runtime topology.

## Changes in 1.5

- Fix RAG residency-set restoration for embedding-only models. The fallback `/api/embed` load request now uses a harmless non-empty probe instead of an empty input that Ollama 0.34 rejects. The helper continues to omit `keep_alive` unless explicitly overridden so each lane/service applies its configured/default lifetime policy.
- Keep restoration fail-closed: a benchmark that cannot restore the starting residency set remains an infrastructure failure even when semantic RAG cases pass.
- Make installer all-current model reconciliation concise: required categories now print `Production: 5/5 current`, `Task: 1/1 current`, and `Embedding: 1/1 current` without an additional `Done: N model(s) processed.` line. Detailed output remains for downloads, metadata repair, Modelfile drift or registration changes.
- Rename the setup-plan display label from `primary reboot` to the operator-facing `reboot required`; the actual reboot lifecycle is unchanged.

## Installed 1.4 evidence motivating this release

Exact installed `bc250-llm-server-0.11.3-1.4.fc44.x86_64` completed the guided installer and core verifier with **54 ok / 0 warn / 0 fail**. The installer correctly reused the verified IQ3_S source while reconciling its Modelfile and downloaded/registered the new IQ3_XXS experiment. Optional maintenance/Pi setup was skipped without mutating existing configuration.

The subsequent v4.2 revalidation did **not** complete. RAG quality itself passed **4/4**, but post-benchmark restoration of the previously resident Jina embedding model failed because the fallback embedding-load probe used an empty input. Ollama 0.34 returned `Input content cannot be empty`, so the harness correctly failed closed as infrastructure failure. A separate task quality result was 5/6 with `tags-en: relevance`; that result is preserved for review and is not changed by this release.

This run is therefore useful exact-1.4 installed-device evidence, but it is **not** a complete 1.4 revalidation pass.

## Deliberate non-changes

- no RAG model/default change; Gemma E4B / `bc250-office-documents` remains the production document/RAG role on the 16 GiB profile;
- no RAG evaluator weakening and no change to hard/informational resource thresholds;
- no task prompt/evaluator change for the single `tags-en` relevance miss until its output is reviewed or the result reproduces;
- no MTP model/default/optimization change;
- no service topology, CU/governor or Open WebUI desired-state change.

## Next device gate

Install exact 1.5 and rerun `sudo bc250-revalidate start --owui-token-file /root/owui-test.key`. The key acceptance question is whether RAG finishes 4/4 **and** restores the embedding residency set successfully. Review `tags-en` separately if it reproduces.

## Source validation

`make validate`: **403/403 PASS**. Changed Python compiles and packaged/source shell syntax passes `bash -n`. `models/modelctl.py` remains executable (`0755`). Ruff/ShellCheck were not run in this environment. RPM/SRPM build and exact installed 1.5 BC-250 runtime qualification remain external gates.

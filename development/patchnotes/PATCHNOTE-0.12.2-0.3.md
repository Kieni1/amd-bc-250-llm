# Patch note — 0.12.2-0.3

`0.12.2-0.3` is the repaired successor to the rejected `0.12.2-0.2` source candidate. It closes four source-review findings without changing the broader 0.12.2 runtime/model policy.

- Open WebUI migration safety now starts in RPM `%pre`: if persistent OWUI state exists, `systemctl stop open-webui.service` is issued unconditionally and `ActiveState=inactive` is required before the package-created boot-enable drop-in is removed. The new Quadlet cannot become restart-eligible through `%systemd_post` or another daemon-reload until that stopped invariant is established. Guided `bc250-install` still creates/verifies the stopped-state full rollback snapshot before re-enabling and starting OWUI 0.11.4.
- Translation modality checking is clause-local, ordered and polarity-aware rather than document-global. Negated recommendations and German `muss nicht` are distinct protected states, and recommendation/obligation or permission/obligation events cannot be swapped either across adjacent clauses or within one multi-modal clause.
- Single-separator three-decimal numbers such as `1,234` and `1.234` retain both plausible interpretations for integrity comparison. Translating either ambiguous source form to only `1234` now fails closed for percentages and currencies; unchanged ambiguous forms remain acceptable.
- Translation withholding uses neutral integrity wording so literal/numeric failures are not mislabeled as legal-modality failures. Direct and Open WebUI translation qualification reuse the runtime literal-integrity authority.

The existing 0.12.2 decisions remain: Ollama 0.34.4, Open WebUI 0.11.4, governor 0.4.13, Advanced `think=true` candidate policy, Deep `keep_alive=0`, Tika 4, 8K Qwen pressure-profile retests, role-aware model metadata and the existing four-lane architecture.

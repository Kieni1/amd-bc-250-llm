# Long-term engineering guidelines

## 1. Optimize for a boring appliance

Build, install, inspect, recover and remove should be straightforward. Clever implementation is not a product feature.

## 2. Keep the core stock-first

Prefer standard Fedora/kernel/userspace behavior. Experimental hardware paths stay outside the core until their user value clearly exceeds maintenance and release cost.

## 3. One owner per fact

Important state or identity has one authoritative source. Other commands may display or validate it, not independently derive competing truth.

Examples: Version/Release, runtime pins, model defaults, desired Open WebUI state, selected release identity.

## 4. Prefer deletion over compatibility debt

Compatibility code is justified by a supported upgrade/data path. When that path is no longer supported or needed, remove the compatibility layer and its tests.

## 5. Keep scripts shallow

Avoid wrapper chains and scripts that mostly invoke other scripts. A public command path should be traceable to the component that owns the behavior.

If parsing/state serialization dominates shell code, simplify the behavior or move the structured portion to a language suited to it.

## 6. Validation must not become architecture

Prefer structural guarantees over repeated runtime checks. Keep release-critical validation small. Review every hard gate periodically and ask what artifact-critical invariant it protects.

## 7. Tests follow supported behavior

Tests are not sacred history. Delete or rewrite them when the supported contract changes.

Keep a small release-critical gate, retain broad advisory source coverage, and use narrow exact-artifact device checks. Do not equate fewer tests with simpler product architecture.

## 8. Release identity stays conventional

Use normal RPM Version/Release semantics. Iteration labels live in Git/handovers, not package identity.

## 9. Exact artifacts cross authority boundaries

Selected GitHub build -> exact RPM hash -> exact device test. Never inherit device acceptance from similar source or a previous RPM.

## 10. Greenfield review is recurring maintenance

After a meaningful stable release, or whenever maintenance begins to dominate progress, review the repository as if designing it today.

Ask:

- Which code would we not write today?
- Which scripts exist only because of removed features?
- Which tests protect implementation instead of behavior?
- Which states can disappear?
- Which abstractions have one real caller?
- Which package/build steps can be delegated to standard tooling?

## 11. Complexity requires evidence

A new daemon, state machine, private runtime, boot path, qualification framework or hard release gate requires a concrete measured reason to exist.

If maintenance/failure/release cost is disproportionate to user value, remove it even if technically successful.

## 12. Safety rules survive implementation cleanup

Greenfield cleanup may remove harnesses and scripts, but it must retain durable safety properties:

- fail closed before destructive mutation when state cannot be established;
- rollback material before risky replacement;
- verify cleanup/restoration;
- preserve secrets/private data;
- use external vantage for external exposure claims;
- distinguish failure from incomplete evidence.

## 13. Keep handovers current but not thin

Current handovers should contain enough operational and reasoning discipline for a new engineer/chat to avoid repeating known failure modes.

Remove stale chronology and obsolete campaign machinery, not the lessons learned from them.

## 14. Separate product evolution from infrastructure cleanup

Do not mix runtime upgrades, model-policy changes, performance tuning and broad cleanup unless the dependency is unavoidable.

## 15. Stop when simplification stops simplifying

Do not replace messy code with a more abstract framework just to make the diff look organized. The target is fewer concepts, fewer owners and a smaller failure surface.

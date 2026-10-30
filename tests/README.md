# Tests

This is intentionally a lean pre-1.0 suite.

RPM `%check` runs the package-critical module set declared in `release-contract.json` via
`scripts/validate.sh --package`. The release-preflight module is declared separately in the same
contract, while `scripts/validate.sh` without a mode runs the full advisory repository suite.

The package-critical set protects release identity, packaging/source integrity, runtime behavior,
managed documents/RAG, upstream patch validation and qualification logic without requiring root or
host runtime state. Broader modules cover release wiring, model/catalog behavior, workflows,
benchmarks, installation, maintenance, Open WebUI, storage and other source-level contracts.

Rules for new tests:

1. Test supported public behavior or release integrity, not private helper structure.
2. Do not write to `/run`, `/etc`, systemd, containers, or other host state.
3. Do not require root, a GPU, Ollama, Open WebUI, network access, or a particular workstation.
4. Do not pin documentation wording, historical checkpoint names, temporary implementation order, or exact test counts.
5. Do not duplicate a release-gate command with a synthetic test when executing the command already proves the contract.
6. Prefer one representative contract test over matrices of edge cases unless a real regression justifies them.
7. Delete tests when the behavior they protect is removed; do not preserve compatibility with obsolete internals.

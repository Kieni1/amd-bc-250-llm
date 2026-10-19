# Tests

This is intentionally a lean pre-1.0 suite.

- `test_core.py` is the only RPM `%check` module. It protects release identity, runtime pins, core CLI help, package ownership and active model loading without requiring root or host runtime state.
- `test_release.py` checks release/build policy and frozen-source wiring.
- `test_models.py` checks active catalog integrity without pinning every implementation detail.
- `test_workflows.py` smoke-tests supported operator/specialist entrypoints through `--help` only.
- `test_benchmark.py` protects only the visible-output/thinking semantics that affect evidence correctness.

Rules for new tests:

1. Test supported public behavior or release integrity, not private helper structure.
2. Do not write to `/run`, `/etc`, systemd, containers, or other host state.
3. Do not require root, a GPU, Ollama, Open WebUI, network access, or a particular workstation.
4. Do not pin documentation wording, historical checkpoint names, temporary implementation order, or exact test counts.
5. Do not duplicate a release-gate command with a synthetic test when executing the command already proves the contract.
6. Prefer one representative contract test over matrices of edge cases unless a real regression justifies them.
7. Delete tests when the behavior they protect is removed; do not preserve compatibility with obsolete internals.

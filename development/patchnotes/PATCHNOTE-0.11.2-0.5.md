# Patch note — 0.11.2-0.5

Release `0.11.2-0.5` is a corrective packaging and qualification update. It does not change production models, runtime topology, benchmark thresholds, or Open WebUI role policy.

## Fixed

- **Installed Open WebUI translation revalidation:** `openwebui-benchmark.py` previously derived `examples/benchmark/translation-office.json` from its source-tree location. Installed under `/usr/libexec/bc250-llm-server`, that became the invalid path `/usr/examples/benchmark/translation-office.json`. The stage now uses the same package-resource resolver as the other benchmark checks and resolves the RPM fixture from `/usr/share/bc250-llm-server/benchmark/translation-office.json`.
- **Consistent benchmark resources:** source/install/override selection is centralized in `benchmark_common.py`. `category-benchmark.py` and `openwebui-benchmark.py` now share the same fixture-resolution contract; category task prompt policy also uses the shared package-resource method.
- **Cleaner source validation:** without an explicit override, a source checkout prefers its own resources even when an older RPM is installed. `BC250_BENCH_FIXTURES` and `BC250_SHARE` remain explicit authoritative overrides.
- **GitHub test portability:** installer unit tests carry their own minimal `jq` test double, eliminating dependence on whether the GitHub test image happens to contain `jq`.
- **Reported Ruff I001:** corrected import ordering in `tests/test_openwebui.py`; Ruff itself was not executed in the local source-validation environment.

## Validation scope

Focused validation for this patch covered the shared resource resolver, Open WebUI translation fixture consumption, benchmark/category behavior touched by the refactor, installer tests affected by the hermetic `jq` fixture, packaging release/changelog consistency and Python syntax on changed Python files. Ruff was not available or executed in that local environment; the reported import-order finding was corrected in source and remains for the workstation lint gate to verify. The full 341-test suite and real BC-250 revalidation were intentionally not run locally.

## Device follow-up

After installing `0.11.2-0.5`, rerun:

```bash
sudo bc250-revalidate start --owui-token-file /root/owui-test.key
```

The previous `owui-translation` infrastructure failure for `/usr/examples/benchmark/translation-office.json` should no longer occur. Any remaining `quality-fail` result should then represent benchmark quality rather than missing packaged data.

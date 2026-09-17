# BC-250 quality-check source tree

This subtree contains real-device candidate/quality scripts. The canonical operator
procedure is `docs/QUALITY-CHECKS.md` in the source tree and
`/usr/share/doc/bc250-llm-server/docs/QUALITY-CHECKS.md` after installation. Keep
workflow, promotion and evidence-policy prose there rather than duplicating it here.

These scripts are intentionally separate from `bc250-revalidate`: they investigate
candidates and quality questions; they do not constitute final release qualification
and they do not build RPMs.

## Layout

- `history/` — retained Batch 1–3D and short historical comparison recipes for
  reproducibility; do not use them as the default path for new experiments.
- `main/` — sequential main-model candidate matrices against production GPT-OSS.
- `task/` — generic compact-task screens against the package-owned task default.
- `translation/` — direct screens, authenticated Open WebUI integration screens,
  prompt profiles and provider-mutation support.
- `package/` — lightweight installed-asset smoke checks.
- `utils/` — evidence inspection helpers.

## Maintainer rules

Prefer extending an existing generic screen over adding one wrapper per model. Preserve
`rc=0` pass, `rc=3` quality failure, and other-nonzero infrastructure-failure semantics.
A script that mutates Open WebUI must restore the exact original state and keep secrets
out of evidence. Do not put GGUF weights in evidence bundles. Evidence tarballs from these experiment scripts intentionally have no `.sha256`
sidecar files, but the scripts print the archive SHA-256 so the returned evidence can be
identified exactly. Copy the exact contract inputs into evidence when provenance is needed.

For task candidates, reject cheaply: one quality screen first, then the tiny warm-main
survival gate for materially larger models, then product-path/overlap work. For direct
translation, keep the main lane empty, record the reasoning policy (`auto|true|false`),
and wait for memory recovery before moving to another large foreground model.

When a run materially changes a model decision, record the exact model/settings/results,
evidence filename + SHA-256, interpretation, decision, and **retest conditions** in the
Git repository under `development/model-runs/` (not in the installed RPM); update
`MODELS.md` only with the concise current conclusion.

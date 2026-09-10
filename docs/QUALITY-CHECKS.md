# Standalone quality checks

The package installs candidate-quality checks under
`/usr/share/bc250-llm-server/quality-checks/`. They are deliberately separate
from `bc250-revalidate` and from deterministic package-build validation.

Use them only on the real BC-250 when investigating model quality. They can
download/register experimental GGUFs, make model requests, and create evidence
bundles below `${BC250_QUALITY_ROOT:-$HOME/bc250-quality}` with a matching
`.tar.gz` in `$HOME`. They do **not** build the RPM and do not constitute final
v1.0 qualification.

## Package-level smoke

After installing an RPM, the lightweight asset check verifies that the new
standalone scripts and candidate Modelfiles were installed and that model
discovery can see them. It does not download weights or exercise the GPU:

```bash
sudo /usr/share/bc250-llm-server/quality-checks/package/installed-assets.sh
```

## Compact task candidates

Run one candidate at a time. Each wrapper defaults to three rounds and compares
the candidate on main Ollama against the packaged Gemma 3 1B task baseline:

```bash
/usr/share/bc250-llm-server/quality-checks/task/11-lfm12b.sh
/usr/share/bc250-llm-server/quality-checks/task/12-minicpm5-2b.sh
/usr/share/bc250-llm-server/quality-checks/task/13-qwen3-1p7b.sh
/usr/share/bc250-llm-server/quality-checks/task/14-qwen38-2b.sh
```

The generic form is:

```bash
/usr/share/bc250-llm-server/quality-checks/task/10-candidate-screen.sh \
  EXPERIMENT-MODEL [ROUNDS]
```

The screen unloads the main lane around each candidate request series so an
experimental task model is not accidentally measured while a warm GPT-OSS model
is resident. That isolation is a quality-screen safety measure; a separate
coexistence/resource test is mandatory before any task promotion.

## Translation candidates

Keep the previously weak Ministral candidate to a short comparison screen, then
prioritize Hunyuan-MT and Translate-Gemma:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/11-ministral-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/12-hunyuan-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/13-translate-gemma-direct.sh
```

These use the existing `bc250-benchmark translation` fixture with explicit
source/target direction and do not mutate Open WebUI. A candidate that clearly
survives the direct screen can then be tested through the actual authenticated
Open WebUI translation preset:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/21-hunyuan-owui.sh
/usr/share/bc250-llm-server/quality-checks/translation/22-translate-gemma-owui.sh
```

The generic integration form is:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/20-owui-candidate-screen.sh \
  EXPERIMENT-MODEL \
  /usr/share/bc250-llm-server/quality-checks/translation/prompts/auto-direction-minimal.txt \
  [ROUNDS]
```

The integration check saves the exact existing `bc250-office-translation`
preset, temporarily points it at the candidate, verifies live readback, disables
background title/tag/follow-up jobs, restores the original preset, and scans the
evidence directory for the bearer token before creating the tarball. Treat a
restoration or credential-scan failure as infrastructure failure.

## Evidence semantics

The scripts retain the package's quality-result semantics:

- `rc=0`: quality pass;
- `rc=3`: quality failure that remains useful evidence;
- other nonzero result: infrastructure failure.

Output-budget diagnostics are evidence and must not automatically be relabeled as
model-quality defects. Likewise, evaluators must not be weakened to turn genuine
model mistakes into passes.

Historical Batch 1–3D scripts are installed under `quality-checks/history/` only
for reproducibility. Prefer the generic current screens for new comparisons.

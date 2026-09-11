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
the candidate against the packaged Gemma 3 1B task baseline on the dedicated
task Ollama runtime:

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

The screen downloads the candidate through the normal experiment catalog and
temporarily mirrors its Ollama registration into the task service. This makes
baseline and candidate use the same task-lane 4096-context, q8 KV-cache and
keep-alive policy. The temporary task registration is removed on exit. The main
lane is still unloaded around each candidate request series so an experimental
task model is not accidentally measured while a warm GPT-OSS model is resident.
That isolation is a quality-screen safety measure; a separate coexistence/resource
test is mandatory before any task promotion.

Task benchmark metadata records the actual request contract: task requests use
`keep_alive=0`, titles mirror Open WebUI 0.11.3's 1000-token fallback, and the
packaged tag/query paths retain the 128-token task budget. The screen does not
silently enlarge those budgets to improve a candidate's score.

## Translation candidates

Start with a short LFM reference under the same current evaluator, keep the
previously weak Ministral candidate to a short comparison screen, then prioritize
Hunyuan-MT and Translate-Gemma:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/14-lfm-direct-reference.sh
/usr/share/bc250-llm-server/quality-checks/translation/11-ministral-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/12-hunyuan-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/13-translate-gemma-direct.sh
```

The LFM reference does not install or mutate the production model. It exists so
changes to the translation evaluator, output budget, or specialist prompt profiles
do not get compared only against a historical score produced under an older
contract. Run one batch at a time.

Direct screening uses explicit source/target direction, defaults to a 1024-token
output budget, and does not mutate Open WebUI. Hunyuan-MT uses its upstream
target-language user prompt; Translate-Gemma uses a `CURRENT_SOURCE`-shaped
system/user exchange; other models use the generic explicit-direction prompt.
A candidate that clearly survives the direct screen can then be tested through
the actual authenticated Open WebUI translation preset. Before the first challenger
OWUI run, re-anchor the best historical LFM prompt once under the same current
OWUI evaluator:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/23-lfm-owui-reference.sh
/usr/share/bc250-llm-server/quality-checks/translation/21-hunyuan-owui.sh
/usr/share/bc250-llm-server/quality-checks/translation/22-translate-gemma-owui.sh
```

Run only the reference and the challenger that actually survived direct screening;
do not automatically mutate Open WebUI for a failed direct candidate.

The generic integration form is:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/20-owui-candidate-screen.sh \
  EXPERIMENT-MODEL \
  /usr/share/bc250-llm-server/quality-checks/translation/prompts/auto-direction-minimal.txt \
  [ROUNDS]
```

The integration check saves the exact existing `bc250-office-translation`
preset, temporarily points it at the candidate, verifies that selected stable live-preset fields differ
only by the intended candidate delta, disables background title/tag/follow-up jobs,
captures per-request wall time plus BC-250 temperature/memory/swap telemetry,
restores the original preset, and scans the evidence directory for the bearer token
before creating the tarball. Translate-Gemma uses its dedicated auto-direction
prompt shaped around the fine-tune's `CURRENT_SOURCE` contract. Treat a restoration,
telemetry, or credential-scan failure as infrastructure failure.

## Evidence semantics

The scripts retain the package's quality-result semantics:

- `rc=0`: quality pass;
- `rc=3`: quality failure that remains useful evidence;
- other nonzero result: infrastructure failure.

The standalone direct and Open WebUI wrappers propagate this return-code contract
after writing their evidence tarball; do not infer success merely because a tarball
was created. Their summaries include per-round, per-direction and per-case quality
plus latency/resource extrema.

Output-budget diagnostics are evidence and must not automatically be relabeled as
model-quality defects. Likewise, evaluators must not be weakened to turn genuine
model mistakes into passes.

Historical Batch 1–3D scripts are installed under `quality-checks/history/` only
for reproducibility. Prefer the generic current screens for new comparisons.

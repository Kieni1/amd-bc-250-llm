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

## Main-model candidates

Run the packaged large-main candidate matrix only on the real BC-250:

```bash
sudo /usr/share/bc250-llm-server/quality-checks/main/10-main-model-candidate-matrix.sh
```

It compares production GPT-OSS at the start and end, installs missing candidates
through `bc250-model`, unloads resident main/task/embedding models between runs, and
runs the generation `compare` profile plus the memory-oriented `edge` profile.
Candidate GGUFs are retained by default (`BC250_KEEP_GGUF=1`) so a failed registration
or later lower-quant experiment does not force a redownload. Registrations created by
the matrix are removed during cleanup. Set `BC250_RUN_EDGE=0` only for the shorter
first quality screen; any candidate that survives still needs the resource edge run.

## Compact task candidates

The previous one-off compact-candidate wrappers were removed when their Modelfiles
moved to the source-only graveyard. For any future packaged `exp-*` challenger,
compare it against the current package-owned task default with the generic form:

```bash
/usr/share/bc250-llm-server/quality-checks/task/10-candidate-screen.sh \
  EXPERIMENT-MODEL [ROUNDS]
```

The generic screen defaults to one canonical round. It downloads the candidate through
the normal experiment catalog and temporarily mirrors its Ollama registration into the
task service for a cheap same-lane comparison. The temporary task registration is
removed on exit. This is quality evidence only. For a materially larger candidate, do
not spend repeated task/product-path calls until the dedicated warm-main safety gate
passes:

```bash
CANDIDATE_MODEL=tmp-task-candidate:latest \
  /usr/share/bc250-llm-server/quality-checks/task/20-survival-gate.sh
```

The survival gate is intentionally a low-level safety probe: it expects a uniquely named
temporary task-lane alias that has already been staged and definition-checked by the
specialist campaign. It does not install or clone a model itself, which avoids hiding
model-definition changes inside the safety measurement.

That gate uses a tiny eight-token request beside warm GPT-OSS, requires task unload,
main residency, the normal main/task/embedding/Open WebUI/Tika services to stay active,
minimum memory/swap guardrails and no new serious kernel warning. Any global OOM or main-residency loss rejects the concurrent task role.
After an OOM experiment, use `task/30-appliance-recovery-check.sh` before continuing.
By default it actively reloads/warm-checks GPT-OSS if needed, requires the normal
main/task/embedding/Open WebUI/Tika services, an empty task lane, and fails on serious
GPU/OOM events that occur during the recovery probe. Serious events
from the preceding failed experiment are printed separately as context and do not by
themselves make recovery impossible to prove. Set `WARM_MAIN=0` only for an explicitly
read-only residency check.

Task benchmark metadata records the actual request contract: task requests use
`keep_alive=0`, titles mirror Open WebUI 0.11.3's 1000-token fallback, and the
packaged tag/query paths retain the 128-token task budget. The screen does not
silently enlarge those budgets to improve a candidate's score.

## Translation candidates

Use the eight-case DE<->FR suite as a short screening gate, not a ranking benchmark.
Once a candidate reaches the known saturated ceiling, advance it only if the current
Stage-2 decision record gives it a real promotion case. Do not repeat the short screen to
rank already-saturated models. No challenger is promoted until the harder corpus and
exact product path are complete. Useful current wrappers remain:

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

Direct screening uses explicit source/target direction, defaults to one round and a
1024-token output budget, and does not mutate Open WebUI. The main lane must be empty
before a foreground direct screen; the harness refuses to unload a model that was
already resident. Set `BC250_TRANSLATION_THINK=auto|true|false` to make the reasoning
request contract explicit. Several Qwen-family candidates produced empty answers when
the default reasoning path consumed the budget and then passed 8/8 with `think:false`,
so thinking policy is part of translation provenance. Hunyuan-MT uses its upstream
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

The integration check serializes temporary Open WebUI mutations with an exclusive
lock. It saves the exact `bc250-office-translation` preset and complete Ollama
provider config, keeping the unredacted provider config only in root-owned mode-0600
files under `/run`. For an experimental model it locates the enabled main provider
by port 11434 and, only when that provider already has a restrictive `model_ids`
list, appends the raw candidate exactly once; an absent/empty list remains
unrestricted. `prefix_id` is honored for the effective model ID. Zero/multiple
11434 providers or a disabled provider fail closed. Evidence receives only redacted
provider snapshots.

The check then proves effective candidate/base-preset visibility, disables
background title/tag/follow-up jobs, preserves curl rc + HTTP status + response body
for provider/model/chat operations, and captures per-request wall time plus BC-250
temperature/memory/swap telemetry. On exit it restores the preset first and exact
provider config second, refreshes effective models, verifies both persisted and
effective restoration, scans evidence for the admin token and all provider secrets,
and writes runtime provenance plus `run-manifest.json`. Translate-Gemma uses its
dedicated auto-direction prompt shaped around the fine-tune's `CURRENT_SOURCE`
contract. Treat any restoration, telemetry, HTTP-contract or credential-scan
failure as infrastructure failure.

## Evidence semantics

The scripts retain the package's quality-result semantics:

- `rc=0`: quality pass;
- `rc=3`: quality failure that remains useful evidence;
- other nonzero result: infrastructure failure.

The standalone direct and Open WebUI wrappers propagate this return-code contract
after evidence finalization; do not infer success merely because an evidence
directory or tarball exists. The direct translation harness writes its authoritative
local final status after privacy scanning; if archive creation itself fails, it rewrites
the local status/manifest with the archive-failure return code. The OWUI wrapper deliberately withholds the tarball
if credential scanning or root-only temporary-file cleanup fails. Their summaries include per-round, per-direction and per-case quality
plus latency/resource extrema.

Output-budget diagnostics are evidence and must not automatically be relabeled as
model-quality defects. Likewise, evaluators must not be weakened to turn genuine
model mistakes into passes.

Historical Batch 1–3D scripts are installed under `quality-checks/history/` only
for reproducibility. Prefer the generic current screens for new comparisons.

Before production translation promotion, use a harder corpus covering both directions, inclusive deadlines, contractual modality, exact amounts/references, negation, protected paths/keys/quotes and structured formatting. The current eight-case short screen remains a screening gate, not promotion proof.

Evidence tarballs from the current generic task/translation checks intentionally have no `.sha256` sidecar files, but each script prints the archive SHA-256 for exact evidence identification. Preserve the exact fixture/evaluator/prompt material inside evidence where needed, normalize archive ownership metadata, and keep archive/delivery bookkeeping separate from model-quality conclusions.

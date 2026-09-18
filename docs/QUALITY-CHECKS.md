# Standalone quality checks

The package installs candidate-quality checks under
`/usr/share/bc250-llm-server/quality-checks/`. They are deliberately separate
from `bc250-revalidate` and from deterministic package-build validation.

Use them only on the real BC-250 when investigating model quality. They can
download/register experimental GGUFs, make model requests, and create evidence
bundles below `${BC250_QUALITY_ROOT:-$HOME/bc250-quality}` with a matching
`.tar.gz` in `$HOME`. They do **not** build the RPM and do not replace whole-appliance revalidation or production-promotion evidence.

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
main residency, healthy services, minimum memory/swap guardrails and no new serious
kernel warning. Any global OOM or main-residency loss rejects the concurrent task role.
After an OOM experiment, use `task/30-appliance-recovery-check.sh` before continuing.
By default it actively reloads/warm-checks GPT-OSS if needed, requires an empty task lane,
and fails on serious GPU/OOM events that occur during the recovery probe. Serious events
from the preceding failed experiment are printed separately as context and do not by
themselves make recovery impossible to prove. Set `WARM_MAIN=0` only for an explicitly
read-only residency check.

Task benchmark metadata records the actual request contract: task requests use
`keep_alive=0`, titles mirror Open WebUI 0.11.3's 1000-token fallback, and the
packaged tag/query paths retain the 128-token task budget. The screen does not
silently enlarge those budgets to improve a candidate's score.

## Translation qualification

The broad DE↔FR tournament is closed. `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` is the package production translation
base and the two package-owned Open WebUI roles provide the selected Stage-2E direction
contract. The former LFM production model is retained only as `exp-lfm25-8b-a1b-liquidai-q6-k` for explicit
rollback/reference comparisons. Hunyuan and Ministral translation-only challengers are
retired to the source graveyard; TIR remains experimental only for broader office/RAG work.

Current direct checks:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/13-translate-gemma-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/14-lfm-direct-reference.sh
```

Current restoring Open WebUI comparisons:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/22-translate-gemma-owui.sh
/usr/share/bc250-llm-server/quality-checks/translation/23-lfm-owui-reference.sh
```

The generic `10-direct-candidate-screen.sh` and `20-owui-candidate-screen.sh` remain
available for a deliberately selected active `exp-*` model. They preserve the same
return-code, restoration, privacy and evidence rules. Do not resurrect graveyard models
merely to repeat a closed tournament.

The production product path is the pair of package-owned roles
`bc250-office-translation-de-fr` and `bc250-office-translation-fr-de`. Both use the
exact Stage-2E system prompt, `max_tokens=2048`, thinking omitted, and the non-global
`bc250_translation_direction` filter. After installing this release, run a bounded
real-device product-path verification before calling the new default fully requalified.
The exact Stage-2E evidence archive remains
`bc250-translation-stage2e-config-bundle-20260917-232916.tar.gz`, SHA-256
`63fa90ea1187b7c878da0067d3f0be91e5a9e9faadbb4c919c7ed2a374f80c1c`.

## Evidence semantics

The scripts retain the package's quality-result semantics:

- `rc=0`: quality pass;
- `rc=3`: quality failure that remains useful evidence;
- other nonzero result: infrastructure failure.

The standalone direct and Open WebUI wrappers propagate this return-code contract
after evidence finalization; do not infer success merely because an evidence
directory or tarball exists. The OWUI wrapper deliberately withholds the tarball
if credential scanning or root-only temporary-file cleanup fails. Their summaries include per-round, per-direction and per-case quality
plus latency/resource extrema.

Output-budget diagnostics are evidence and must not automatically be relabeled as
model-quality defects. Likewise, evaluators must not be weakened to turn genuine
model mistakes into passes.

Historical campaign scripts remain in source under `quality-checks/history/` for reproducibility and archaeology; they are not installed as the current operator interface. The supported current screens carry forward the lifecycle properties that still matter: bounded lane isolation, pre/post state capture, exact Open WebUI/provider restoration, credential/privacy checks, serious-warning capture, memory recovery, normalized evidence archives and authoritative final-RC recording. Prefer those current screens for new comparisons.

Stage-2E completed the broad hard-corpus/model-configuration comparison and selected Translate-Gemma. This source promotes those weights as `prod-translate-gemma4-sub-e4b-17s-q4-k-xl` behind the two package-owned direction roles. After installing the built RPM, run only the bounded integrated Open WebUI verification: canonical sanity plus the targeted protected-finance, bullets/table, `Avoir`, and both long-document cases from the Stage-2E evidence. Do not restart broad candidate discovery unless that product-path verification exposes a model-level reason.

Evidence tarballs from the current generic task/translation checks intentionally have no `.sha256` sidecar files, but each script prints the archive SHA-256 for exact evidence identification. Preserve the exact fixture/evaluator/prompt material inside evidence where needed, normalize archive ownership metadata, and keep archive/delivery bookkeeping separate from model-quality conclusions.

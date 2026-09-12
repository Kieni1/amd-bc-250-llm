# BC-250 standalone quality checks

These checks are intentionally **separate from `bc250-revalidate`**. They are
operator-run candidate/quality experiments for the real BC-250 and must not be
interpreted as v1.0 release qualification. RPM builds remain GitHub workflow
work; these scripts do not build packages.

## Layout

- `history/` — the actual Batch 1–3D evidence scripts plus the short Ministral
  comparison recipe. They are retained for reproducibility.
- `task/` — one-candidate-at-a-time compact task screens. Each run compares the
  candidate against the package-owned LFM2.5 1.2B baseline without changing defaults.
- `translation/` — direct candidate screens first, then an optional authenticated
  Open WebUI integration screen for candidates that survive the direct screen.
- `utils/` — evidence inspection helper.

All scripts write evidence below `${BC250_QUALITY_ROOT:-$HOME/bc250-quality}` and
normally create a `.tar.gz` in `$HOME`; the OWUI mutation screen withholds its
tarball if credential/root-temp safety checks fail. `rc=3` remains a quality
failure rather than an infrastructure failure. The machine-facing scripts deliberately require
BC-250 services/tools and should not be run in generic build CI.

## Task candidate sequence

Use `10-candidate-screen.sh MODEL [ROUNDS]` for any future packaged `exp-*` task
challenger. The previous one-off wrappers were removed when their candidate
Modelfiles moved to the source-only graveyard. Default rounds: 3. The experimental
GGUF is
downloaded through the normal experiment catalog, then temporarily registered
on the dedicated task Ollama so baseline and candidate use the same task-lane
context/KV-cache/keep-alive policy. The temporary task registration is removed
when the screen exits. The main lane is unloaded before each candidate run so a
warm GPT-OSS model cannot overlap the experiment accidentally. A separate
coexistence test is required before any production task promotion.

The aggregate records overall, per-round and per-case results plus exact failed
responses. A quality failure remains `rc=3`; any other nonzero return code is an
infrastructure/restoration failure.

## Translation candidate sequence

Re-anchor the current evaluator with a short LFM reference, keep the already-tested
Ministral comparison short, then prioritize Hunyuan-MT and Translate-Gemma:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/14-lfm-direct-reference.sh
/usr/share/bc250-llm-server/quality-checks/translation/11-ministral-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/12-hunyuan-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/13-translate-gemma-direct.sh
```

Direct screening uses explicit source/target direction and a 1024-token default
output budget. Hunyuan-MT is tested with its upstream target-language prompt and
Translate-Gemma with a `CURRENT_SOURCE`-shaped exchange. The LFM reference does not
change production; it only provides an apples-to-apples comparator under the same
current evaluator. It is deliberately separate from Open WebUI integration. If a
candidate survives the direct screen, first run the repaired LFM OWUI
reference once, then run only the surviving challenger integration wrapper:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/23-lfm-owui-reference.sh
/usr/share/bc250-llm-server/quality-checks/translation/21-hunyuan-owui.sh
# or, if Translate-Gemma is the survivor:
/usr/share/bc250-llm-server/quality-checks/translation/22-translate-gemma-owui.sh
```

The OWUI check takes an exclusive mutation lock, saves the exact translation
preset and full Ollama-provider config in root-only `/run` files, and temporarily
adds an experimental candidate only to the existing main-provider allow-list when
that provider is restricted. Full provider config is never copied into evidence;
only recursively redacted structural snapshots are archived. The check verifies
effective base/preset visibility, preserves HTTP status and response bodies for
mutations/chat requests, captures per-request wall time and BC-250 telemetry, then
restores the preset and exact provider policy and verifies effective visibility
again. Evidence is scanned for the Open WebUI token and provider secrets before
archiving. A small `run-manifest.json` and runtime/model provenance make the result
reproducible. Restoration/telemetry/credential failures are infrastructure
failures. Translate-Gemma uses its dedicated auto-direction prompt. Do not use
Open WebUI interactively while it runs.

## Interpretation

- Do not promote a task model from score alone; prove coexistence with warm
  GPT-OSS and acceptable latency/memory afterward.
- A translation candidate must first beat the current LFM quality pattern, then
  pass the real OWUI integration check.
- Output-budget diagnostics are evidence, not automatic proof that a model is
  poor. The direct LFM comparison previously showed budget starvation.
- Do not weaken evaluators to turn genuine model errors into passes.

Before production translation promotion, use a separate broader 24–40 case corpus covering both directions, office prose, invoices/tables, IDs/dates/amounts, negation, formatting, proper nouns and source-language leakage. The 8-case short screen remains a screening gate, not promotion proof.

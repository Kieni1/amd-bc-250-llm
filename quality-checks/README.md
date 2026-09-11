# BC-250 standalone quality checks

These checks are intentionally **separate from `bc250-revalidate`**. They are
operator-run candidate/quality experiments for the real BC-250 and must not be
interpreted as v1.0 release qualification. RPM builds remain GitHub workflow
work; these scripts do not build packages.

## Layout

- `history/` — the actual Batch 1–3D evidence scripts plus the short Ministral
  comparison recipe. They are retained for reproducibility.
- `task/` — one-candidate-at-a-time compact task screens. Each run compares the
  candidate against the packaged Gemma 3 1B baseline without changing defaults.
- `translation/` — direct candidate screens first, then an optional authenticated
  Open WebUI integration screen for candidates that survive the direct screen.
- `utils/` — evidence inspection helper.

All scripts write evidence below `${BC250_QUALITY_ROOT:-$HOME/bc250-quality}`,
create a `.tar.gz` in `$HOME`, and preserve `rc=3` as a quality failure rather
than an infrastructure failure. The machine-facing scripts deliberately require
BC-250 services/tools and should not be run in generic build CI.

## Task candidate sequence

Run one batch at a time:

```bash
/usr/share/bc250-llm-server/quality-checks/task/11-lfm12b.sh
/usr/share/bc250-llm-server/quality-checks/task/12-minicpm5-2b.sh
/usr/share/bc250-llm-server/quality-checks/task/13-qwen3-1p7b.sh
/usr/share/bc250-llm-server/quality-checks/task/14-qwen38-2b.sh
```

The underlying `10-candidate-screen.sh MODEL [ROUNDS]` can be reused for any
packaged `exp-*` task challenger. Default rounds: 3. The experimental GGUF is
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

The OWUI check temporarily repoints only `bc250-office-translation`, verifies that
the selected stable live-preset fields contain only the intended candidate delta, disables background
title/tag/follow-up jobs, captures per-request wall time and BC-250 telemetry,
restores the exact original preset, scans evidence for the bearer token, and treats
restoration/telemetry/credential failures as infrastructure failures. The
Translate-Gemma wrapper uses its dedicated auto-direction prompt. Do not use Open
WebUI interactively while it runs.

## Interpretation

- Do not promote a task model from score alone; prove coexistence with warm
  GPT-OSS and acceptable latency/memory afterward.
- A translation candidate must first beat the current LFM quality pattern, then
  pass the real OWUI integration check.
- Output-budget diagnostics are evidence, not automatic proof that a model is
  poor. The direct LFM comparison previously showed budget starvation.
- Do not weaken evaluators to turn genuine model errors into passes.

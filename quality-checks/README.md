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
packaged `exp-*` task challenger. Default rounds: 3. It unloads the main lane
before and after each candidate run so a warm GPT-OSS model cannot overlap the
experiment accidentally. A separate coexistence test is required before any
production task promotion.

## Translation candidate sequence

Keep the already-tested Ministral comparison short, then prioritize Hunyuan-MT
and Translate-Gemma:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/11-ministral-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/12-hunyuan-direct.sh
/usr/share/bc250-llm-server/quality-checks/translation/13-translate-gemma-direct.sh
```

Direct screening uses the installed translation benchmark's explicit source and
target direction. It is deliberately separate from Open WebUI integration. If a
candidate survives the direct screen, run the integration check, for example:

```bash
/usr/share/bc250-llm-server/quality-checks/translation/20-owui-candidate-screen.sh \
  exp-hunyuan-mt-7b-mungert-q4-k-m \
  /usr/share/bc250-llm-server/quality-checks/translation/prompts/auto-direction-minimal.txt
```

The OWUI check temporarily repoints only `bc250-office-translation`, verifies the
live readback, disables background title/tag/follow-up jobs, restores the exact
original preset, scans evidence for the bearer token, and treats restoration
failure as infrastructure failure. Do not use Open WebUI interactively while it
runs.

## Interpretation

- Do not promote a task model from score alone; prove coexistence with warm
  GPT-OSS and acceptable latency/memory afterward.
- A translation candidate must first beat the current LFM quality pattern, then
  pass the real OWUI integration check.
- Output-budget diagnostics are evidence, not automatic proof that a model is
  poor. The direct LFM comparison previously showed budget starvation.
- Do not weaken evaluators to turn genuine model errors into passes.

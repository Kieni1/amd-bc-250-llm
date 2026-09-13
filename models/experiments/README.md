# Experimental model subtree

This directory contains helper logic for operator-selected comparison models. The
canonical **current model status, active experiment catalog, retirement reasons and
measured promotion evidence** live in [`../../MODELS.md`](../../MODELS.md). Do not
maintain a second status table here.

## Operator entry points

```bash
sudo bc250-model list experiments
sudo bc250-model install experiments
bc250-benchmark
```

Normal discovery comes from `models/modelfiles/exp-*.Modelfile`. Candidates that no
longer have a plausible promotion path move to `models/modelfiles-graveyard/`; that
directory is source-only and is not installed or discovered. In particular, the
retired task candidate `exp-qwen38-4b-distill-empero-q6-k` must not be confused with
the separate active general comparison `exp-qwen38-4b-empero-q6-k`.

For new comparisons, use the current scripts documented in
`docs/QUALITY-CHECKS.md`. Installation success is never promotion evidence: compare
quality, full-GPU residency, cold load, context scaling, temperature, memory/swap
pressure and sustained correctness on the real BC-250. A task candidate also needs
explicit coexistence evidence beside the warm main model before promotion.

## Adding or retiring an experiment

1. Add a checksum-pinned `exp-*.Modelfile` under `models/modelfiles/`.
2. Add the exact model ID and purpose to the canonical active catalog in `MODELS.md`.
3. Add or reuse a bounded quality screen only where the existing benchmark surface
   cannot answer the question.
4. In the Git repository (not the installed RPM), record consequential run evidence
   and the resulting decision under `development/` so a future cleanup does not erase
   why a candidate was rejected.
5. When retiring a manager-owned model, move its Modelfile to the source graveyard,
   add its canonical identity to `models/retired-models.json`, and update `MODELS.md`.

Do not weaken quality evaluators to keep a candidate active. Do not move a model out
of the graveyard merely because its raw benchmark score looks attractive; first read
the recorded rejection and its explicit retest conditions.

## Source-management caveat

Local-GGUF revisions may be commits, tags, branches or `latest`. Moving revisions
favor flexibility over reproducibility; `--refresh` deliberately fetches the source
again. Vision/OCR `hf.co/...` models are Ollama-managed when a separate projector is
required, because the current local Modelfile import path cannot safely reconstruct an
arbitrary main-GGUF + projector pair. Do not copy only the main GGUF into the managed
source tree and call it a restorable backup.

MTP/draft heads are a separate download-only llama.cpp workflow; see
[`../mtp/README.md`](../mtp/README.md). OCR behavior and measured status are described
in `MODELS.md`; use `bc250-ocr list` for the installed engines.

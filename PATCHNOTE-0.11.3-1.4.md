# BC-250 0.11.3-1.4 patch note

## Release identity

VERSION: `0.11.3`  
RPM Release: `1.4`  
Expected NVR: `bc250-llm-server-0.11.3-1.4`

This release closes the current source-side RAG integration tranche and records the completed
BC-250 RAG finalist decision while preserving the existing appliance architecture and resource
policy.

The Qwen3.8 candidate additions below are a pre-publication same-NVR source refinement. Any prior
1.4 source hash/artifact must therefore be distinguished from these final bytes; no hardware evidence
is silently transferred between same-NVR artifacts.

## Changes in 1.4

- Same-release pre-publication refinement: add bounded Qwen3.8 27B experiments while keeping all production model roles unchanged. `exp-qwen38-27b-ista-gsq-rco-iq3-xxs` is the 10.1 GB deployability/RAG-oriented text candidate at 16K with non-thinking sampling; the existing 11.8 GB IQ3_S entry is retuned as the quality-first main-model experiment at 8K with thinking-mode sampling.
- Add disabled download-only `qwen3.8-27b-ymq-xs-ti-mtp` (10.2 GB published GGUF) as a Qwen3.8 27B MTP challenger against the existing HauhauCS IQ2_M control (~10.32 GB), with matched 8K context and draft depth 2. This is catalog inclusion only, not BC-250 MTP qualification.

- Record the final RAG finalist evidence from exact installed `0.11.3-0.4`: both Gemma E4B and
  Qwen 9B were strong on broad direct retrieval and short authenticated Open WebUI RAG, but Gemma
  retained materially safer sustained-residency headroom. The production document/RAG role remains
  `bc250-office-documents` / `prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl`. Qwen stays available for
  its separate higher-quality general-office role.
- Restore the pre-benchmark Ollama residency **sets** without forcing `keep_alive=30m`; reloads now
  omit an explicit keep-alive so the main and embedding services apply their own configured/default
  lifetime policy. Exact remaining expiry time is not claimed or reconstructed.
- Rename the canonical RAG resident-session swap field from `cumulative_swap_growth_mib` to
  `swap_peak_delta_mib`, which accurately means peak observed swap minus starting swap.
- Reconcile development/release memory with current deterministic source validation and clarify the
  main-lane architecture: port 11434 is a warm interactive product-role lane, while GPT-OSS is the
  deep-reasoning and worst-case-memory production reference.
- Preserve the evaluator, Open WebUI preset resolution/readiness, safe MTP process-group cleanup,
  installer/maintenance UX and revalidation diagnostic changes from 1.1-1.3.

## RAG evidence carried into the decision

The broad fixed-retrieval campaign used 56 documents, 48 answerable cases, eight abstention probes,
two repetitions/model and Top-K 8. Both finalists achieved 96/96 target retrieval, 96/96
all-required-support retrieval, 8/8 abstention and no truncations. Known scorer false negatives were
subsequently fixed deterministically in package source; manually adjudicated effective scores are
kept as historical evidence rather than hard-coded expectations.

On the authenticated Open WebUI path, both models passed 36/36 short-session turns. In sustained
residency, Gemma completed 42/42 turns with about 2766 MiB minimum / 2770 MiB end-of-arm
MemAvailable, about 15 MiB swap growth and no safety/residency failure. Qwen remained semantically
correct before abort but fell to roughly 338 MiB minimum MemAvailable and reached the experiment's
configured 512 MiB safety floor after only a few subruns. This is the reason Gemma remains the
long-lived RAG default on the current 16 GiB profile.

The 512 MiB value above is the residency experiment's safety-abort setting. Whole-appliance
revalidation policy remains unchanged.

## Deliberate non-changes

- no change to the production RAG answer model; the new IQ3_XXS entry is an opt-in experiment and does not reopen the completed Gemma-vs-Qwen9B production decision;
- no first-class long-residency benchmark framework in this release; the production selection
  question is already answered, so additional framework work would need a new concrete product need;
- no change to the 128 MiB whole-appliance hard floor or the existing 512 MiB informational
  tight-headroom diagnostic;
- no production model bytes, Open WebUI desired-state IDs or lane-topology changes; experimental
  Modelfiles/catalog entries change only for the bounded Qwen3.8 candidates described above;
- no attempt to reconstruct exact pre-benchmark model expiry timestamps that Ollama does not expose
  as a reliable restoration contract.

## Evidence boundary

The RAG finalist campaign is real-device evidence for exact installed
`bc250-llm-server-0.11.3-0.4.fc44.x86_64`. It justifies the current model-role decision, but it does
not make 1.4 exact-source hardware-qualified. Real arbitrary office PDFs/Tika/OCR edge cases and
collection update/delete/re-import workflows remain a separate product-evidence gate.

## Source validation

- `make validate`: **402/402 PASS**
- Python `compileall` for `cmd`, `models` and `tests`: PASS
- `bash -n` across packaged/source shell scripts: PASS
- `models/modelctl.py`: source mode remains `0755`
- Ruff/ShellCheck: not run in this environment
- RPM/SRPM build: external / GitHub-owned
- exact installed 1.4 BC-250 runtime/hardware qualification: not yet run

# BC-250 current-work handover — 0.12.2-0.6 final integration

## Release identity

```text
VERSION       0.12.2
RPM Release   0.6
NVR           bc250-llm-server-0.12.2-0.6
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full
Governor      0.4.13
Revalidation  v4.6
```

This handover supersedes earlier 0.6 drafts that treated Ornith as a mandatory install prerequisite or the Translate-Gemma `sollten -> doivent` behavior as an unresolved release blocker.

## Final integrated product decisions

### Structured output

Use role-specific explicit policy, not prompt heuristics:

- **Standard:** strict structured requests supply the exact JSON schema as request `params.format` and `temperature=0.0`; do not override `think`. Final focused evidence was 200/200 strict exact.
- **Documents:** strict structured requests supply the exact JSON schema as request `params.format` and `temperature=0.0`; leave normal thinking unchanged. Focused evidence was 25/25 and no larger confirmation is required.
- **Advanced:** normal `Office - Advanced` remains `think=true`; new explicit `Office - Advanced Structured` uses the same Qwen3.5 9B base, same 6144-token budget and same samplers with only `think=false`.
- **Deep:** unchanged; do not introduce `think=false`.

Open WebUI 0.11.4 already performs the required parameter merge/translation. Do not patch generic `payload.py`, infer structured intent from prompt text, or disable reasoning globally.

### Translation

Production remains `prod-translate-gemma4-sub-e4b-17s-q4-k-xl`. The native model can strengthen German recommendation `sollten` into French obligation `doivent`; keep the package's clause-local modality guard fail-closed. This underlying model limitation is now documented and accepted rather than release-blocking.

The EuroLLM challenger is closed and moved to the source graveyard:

```text
exp-eurollm9b-instruct-2512-mradermacher-q4-k-m
```

Round 1 is sufficient: EuroLLM fixed `sollten -> devraient` (2/2) but reproducibly regressed German `muss nicht` to English output (0/2). Retain Translate-Gemma; no Round 2 is justified and EuroLLM is not part of the active catalog.

### Agent

Agent is an add-on. Do not install Ornith as part of the core fresh/model-only baseline. When no Agent model is installed, revalidation reports optional coverage unavailable/skipped and overall coverage may be PARTIAL without failing core infrastructure. If Agent is installed, exclusive-lane service/API/topology failures remain infrastructure failures.

### Benchmark reporting

Generation summary now includes:

- `cold_load_s` separate from `cold_wall_s`;
- 4K/16K deep-context target and actual prompt-token aggregates;
- thermal mean/min/max/first/last/drift and total wall time;
- selected-lane completeness checks.

These are measurements/coverage checks only. No synthetic board score or device ranking is introduced. Native PSI/OOM enrichment remains optional future work.

### Installer completion

Keep the completion footer compact:

```text
OVERVIEW

Further setup
  Open WebUI:    sudo bc250 openwebui-setup init
  Maintenance:   sudo bc250 maintenance --help
  Documentation: /usr/share/doc/bc250-llm-server/

Storage
  sudo bc250 storage -h

NEXT STEPS

CU routing
  sudo bc250-cu-live-manager

Models
  sudo bc250 install --models-only

Validation
  sudo bc250 verify
  sudo bc250 revalidate start
  sudo bc250-40cu status

Benchmark
  bc250 benchmark --help
```

`NEXT STEPS` remains amber/yellow.

### Retired model state

Qwen3.6 35B remains graveyard/retired only and must not appear in active discovery. No unqualified replacement is promoted merely to fill that catalog slot.

## Remaining exact-device closure

After source/RPM build, only focused release confirmation is justified:

1. install exact 0.12.2-0.6; record `rpm -V`, runtime pins, kernel and final normal topology;
2. verify compact completion rendering and CU guidance on a real terminal;
3. verify Agent absence yields explicit optional coverage skip/partial, not infrastructure failure; if Agent is installed, verify normal exclusive-mode qualification/restoration;
4. verify the new Advanced Structured preset is visible to an ordinary user, maps to the expected Qwen3.5 base and effective `think=false`; prove normal Advanced remains `think=true`;
5. integrated strict-structured regression: Standard schema+temp0, Documents schema+temp0, Advanced Structured `think=false`, Deep unchanged, with type-sensitive exact JSON validation and controls for ordinary non-structured chat;
6. do not continue EuroLLM qualification; Round 1 found a reproducible language regression and production Translate-Gemma remains selected;
7. run one final whole-appliance revalidation and preserve cleanup/restoration/CU evidence.

Do not replay closed Deep/RAG/Tika/MTP/title-tag or broad native model campaigns merely for closure.

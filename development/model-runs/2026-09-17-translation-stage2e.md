# Translation Stage-2E configuration decision — 2026-09-17

Evidence class: REAL BC-250 + authenticated Open WebUI product path.

Evidence archive:

`bc250-translation-stage2e-config-bundle-20260917-232916.tar.gz`

SHA-256:

`63fa90ea1187b7c878da0067d3f0be91e5a9e9faadbb4c919c7ed2a374f80c1c`

## Selected candidate configuration

```text
model:       exp-translate-gemma4-sub-e4b-17s-q4-k-xl
prompt:      explicit-direction v1
think:       omitted / not forced
max_tokens:  2048
```

Exact system prompt SHA-256:

`c12ccfb4694a444dff66400141c6ae8eaebb66195e98851ddc5b562cbbdb57db`

Direction is not hardcoded into the system prompt. The DE→FR and FR→DE user wrappers
name the direction explicitly and place the unmodified source immediately after
`[CURRENT_SOURCE]\n`.

## Result

- hard automatic: 10/16;
- DE→FR: 2/8;
- FR→DE: 8/8;
- correct target language: 16/16;
- advisory semantic dimensions: 72/78;
- mean wall: 6.91 s;
- p95 wall: 23.01 s;
- minimum MemAvailable: 8362 MiB.

The 1024-token baseline truncated the long FR→DE case at exactly 1024 output tokens.
With 2048, that case produced 1376 output tokens and completed correctly.

Forcing `think:false` is rejected: it reproducibly leaves most of the focused FR→DE
`Avoir` case in French. The selected configuration leaves thinking unspecified.

## TIR comparison

TIR baseline also reached 10/16 but only 65/78 semantic dimensions, varied across every
repeated case, averaged 10.60 s and reached 5871 MiB minimum MemAvailable. It also
retains terminology/source-leakage/table instability and does not solve protected
financial-format preservation. Close TIR as the normal deployment choice under current
evidence.

## Remaining integration caveats

- Translate-Gemma localizes protected DE→FR financial typography such as `8.1 %` to
  `8,1 %` and can reorder/localize CHF formatting despite explicit preservation text.
- One targeted DE→FR bullet case omits the trailing ordinary-language line.
- The focused `Avoir AV-19` result becomes `AV-19:` rather than an explicit `Gutschrift`.
- Numeric evaluator parsing must treat one-decimal locale forms such as `8,1` as 8.1,
  not 81.

## Integration decision

Add package-owned DE→FR and FR→DE candidate roles that reproduce the exact tested
contract, but retain the existing LFM translation production/default role. Do not run
another broad model campaign. Requalify only the integrated final path using canonical
sanity plus the targeted protected-finance, bullets/table, `Avoir`, and both long
translation cases. Promote only after that bounded gate passes.

Preset/provider restoration was verified for every Stage-2E configuration. Privacy
scans passed and serious-warning evidence was empty.

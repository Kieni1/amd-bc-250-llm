# MTP reference material

This directory preserves the compact methodology needed to reproduce or audit the final 2026-09-19 BC-250 MTP campaign without turning the RPM into a benchmark-kit distribution. These files are source/development references and are not runtime appliance payload.

## Current durable evidence

The package's authoritative current conclusion is:

`development/model-runs/2026-09-19-mtp-final-qualification.md`

That record contains the reviewed candidate results, corrected draft-depth conclusions, exact runtime identity, safety interpretation and remaining optional tests.

## Preserved external reference kit

The specialist campaign used the external archive:

```text
bc250-mtp-reference-kit-v3.tar.gz
SHA-256: 16251f8f5bd6a753921f593897fcee3be7cbade26d0a1b83c4b8c2d9f5b7469b
```

The tarball itself is deliberately not vendored into this source tree or installed by the RPM. The handover/reference archive may retain it separately.

Included here:

- `BC250_MTP_EXECUTION_GUIDE_v3.md` — maps each specialist command to the experimental question it answers and documents the reviewed campaign contract. The source-tree copy normalizes the original operator-specific rsync destination to placeholders; experimental semantics are unchanged.
- `bc250-mtp-reference-kit-v3-validation.txt` — validator output for the supplied reference kit. It records syntax/compile/static/mock checks only; it does **not** claim BC-250 inference. ShellCheck was unavailable and is not claimed.

Important distinction: the specialist reference campaign intentionally drains ordinary Ollama residency for isolated measurements and does not automatically rewarm it. That is an experiment-specific isolation rule, not the normal package benchmark/restoration contract.

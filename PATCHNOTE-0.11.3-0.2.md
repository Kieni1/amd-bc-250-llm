# Patch note — 0.11.3-0.2

## Summary

`0.11.3-0.2` is a focused model-lifecycle correction and MTP usability release. It
keeps the 0.11.3 command/state redesign and revalidation v4.2 unchanged while repairing
three contract defects found during review of the central model manager.

## Corrected model-manager behavior

- `bc250-fetch-mtp` now dispatches to `bc250-model apply mtp --include-disabled` instead
  of the removed pre-0.11.3 `install mtp` grammar.
- MTP entries keep the same global display/selection index in `list mtp --all` and
  `list all --all`.
- `--revision` and `--sha256` are enforced against the complete selection before a
  category-`all` operation is split into per-category groups; one override can no longer
  leak across multiple selected models.
- Secondary lifecycle surfaces are reconciled too: the installed-assets smoke uses
  unprivileged catalog `list`, current handovers agree on RPM Release `0.2`, and the
  README/TLDR/model/specialist guidance all expose the explicit `bc250-fetch-mtp` route.
- Regression coverage now protects current release metadata, MTP opt-in discoverability,
  and the no-`sudo` contract for active read-only `list`/`path` callers.

## MTP operator workflow

MTP remains download-only and disabled from generic convergence. The supported explicit
test preparation path is:

```bash
bc250-model list mtp --all
sudo bc250-fetch-mtp qwen3.6-27b-mtp
sudo bc250-model status mtp qwen3.6-27b-mtp --include-disabled --verbose
LLAMACPP=/path/to/llama-server bc250-run-mtp 27b
```

With no selection, `sudo bc250-fetch-mtp` presents both packaged MTP candidates.
`bc250-run-mtp` now lists disabled candidates in its usage path and prints the exact
fetch command when the selected GGUF is absent. Generic `apply all` still excludes MTP.
No MTP definition is enabled or promoted by this release.

The runtime boundary is unchanged: the RPM does not ship llama.cpp, and MTP still needs
real BC-250 testing with exact runtime/build/flags, completion integrity, draft acceptance,
answer quality, memory/swap and stability evidence.


## Validation

Current source validation after the corrections:

```text
make validate
  repository/RPM preflight   PASS
  packaged shell syntax      PASS
  deterministic tests        367 / 367 PASS

all repository .sh files     bash -n PASS
packaging/bc250 dispatcher    bash -n PASS
touched Python               compile PASS
```

Ruff and ShellCheck were not available here. RPM build/install and real BC-250 MTP
runtime qualification remain external/device work.

## Release identity

```text
VERSION:      0.11.3
RPM Release:  0.2
Harness:      v4.2
```

Expected NVR: `bc250-llm-server-0.11.3-0.2`.

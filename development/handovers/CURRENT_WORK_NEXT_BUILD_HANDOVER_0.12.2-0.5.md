# BC-250 current work / next-build handover — 0.12.2-0.5

## Identity

```text
VERSION       0.12.2
RPM Release   0.5
NVR           bc250-llm-server-0.12.2-0.5
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full / TIKA_SERVER_VERSION=4
Governor      0.4.13
Revalidation  v4.6
```

## Implemented source delta

- Guided OWUI convergence is safety-gated: rollback boundary -> private/local OWUI readiness -> authenticated package apply/status -> install/enable/verify OWUI boot publication -> enable nginx. Any failure leaves publication held and returns degraded/nonzero.
- Advanced remains `think=true` with the established samplers and moves from the proven 4096 mechanism to a bounded `max_tokens=6144` candidate. Device qualification must prove effective `options.num_predict=6144`.
- Clean reasoning-only ceiling exhaustion without visible output is `INCOMPLETE / production-contract-budget`; repetition/degeneration remains a quality defect.
- Translation integrity is ordered, clause-local and polarity-aware: negated recommendations, `muss nicht`/no-obligation, same-clause modality order and prohibition are preserved fail-closed. German finite-modal negation is bounded to the text after that modal and before the next protected modal, so a later `darf nicht` cannot reclassify an earlier `muss`; preceding `nicht` is used only for participial forms such as `nicht erlaubt` / `nicht verpflichtet`. FR→DE additionally recognizes positive German `kann/können/kannst/könnt` as the counterpart of positive French `pouvoir`, while negated `können ... nicht` is not blindly treated as normative prohibition.
- Deep residency is unchanged and already strongly qualified on exact 0.12.2-0.4: verified task/embed eviction, `keep_alive=2m`, second-request reuse, idle expiry and cold reload.

## Evidence closures

- Tika 4 genuine DOCX: real bullets serialize as `· item`; heading/table/list content and retrieved bullet/table facts are intact. No RPM workaround.
- Repeated title/tag persistence: titles and tags persisted across single-model and Advanced+Deep runs; no task topology/config change.

## Exact-device work after build/install

1. Focused translation regression using the exact FR source / faithful German target plus unsafe negative cases.
2. Focused Advanced 6144 propagation + completion-quality matrix.
3. One final full OWUI release qualification after desired-state convergence.

Do not replay the old native long-run, Tika or title/tag campaigns solely for closure.

## Workbench continuity

The transient worktree is not authoritative. Continue only from the newest explicit workbench checkpoint SHA (or an exact Git commit SHA when one exists). After each meaningful source batch, create a non-release checkpoint ZIP whose own `WORKBENCH-STATE.json` records predecessor SHA, release/NVR, changed files, validation and open work; record the checkpoint SHA externally as well. Diff it against its predecessor and inspect deleted regression tests/guards before new edits. Keep workbench state metadata out of release/source-package payloads. If the newest checkpoint is unavailable, do not reconstruct silently from an older release archive.

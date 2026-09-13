# BC-250 development workflow handover

This handover is deliberately **versionless**. It defines how to work on the project,
not what the current release happens to contain. Always inspect the newest supplied
source first.

## Authority

Use, in order:

1. current user instruction;
2. newest supplied source/package archive;
3. real-device evidence from the exact installed package;
4. current validation evidence;
5. current handovers/decision records;
6. older logs/chats/patches.

Never silently merge an older handover assumption into newer source.

## Validation ownership

Do not try to run checks that are unavailable in the current environment.

```text
GitHub       RPM/package builds
workstation  Ruff and developer linting as configured by the user
BC-250       hardware, services, Ollama/models, Open WebUI, WOL/power, real qualification
```

Run source/unit/syntax checks locally only when the required tools are actually present.
Do not repeatedly probe for unavailable Ruff, ShellCheck, rpmbuild or hardware tooling.
Always state exactly what ran and exactly what did not.

Never say “all checks passed” if only a subset was available.

## Quality integrity

Never weaken quality thresholds, evaluators, restoration checks, secret hygiene,
verifier thresholds or return-code semantics merely to get green output.

Keep separate:

```text
model-quality defect
evaluator defect
package/integration defect
operator/environment state
```

If the check is wrong, demonstrate why and fix it deterministically.

## Real-device testing

Work one bounded evidence-producing batch at a time. Prefer a read-only baseline before
mutation. Let the result determine the next batch.

Do not provide multiple speculative destructive stages before seeing the first result.
Restore state before changing test lanes.

Preserve downloaded GGUFs whenever practical. Prefer validated-source reuse,
re-registration and XFS dedupe over deletion/redownload. Do not manually delete Ollama
blobs or run source pruning merely to save space when package/Ollama lifecycle behavior
covers the case.

## Releases and source refreshes

The project is pre-v1.0. `VERSION` and RPM `Release` advance independently.

When the user asks for a release:

1. integrate only justified changes;
2. reconcile affected docs/changelog;
3. bump the requested metadata;
4. run available validation;
5. remove temporary caches/build debris;
6. create the full source ZIP;
7. provide SHA-256 and exact validation boundary.

When the user explicitly asks to regenerate/source-refresh **without a metadata bump**,
leave `VERSION` and RPM `Release` unchanged and document that the source archive changed.
Avoid changing installed payload merely to record a Git-only coordination refresh.

Full ZIP only when explicitly requested. For “files only”/targeted changes, provide the
repo-relative changed files.

## Git commit messages

Return reasonably atomic commands in this form:

```bash
git commit -m "<short imperative message>" \
  path/to/file1 \
  path/to/file2
```

Prefer functional fix + its tests together, operator UX with its tests/docs, separate
packaging changes where useful, and release metadata/changelog last. Do not create a
giant “update stuff” commit.

## Code quality

Prefer small changes and existing package interfaces. Avoid new daemons, databases,
frameworks and unnecessary dependencies when shell/Python/systemd already solves the
problem safely.

Keep boundaries clear: dispatchers dispatch, helpers implement focused behavior, and
safety policy stays in the component that owns it.

Regression tests should prefer observable behavior over exact implementation strings.
Documentation tests should guard demonstrated drift classes, not parse every sentence.

## Documentation

Audit only affected docs. Runnable copy/paste commands belong in `bash` fences with
correct privilege. Inline code normally names an interface rather than instructing the
operator to run it.

Canonical current interfaces should not be duplicated across several documents when a
link will do. Preserve durable negative results in `development/DECISIONS.md` or
`development/model-runs/` with explicit retest conditions.

## Raspberry Pi / maintenance boundary

The Pi is primarily an availability/power companion, with backup secondary:

```text
Pi       WOL, wake schedule, office-readiness observation, optional safe-shutdown request,
         optional read-only backup pull
BC-250   office service, safe-shutdown decision, after-hours policy, local backups,
         optional restricted export
```

The Pi must not infer idleness and use raw poweroff. Use the package-maintained safe
shutdown interface. Do not expose internal Open WebUI/Ollama ports merely for Pi health.

## Evidence discipline

Separate:

```text
Observed facts
Interpretation
Proposed change
```

When something is inferred, say so. Include exact commands, package/NEVRA, model IDs,
settings, result artifact names/SHA-256 and restoration state when relevant. Never bundle
GGUFs or credentials.

## Main vs specialist chats

Main integration owns release policy and cross-stream decisions. Use temporary specialist
chats for bounded quality work such as translation, RAG, agentic, main-lane or MTP.
Specialists do not independently bump versions or change production defaults unless main
integration explicitly asks.

After implementing a review, report what changed, deliberate deferrals, validation run/
not run and residual risk. Do not re-present the whole audit.

## Fresh-chat instruction

> Work from the newest supplied BC-250 source archive as authoritative. Do not attempt
> unavailable checks: GitHub owns RPM/package builds, the workstation owns Ruff, and the
> BC-250 owns hardware/runtime qualification. State exactly what was tested. Keep patches
> small, preserve GGUFs, never weaken quality/restoration thresholds, and use one bounded
> hardware batch at a time. Read `development/VALIDATION-MATRIX.md`,
> `development/TESTING-STRATEGY.md`, and the relevant current source docs before proposing
> new qualification work. Return atomic Git commit commands when requested.

# BC-250 validation matrix — current release line

Current release identity: `bc250-llm-server-0.14.1-1.9`.

This matrix tracks only the evidence needed to move the current line forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.9` assigned consistently | keep unchanged until package-only revision or next product version |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and any bounded cleanup |
| Changed 1.9 source checks | focused model-catalog/installer plus managed-document chunk/topology/review regressions and syntax checks PASS | run the full release gate before selecting a build |
| Full source suite | not used as the edit-loop oracle; 1.8 remains historical baseline only | run normal release-gate validation before authoritative build selection |
| RPM `%check` | pending for 1.9 | must pass unprivileged in the Fedora 44 SRPM rebuild |
| Source0/spec freeze | tracked-source contract implemented | freeze exact 1.9 inputs in selected build |
| RPM payload | package contract implemented | must pass on built RPM |
| rpmlint | blocking configured package gate | any unfiltered finding blocks artifact evidence; fix the package or document a genuine appliance-specific false positive |
| Authoritative SRPM rebuild | hard release gate | frozen SRPM must rebuild once in an isolated topdir; those exact rebuilt binaries become the artifacts |
| GitHub authority | explicit selected `workflow_dispatch` run | capture `release-evidence.json` + `release-selection.json` |
| Runtime/UI baseline | Ollama `0.40.8` + Open WebUI `0.12.3` unchanged | focused exact-1.9 model-installer/MTP UX smoke; do not reopen proven tuning/topology without evidence |
| Managed Documents correctness | 1.9 adds fail-closed multi-chunk assembly validation, readiness-window Agent cleanup and explicit review result state | rerun clean synthetic multi-chunk DOCX plus intentional unreachable-Agent/cleanup and review-state checks |
| Exact-RPM core functionality | 1.8/1.7.1 provide unchanged-boundary baseline evidence | run normal new-build health/verify plus explicit MTP overview/selection safety and focused Managed Documents regression |
| Product-roadmap baseline | 1.9 unifies MTP discovery/explicit preparation and closes 1.8 Managed Documents acceptance defects without changing runtime tuning | after acceptance, return to measurable document/retrieval and German–French workflow quality |

## Current stop conditions

### Blocking current-release coherence

Stop release creation for:

- inconsistent Version/Release/source identity;
- dirty/unbound authoritative Git source;
- current operator/release guidance contract drift;
- development-scope consistency failure;
- Ruff or ShellCheck failure;
- Source0/spec integrity failure;
- package-critical `%check` failure;
- configured rpmlint failure;
- RPM payload mismatch;
- authoritative frozen-SRPM rebuild failure, or failure to publish its exact rebuilt binaries, in the release environment;
- missing/ambiguous artifact identity.

### Advisory/historical material

Do not stop artifact production solely for:

- archive-only wording or historical evidence prose;
- unchanged historical development-scope hashes;
- unrelated noncritical behavioral findings from the broad advisory suite;
- historical campaign expectations.

Current operator/release guidance is not "documentation-only" when it defines release or safety behavior; contradictions there are blocking coherence defects.

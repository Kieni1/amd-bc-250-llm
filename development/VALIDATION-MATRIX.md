# BC-250 validation matrix — current release line

Current release identity: `bc250-llm-server-0.14.1-1.2`.

This matrix tracks only the evidence needed to move the current line forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.2` assigned consistently | keep unchanged until package-only revision or next product version |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and any bounded cleanup |
| Release preflight | source/release-pipeline gate available | rerun on final source before authoritative build |
| Full source suite | broad existing suite retained | all modules should pass or have explicit advisory classification |
| RPM `%check` | bounded package-critical subset | must pass unprivileged in Fedora 44 build |
| Source0/spec freeze | tracked-source contract implemented | freeze exact inputs in selected build |
| RPM payload | package contract implemented | must pass on built RPM |
| rpmlint | blocking configured package gate | any unfiltered finding blocks artifact evidence; fix the package or document a genuine appliance-specific false positive |
| SRPM isolated-topdir rebuild | hard release gate | must pass in the release environment |
| GitHub authority | explicit selected `workflow_dispatch` run | capture `release-evidence.json` + `release-selection.json` |
| Exact-RPM core functionality | pending | run small BC-250 smoke on selected RPM |
| Product-roadmap baseline | pending device smoke | freeze known-good stock-core baseline, then proceed directly to RAG/document, DE↔FR translation and local-assistant work; simplify only where it removes concrete risk |

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
- isolated SRPM topdir rebuild failure in the release environment;
- missing/ambiguous artifact identity.

### Advisory/historical material

Do not stop artifact production solely for:

- archive-only wording or historical evidence prose;
- unchanged historical development-scope hashes;
- unrelated noncritical behavioral findings from the broad advisory suite;
- historical campaign expectations.

Current operator/release guidance is not "documentation-only" when it defines release or safety behavior; contradictions there are blocking coherence defects.

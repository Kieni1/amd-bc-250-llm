# BC-250 validation matrix — current release line

Current release identity: `bc250-llm-server-0.14.1-1.8`.

This matrix tracks only the evidence needed to move the current line forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.8` assigned consistently | keep unchanged until package-only revision or next product version |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and any bounded cleanup |
| Release preflight | `27/27` PASS on the final 1.8 source candidate | repeat in the authoritative Fedora 44 build context |
| Changed 1.8 source checks | revalidation, Managed Documents v2, support/CLI and upstream-patch regressions PASS; live sandbox support-bundle creation/self-verification also PASS | repeat package/device checks on the exact selected RPM |
| Full source suite | `692/692` PASS across 24 deterministic modules; package-critical subset `151/151` PASS | retain exact results in the selected build and rerun package `%check` |
| RPM `%check` | pending for 1.8 | must pass unprivileged in the Fedora 44 SRPM rebuild |
| Source0/spec freeze | tracked-source contract implemented | freeze exact inputs in selected build |
| RPM payload | package contract implemented | must pass on built RPM |
| rpmlint | blocking configured package gate | any unfiltered finding blocks artifact evidence; fix the package or document a genuine appliance-specific false positive |
| Authoritative SRPM rebuild | hard release gate | frozen SRPM must rebuild once in an isolated topdir; those exact rebuilt binaries become the artifacts |
| GitHub authority | explicit selected `workflow_dispatch` run | capture `release-evidence.json` + `release-selection.json` |
| Runtime/UI baseline | Ollama `0.40.8` + Open WebUI `0.12.3` carried unchanged from the completed 1.7.1 device baseline | focused exact-1.8 smoke on changed boundaries; do not reopen proven tuning/topology without evidence |
| Exact-RPM core functionality | 1.7.1 completed the broad real-device baseline; 1.8 changes qualification, document preparation/status/review and CLI/support surfaces | run focused changed-boundary acceptance plus final health/verify/topology/integrity checks |
| Product-roadmap baseline | 1.8 implements Managed Documents v2 and qualification correctness | after acceptance, prioritize measurable document/retrieval and German–French workflow quality |

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

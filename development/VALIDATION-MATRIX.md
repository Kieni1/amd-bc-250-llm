# BC-250 validation matrix — current release line

Current release identity: `bc250-llm-server-0.14.1-1.7.1`.

This matrix tracks only the evidence needed to move the current line forward. Detailed historical qualification remains in Git history and compact handover archives; it does not transfer PASS status to changed bytes.

| Area | Current state | Next evidence |
|---|---|---|
| Release identity | `0.14.1-1.7.1` assigned consistently | keep unchanged until package-only revision or next product version |
| Clean-core architecture | active GFX/private-RADV/package-owned patched-kernel surface absent | maintain absence during product work and any bounded cleanup |
| Release preflight | `27/27` source preflight PASS | rerun unchanged in the authoritative build context |
| Full source suite | `687/687` PASS across 24 module-isolated test modules | keep as source evidence; rerun if source changes |
| RPM `%check` | `148/148` PASS across the 8 declared source modules | must pass again unprivileged in the Fedora 44 SRPM rebuild |
| Source0/spec freeze | tracked-source contract implemented | freeze exact inputs in selected build |
| RPM payload | package contract implemented | must pass on built RPM |
| rpmlint | blocking configured package gate | any unfiltered finding blocks artifact evidence; fix the package or document a genuine appliance-specific false positive |
| Authoritative SRPM rebuild | hard release gate | frozen SRPM must rebuild once in an isolated topdir; those exact rebuilt binaries become the artifacts |
| GitHub authority | explicit selected `workflow_dispatch` run | capture `release-evidence.json` + `release-selection.json` |
| Runtime/UI baseline | Ollama `0.40.8` + Open WebUI `0.12.3` carried unchanged from 1.7 | bounded exact-1.7.1 runtime/UI smoke; investigate only if structural cleanup changes observable behavior |
| Exact-RPM core functionality | 1.7 is the source/behavioral regression baseline; 1.7.1 bytes still require exact-artifact acceptance | run the structural cleanup regression from `TESTING-STRATEGY.md`, including removed-command absence and reboot persistence |
| Product-roadmap baseline | cleanup release pending exact-RPM smoke | after acceptance, proceed to 1.8 Managed Documents v2 rather than extending cleanup scope |

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

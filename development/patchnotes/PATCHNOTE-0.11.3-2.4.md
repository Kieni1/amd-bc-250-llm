# 0.11.3-2.4

Expected NVR: `bc250-llm-server-0.11.3-2.4`

Bounded source release after exact-2.3 operations acceptance and consolidated Open WebUI product-path investigation.

## Implemented

- Patch the pinned CU live manager's interactive CPU-core-unlock reboot prompt to use
  `/usr/sbin/reboot` instead of `systemctl reboot`, matching the BC-250 reboot invocation proven
  reliable on target hardware.
- Preserve the upstream interaction contract: interactive CPU unlock still asks whether to reboot;
  `--yes` remains non-rebooting and only tells the operator to reboot when ready.
- Keep the fix in the existing pinned-upstream patch rather than copying/forking the live-manager
  source or adding a reboot abstraction.
- Record exact installed 2.3 targeted operations acceptance, including clean RPM verification,
  topology/status/verifier UX, successful baseline-aware identity restore, clean Tika restart
  telemetry, supported reboot reconstruction, healthy 40/40 routing and final authenticated 54/0/0.
- Extend the existing Open WebUI desired-state contract rather than adding another configuration
  layer: Arena is persisted off; external OpenAI/direct/code execution/interpreter/memories/community
  sharing remain persisted off; upload size/count/extensions are converged through supported APIs.
- Keep the five production base models plus the dedicated task model active for package roles/tasks
  while adding package-owned `meta.hidden=true` workspace overrides so the ordinary selector remains
  focused on curated office roles.
- Make authenticated Open WebUI status detect drift in these application/upload/hidden-model values;
  allowed-extension ordering is canonicalized so harmless API ordering changes do not create drift.
- Clarify exclusive-agent UX without adding transition state: Open WebUI remains reachable and may keep
  normal roles listed while their backends are intentionally unavailable until normal mode is restored.
- Record the pinned Open WebUI v0.11.3 OpenAI-style adapter boundary instead of carrying a container
  fork: root `max_tokens` is not a reliable Ollama cap, reasoning-token accounting can report zero despite
  reasoning content, and length termination can surface as `finish_reason=stop`. Package-owned hard caps
  use nested `options.num_predict`; the separately tested preset `params.max_tokens` path is unchanged.

## Deliberately unchanged

- 40-CU routing/persistent-mode semantics.
- Open WebUI readiness architecture; existing package commands already use HTTP/API readiness where
  application readiness matters. Curated presets/providers/task/translation/RAG behavior is otherwise
  unchanged.
- No custom Arena pool, model-order/default preference layer, CORS redesign, extra provider/service,
  generic Open WebUI configuration framework, or vendor patch for an unsupported external OpenAI-style
  API surface is added.
- Firewall/listener policy, backup/prune architecture, RAG, MTP, translation and Pi/companion paths.
- No attempt is made to diagnose or reproduce the deeper cause of the device-proven unreliable
  `systemctl reboot` invocation.

## Evidence boundary

Exact installed `0.11.3-2.3` is device-qualified for the targeted operations fixes recorded in
`development/model-runs/2026-09-20-installed-0.11.3-2.3-operations-acceptance.md`.

This 2.4 tree is source-validated and frozen below. Exact-installed-2.4 RPM/device acceptance is not
claimed until a built package is installed on the BC-250.

## Source validation

- Repository/RPM preflight: **PASS**.
- Complete deterministic suite: **447/447 PASS** when split by module. The monolithic validation
  command exceeded the execution window while tests were still passing, so the identical suite was
  completed in bounded module groups rather than reducing coverage.
- `bash -n`: **64/64 PASS**.
- Python compileall: **PASS**.
- Open WebUI desired-state/model/function JSON parse: **PASS**.
- Deterministic Source0 regeneration/tree equivalence: **PASS (305 files, contents and modes)**.
- RPM/SRPM build and exact-installed 2.4 device acceptance: **not run / external gates**.


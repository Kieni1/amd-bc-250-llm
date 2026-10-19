# Package gate and resilience qualification

Package-gate and resilience authority is bound to the exact installed package, running kernel and
qualification-relevant generic configuration so evidence cannot be silently reused after those inputs
change. Evidence created under an incompatible schema is not resume-compatible. The authoritative
result taxonomy is:

```text
0    PASS / ACCEPT
2    harness / infrastructure / cleanup failure
3    complete with product / quality defect
4    incomplete / evidence gap / review
5    safety / security stop
130  interrupted
```

## Authoritative package gate

Create the ordinary package gate from the exact candidate RPM installed on the
appliance:

```bash
sudo bc250 package-gate capture \
  --candidate-rpm /path/to/candidate.rpm \
  --token-file /var/lib/bc250-llm-server/secrets/openwebui-admin.key
```

`--output DIR` chooses a specific evidence directory. `--source-artifact FILE` can
also bind the gate to an SRPM or source archive. There is intentionally no
operator-supplied result flag: PASS is derived from the candidate/installed RPM
identity, `bc250 verify`, `rpm -V`, actual failed-unit rows, normal topology,
Tika 4.1 service/version/extraction checks, one bounded authenticated Open WebUI
RAG ingest/retrieve smoke with cleanup, and a high-confidence secret scan.

The gate directory contains `gate.json`, raw evidence, and a closed
`SHA256SUMS`. The clean core uses `bc250.package-gate.v3` and records a
`qualification_identity` containing the exact installed RPM, running kernel and
qualification-relevant configuration-tree hashes. Any unlisted/missing file,
checksum mismatch, unknown schema, non-PASS authoritative result, or later
package/kernel/configuration identity drift is rejected by the resilience manager.

## Tika 4.1 qualification boundary

The package pins `apache/tika:4.1.0-full` by immutable OCI digest. The package
gate keeps the refresh qualification intentionally small:

1. `tika.service` must be active.
2. Open WebUI must resolve the private `tika` alias.
3. `http://tika:9998/version` must report Tika 4.1.0.
4. A deterministic text marker must round-trip through the `/tika` extraction endpoint.
5. `bc250 benchmark owui-rag bc250-office-documents` performs one synthetic
   ingest/retrieve path and its built-in cleanup.

Do not restart a broad RAG/model tournament solely for this dependency refresh.

## Resilience manager

The manager consumes a closed package gate plus a small JSON plan whose lane
commands use argv arrays (never shell strings):

```json
{
  "schema": "bc250.resilience-plan.v1",
  "refresh_managed_swap": true,
  "lanes": {
    "20": ["/root/bc250-resilience/lane20.sh"],
    "21": ["/root/bc250-resilience/lane21.sh"],
    "22": ["/root/bc250-resilience/lane22.sh"],
    "23": ["/root/bc250-resilience/lane23.sh"],
    "24": ["/root/bc250-resilience/lane24.sh"],
    "25": ["/root/bc250-resilience/lane25.sh"],
    "26": ["/root/bc250-resilience/lane26.sh"]
  }
}
```

Start and resume with:

```bash
sudo bc250 resilience start --plan /root/resilience-plan.json \
  --package-gate /var/lib/bc250-llm-server/package-gates/gate-...

# after lanes 20-25 and their hygiene barriers pass:
sudo reboot
sudo bc250 resilience resume --campaign-dir /var/lib/bc250-llm-server/resilience/campaign-...
sudo bc250 resilience status --campaign-dir /var/lib/bc250-llm-server/resilience/campaign-...
```

The manager persists lane results and inter-lane hygiene barriers separately.
Normal topology explicitly means main/task/embedding active with Agent inactive;
Agent inactivity is not a hygiene failure. If managed-swap refresh is enabled,
only the package-managed swapfile under `/var/lib/bc250-llm-server/swap/` is deactivated and restored,
with its original priority. Signals are blocked for that critical section, zram
and operator-added swap are never deactivated, and no `swapoff -a` path exists.

SIGINT/SIGTERM terminates the active lane, seals partial evidence, restores the
package-managed normal topology/swap state, persists campaign state, and exits
130. A restoration failure remains recorded even though interruption still exits
130.

On `resume`, source/tool hashes, the installed RPM identity, package-gate closed
manifest, plan hash and the recorded qualification identity are checked before
lane execution. A package change, kernel change or relevant configuration change
invalidates the old evidence and produces a controlled `INCOMPLETE` evidence gap
instead of continuing a stale campaign.
Missing artifacts likewise produce controlled `INCOMPLETE` evidence-gap state
rather than tracebacks.
`DEFECT` and `SAFETY` are terminal and require a new candidate/campaign. After
the required reboot, only Lane 26 may run or retry; the manager never falls back
into another lanes-20-to-25 cycle.

The long-run lane should remain a state/resource drift test. Prefer a 3-hour
canary when useful and a 24-hour primary only when long-duration evidence is
needed; use sparse role transitions and a cheap fixed sentinel instead of
re-running complete model qualification every hour.

## Evidence inventory and conservative cleanup (1.7)

```bash
sudo bc250 qualification list
sudo bc250 qualification list --json
sudo bc250 qualification clean
sudo bc250 qualification clean --older-than-days 30 --keep-latest 2
sudo bc250 qualification clean --older-than-days 30 --keep-latest 2 --apply
```

The inventory covers package-gate artifacts and resilience campaigns. It reports result,
current/stale applicability, size and path. Applicability is derived from the exact
package/kernel/configuration qualification identity recorded by those artifacts. If the
current qualification identity cannot be established, applicability is `UNKNOWN`, never
promoted to current by assumption.

Cleanup is dry-run by default. `--apply` requires root, operates only on direct,
non-symlink children of package-owned evidence roots, preserves nonterminal evidence,
and always retains the newest requested number per evidence class. This command is
space-management QoL only; it never changes qualification results.

## 1.8 package-gate corrections

The Tika extraction smoke uses an alphanumeric deterministic marker that is preserved literally by the pinned Tika 4.1 parser. A failed extraction records both the expected marker and observed extracted text so parser-formatting changes are diagnosable rather than reported as a generic RAG failure.

`bc250 verify` validates operational appliance health **and package-owned live runtime identity**. It is still not release authority: package acceptance additionally requires the authoritative `bc250 package-gate` evidence and the applicable release/device gates.

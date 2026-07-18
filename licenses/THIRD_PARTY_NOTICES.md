# Third-party notices

The repository's original integration scripts, configuration and documentation
are licensed under GNU GPL version 2 only, as provided in `licenses/LICENSE`.

The RPM also contains or refers to separately licensed components:

- **cyan-skillfish-governor-smu** is sourced from
  `filippor/cyan-skillfish-governor`, release `v0.4.11`, commit
  `60ab6e5b354f01f287c73d920990dcd618a674cc`, under the MIT License. The
  project is based on `Magnap/cyan-skillfish-governor`; its upstream license is
  retained in the RPM.
- The main RPM's **BC-250 40-CU unlock** payload contains the Fedora helper and
  patch from `fduraibi/bc250-40cu-unlock`, pinned to commit
  `6c3969ddee40e894297869e6ca30537f274619cb`. It is based on
  `duggasco/bc250-40cu-unlock` and declares GPL-2.0-only. Installing the RPM does
  not apply the patch or enable additional CUs.
- **Ollama**, Open WebUI, Apache Tika, Podman, nginx, Mesa and other runtime
  components retain their own licenses. Ollama is installed separately by the
  operator. Container images and dependency packages are not relicensed here.
- Model weights are not shipped. Source templates identify optional
  third-party repositories only. Operators must review each model's current
  license and terms before downloading it.
- The optional coding-agent setup references
  `unsloth/Ministral-3-8B-Instruct-2512-GGUF` at revision
  `c6345448c40d82d11c744037f4b8aed3e1e4c3ad`. The referenced model currently
  declares Apache-2.0, but the weight is downloaded only after an explicit
  operator command and is not part of this RPM.

## CU live manager

`WinnieLV/bc250-cu-live-manager` is not redistributed because the repository
did not expose an explicit redistribution license when this package was
prepared. The helper defaults to reviewed commit
`8eb45f07810af738f3e4945ea0cc29d399e378a6` and its pinned SHA-256, while still
permitting an operator-supplied immutable revision and checksum. If upstream
publishes suitable redistribution terms, it can
be reconsidered in a later package revision.

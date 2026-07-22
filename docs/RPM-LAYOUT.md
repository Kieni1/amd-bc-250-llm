# RPM layout

## Main package: `bc250-llm-server`

Primary commands:

```text
/usr/bin/bc250
/usr/bin/bc250-model
/usr/bin/bc250-benchmark
/usr/bin/bc250-check-temp
/usr/bin/bc250-40cu
/usr/bin/bc250-cu-live-manager
/usr/bin/bc250-code
/usr/bin/bc250-code-commit
/usr/bin/bc250-compare-experiments
/usr/bin/bc250-fetch-experiments
/usr/bin/bc250-fetch-models
/usr/bin/bc250-fetch-mtp
/usr/bin/bc250-gitea-review
/usr/bin/bc250-install-cu-manager
/usr/bin/bc250-install-ollama
/usr/bin/bc250-swap-profile
/usr/bin/bc250-ollama-profile
/usr/bin/bc250-memory-profile
/usr/bin/bc250-cu-status
/usr/bin/bc250-pull-embedding-model
/usr/bin/bc250-run-mtp
/usr/bin/bc250-setup-coding-agent
/usr/bin/bc250-setup-task-model
/usr/bin/bc250-uninstall-info
/usr/bin/bc250-uninstall
/usr/bin/bc250-verify
/usr/bin/bc250-verify-lan
/usr/bin/llm-run-diagnose
```

Implementation files:

```text
/usr/libexec/bc250-llm-server/
/usr/libexec/bc250-llm-server/modelctl
/usr/libexec/bc250-llm-server/setup-ollama-instance.sh
/usr/libexec/bc250-llm-server/coding-agent/
/usr/libexec/bc250-llm-server/40cu/
```

Examples and templates:

```text
/usr/share/bc250-llm-server/model-management/sources/
/usr/share/bc250-llm-server/model-management/modelfiles/
/usr/share/bc250-llm-server/examples/task-model/
/usr/share/bc250-llm-server/examples/coding-agent/
/usr/share/bc250-llm-server/examples/raspi-wol/
/usr/share/bc250-llm-server/ollama-profiles/
/usr/share/bc250-llm-server/40cu/
/usr/share/bc250-llm-server/cu-live-manager/
```

Configuration:

```text
/etc/bc250-llm-server/
/etc/bc250-llm-server/production-models.toml
/etc/bc250-llm-server/experiments-models.toml
/etc/bc250-llm-server/mtp-models.toml
/etc/cyan-skillfish-governor-smu/config.toml
/etc/nginx/default.d/bc250-llm-server.conf
/etc/nginx/conf.d/00-bc250-websocket-map.conf
/usr/lib/sysusers.d/bc250-llm-server.conf
```

Persistent data is outside RPM ownership:

```text
/var/lib/bc250-llm-server/
/var/lib/bc250-llm-server/gguf/{production,experiments,mtp,task,agent}/
/var/lib/bc250-llm-server/modelfiles/{production,experiments,task,agent}/
/var/lib/bc250-llm-server/ollama/{main,task,agent}/
/var/cache/bc250-llm-server/huggingface/
/var/lib/ollama/
/var/lib/open-webui/
/var/backups/bc250-llm-server/
```

Inspect package ownership without guessing paths:

```bash
rpm -qlv bc250-llm-server.x86_64
rpm -qc bc250-llm-server.x86_64
rpm -qd bc250-llm-server.x86_64
rpm -V bc250-llm-server.x86_64
```

Files created below persistent state directories are intentionally not listed
by `rpm -ql`; they are created by tmpfiles, containers, Ollama or operator
commands rather than carried in the RPM payload.

## Installed experimental 40-CU payload

```text
/usr/bin/bc250-40cu
/usr/bin/bc250-cu-live-manager
/usr/libexec/bc250-llm-server/40cu/bc250-enable-40cu-fedora.sh
/usr/share/bc250-llm-server/40cu/bc250-40cu-amdgpu.patch
/usr/share/bc250-llm-server/40cu/README-upstream.md
/usr/share/bc250-llm-server/40cu/SOURCE-REVISION
/usr/share/bc250-llm-server/cu-live-manager/README-upstream.md
/usr/share/bc250-llm-server/cu-live-manager/SOURCE-REVISION
```

These files belong to the main package. No RPM scriptlet builds or replaces a
kernel module, changes CU routing, or reboots the host. The separate guided
installer prepares the module and its initramfs copy; only
`sudo bc250-40cu enable` activates the additional CUs.

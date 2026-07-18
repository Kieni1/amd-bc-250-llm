# RPM layout

## Main package: `bc250-llm-server`

Primary commands:

```text
/usr/bin/bc250-benchmark
/usr/bin/bc250-check-temp
/usr/bin/bc250-40cu
/usr/bin/bc250-code
/usr/bin/bc250-code-commit
/usr/bin/bc250-compare-experiments
/usr/bin/bc250-fetch-experiments
/usr/bin/bc250-fetch-models
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
/usr/bin/bc250-verify
/usr/bin/bc250-verify-lan
```

Implementation files:

```text
/usr/libexec/bc250-llm-server/
/usr/libexec/bc250-llm-server/coding-agent/
/usr/libexec/bc250-llm-server/40cu/
```

Examples and templates:

```text
/usr/share/bc250-llm-server/models/
/usr/share/bc250-llm-server/experiments/
/usr/share/bc250-llm-server/examples/task-model/
/usr/share/bc250-llm-server/examples/coding-agent/
/usr/share/bc250-llm-server/examples/raspi-wol/
/usr/share/bc250-llm-server/ollama-profiles/
/usr/share/bc250-llm-server/40cu/
```

Configuration:

```text
/etc/bc250-llm-server/
/etc/cyan-skillfish-governor-smu/config.toml
/etc/nginx/default.d/bc250-llm-server.conf
/etc/nginx/conf.d/00-bc250-websocket-map.conf
```

Persistent data is outside RPM ownership:

```text
/var/llm/
/var/lib/ollama/
/var/lib/open-webui/
/var/backups/bc250-llm-server/
```

## Installed experimental 40-CU payload

```text
/usr/bin/bc250-40cu
/usr/libexec/bc250-llm-server/40cu/bc250-enable-40cu-fedora.sh
/usr/share/bc250-llm-server/40cu/bc250-40cu-amdgpu.patch
/usr/share/bc250-llm-server/40cu/README-upstream.md
/usr/share/bc250-llm-server/40cu/SOURCE-REVISION
```

These files belong to the main package. No RPM scriptlet builds or replaces a
kernel module, changes CU routing, or reboots the host.

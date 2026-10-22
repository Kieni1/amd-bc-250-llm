# Release 0.14.1-1.6 — scope and acceptance

## Scope

Release `0.14.1-1.6` is a bounded runtime/maintenance update.

Included:

- Ollama `0.40.6 -> 0.40.8`, generic Linux AMD64 payload pinned by SHA-256;
- Cyan Skillfish governor `0.4.13 -> 0.4.14`, pinned to upstream release commit;
- `actions/checkout` pinned from v6.1.0 to v7.0.1;
- diagnostic use of Ollama 0.40.7+ `/api/show` `renderer`, `parser` and `template_source` metadata.

Unchanged:

- Fedora 44 target;
- Open WebUI `0.12.3`;
- Tika `4.1.0-full`;
- stock Fedora AMDGPU/Mesa/Vulkan architecture;
- main/task/embedding/exclusive-agent lane topology;
- `OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`, `GGML_VK_VISIBLE_DEVICES=0`;
- one loaded model / one parallel request per lane;
- existing context, keep-alive, Flash Attention and KV-cache policies;
- governor package policy: 350–1850 MHz normal range, busy-flag usage, sysfs temperature, existing thermal/ramp/load-target/safe-points;
- production/recommended model selection;
- SRPM-first authoritative release chain.

## Ollama review conclusion

Upstream 0.40.7 adds `renderer`, `parser` and `template_source` to `ollama show` and `/api/show`, improves speculative-draft handling, updates llama.cpp/MLX and changes remote-request cancellation. Ollama 0.40.8 primarily adds the Flint model and does not require a BC-250 service-setting change. `OLLAMA_NO_CLOUD=1` remains required and Flint is not added to the package catalog.

The llama.cpp update means exact-device Vulkan smoke remains mandatory. Test representative small and large production models, package-created registration uniqueness/restart persistence, all normal lanes, and inspect `/api/show` rendering metadata. Do not change memory/context policy merely because the runtime version changed.

## Governor review conclusion

Upstream 0.4.14 adds descriptive errors plus graceful shutdown/error cleanup and GPU-usage clamping. Its configuration contract remains compatible with the package profile, so no tuning values change. Exact-device acceptance needs only a bounded service/version/config/temperature/frequency/load smoke and a representative GPU workload; do not restart a governor-tuning campaign without evidence.

## GitHub Actions

`actions/checkout` is pinned to v7.0.1 commit `3d3c42e5aac5ba805825da76410c181273ba90b1`. v7 adds safer fork-PR handling and dependency/security maintenance. The existing workflow does not intentionally opt into unsafe fork checkout.

## Acceptance

Source candidate:

- current identity/pins coherent;
- focused packaging/runtime/release tests green;
- Ruff/ShellCheck/preflight/package-critical gates green in Fedora authority;
- frozen Source0/spec and source preparation succeed with governor 0.4.14.

Exact selected 1.6 RPM:

1. all normal Ollama lanes report `0.40.8`;
2. representative Vulkan generation succeeds without device-loss/OOM regression;
3. package-owned registrations remain unique and stable across supported restart;
4. `/api/show` rendering metadata is captured for representative models;
5. Open WebUI/RAG/6144 representative regression remains green;
6. governor reports `0.4.14`, service stays healthy, package config/range is intact, temperatures/frequency respond normally under a bounded workload;
7. 40/40 routing, status/health/verify and reboot persistence remain coherent.

Prior device evidence is regression baseline only and cannot be transferred to changed 1.6 bytes.

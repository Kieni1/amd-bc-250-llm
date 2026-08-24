# Benchmark

```bash
bc250-benchmark

# Optional sensor trace in another terminal
/usr/libexec/bc250-llm-server/log_sensors.sh sensors.log
```

The interactive benchmark records cold/warm latency, time to first content and
answer, prompt evaluation, decode throughput, model load time, optional context
curves and sustained-load drift. It writes timestamped CSV and metadata files
in the current directory.

Use the same Ollama version, model revision, governor, context, prompts and
cooling state when comparing results. The benchmark measures this Ollama
deployment; it does not measure Open WebUI, RAG, Tika, browser rendering or
answer quality. See [`../../docs/COMMANDS.md`](../../docs/COMMANDS.md) for
environment controls.

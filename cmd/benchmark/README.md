# Benchmark tools

`compare-models.sh` is an end-to-end Ollama benchmark for the BC-250. It records
cold and warm streaming latency, time to first visible content and answer,
prompt evaluation, decode throughput, model-load time, optional context curves,
and optional sustained-load drift.

Run it as the normal operator account while Ollama is available:

```bash
bc250-benchmark
```

The script writes a CSV and metadata file in the current directory. Use the same
Ollama version, governor configuration, context settings, prompt settings and
cooling state when comparing runs. The numbers describe this Ollama deployment;
they are not a pure Vulkan microbenchmark and do not measure Open WebUI, RAG,
Tika, browser rendering or answer quality.

For a temperature/power trace in a second terminal:

```bash
/usr/libexec/bc250-llm-server/log_sensors.sh sensors.log
```

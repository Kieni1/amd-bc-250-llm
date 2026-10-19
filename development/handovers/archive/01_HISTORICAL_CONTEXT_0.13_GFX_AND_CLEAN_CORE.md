# Historical context — experimental GFX and clean-core decision

The project previously implemented and deeply qualified an experimental GPU path involving patched kernel behavior, private Mesa/RADV userspace, staged boot handling and substantial lifecycle/qualification machinery.

The experiment was technically successful, but measured product benefit was modest relative to kernel, Mesa, boot, packaging, build and support burden.

Durable decision:

- preserve research evidence separately;
- keep experimental GPU work outside the main appliance;
- maintain a stock-first core;
- carry forward only generic improvements that remain valuable without the experiment.

The current `0.14.1-1` line should be treated as the product baseline, not as an extension of the old experimental architecture.

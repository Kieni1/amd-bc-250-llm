# Historical quality campaigns

This directory is source-only development archaeology. It is intentionally not installed
by the RPM and its scripts are not the supported operator interface.

The still-relevant lifecycle rules from these campaigns are carried by the current
`quality-checks/task/` and `quality-checks/translation/` screens:

- isolate the tested lane or refuse to evict a pre-existing workload;
- capture package/service/resource state before and after a run;
- cover the embedding lane in whole-appliance task survival/recovery checks;
- restore Open WebUI preset/provider state exactly after temporary candidate testing;
- keep credentials and private paths out of evidence;
- capture serious OOM/GPU warnings and memory recovery;
- determine the authoritative result only after restoration/privacy/archive outcomes;
- print evidence SHA-256 without checksum sidecar clutter.

The historical prompt variants, broad matrices and challenger-specific wrappers document
closed campaigns. Do not expose them as current installed commands or use them to reopen
a completed tournament.

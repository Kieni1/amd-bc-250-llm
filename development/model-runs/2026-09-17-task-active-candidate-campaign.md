ID: TASK-MODEL-20260917-01
Status: COMPLETE / DECISION RECORDED
Package: 0.11.1-0.10.fc44
Exact model: task-lfm25-1.2b-instruct-liquidai-q6-k (production reference); active compact/extended candidate pool
Role: Open WebUI title/tag/query background task generation
Tests actually run: compact + extended cheap canonical screens; focused Qwen3 4B task staging/survival experiments
Tests not run: no further expensive qualification for candidates that failed quality/survival gates

Observed facts:
- Production LFM remains the only tested model combining useful task quality with proven safe warm-main coexistence.
- Current LFM canonical reference envelope is about 4/6-5/6; remaining issue is concise first-turn tag robustness.
- Qwen3 4B scored 5/6 in two independent cheap screens, the strongest active challenger quality signal.
- Exact-source and 4096-context task-tuned Qwen3 4B staging both caused global OOM and killed warm GPT-OSS.
- Gemma3 1B remains a low-memory control/fallback at about 2/6; other active candidates screened at <=3/6.

Resource/service results:
- Promoted LFM reference previously passed 9/9 true overlap with warm GPT-OSS.
- Qwen3 4B task-tuned tiny survival: minimum MemAvailable about 100 MiB, swap growth about +715 MiB, repeated global OOM activity.

Interpretation:
- Quality does not imply task-role deployability. Larger candidates must pass a tiny warm-main survival gate before expensive qualification.

Decision:
- NO CHANGE: retain LFM 1.2B as production task model.
- REJECT Qwen3 4B for the concurrent background-task role on the current BC-250 topology.

Retest only if:
- Qwen3 4B: hardware/topology memory envelope materially changes.
- LFM prompt work: use a broader first-turn corpus rather than another single-case micro-tuning loop.

Evidence tarballs referenced by the campaign:
- bc250-task-batch-v2-20260917-053931.tar.gz
- bc250-task-batch-v2-20260917-054737.tar.gz
- bc250-q3-stage-20260917-165956.tar.gz
- bc250-q3-stage-20260917-170719.tar.gz
- bc250-q3-task-20260917-171403.tar.gz
- bc250-tags-c-overlap-20260916-213403.tar.gz
- bc250-tags-fr-load-ab-20260916-214035.tar.gz
- bc250-tags-fr-payload-ab-20260916-214605.tar.gz
- bc250-task-tags-ui-lifecycle-candidate-b-20260916-205349.tar.gz
Restoration status: clean recovery was verified after the destructive Qwen3 4B safety failures before further appliance work.
Credential-scan status: campaign evidence handling was reported clean; raw bundles are external and are not committed here.
Caveats: role-specific rejection does not retire Qwen3 4B globally.

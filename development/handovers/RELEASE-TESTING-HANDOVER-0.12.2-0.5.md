# BC-250 release testing handover — 0.12.2-0.5

## Exact candidate

```text
NVR           bc250-llm-server-0.12.2-0.5
Ollama        0.34.4
Open WebUI    0.11.4
Tika          4.0.0-full
Governor      0.4.13
```

Source/static success is not device acceptance. Install the exact NVR and first confirm `rpm -V`, runtime pins, normal topology and successful authenticated OWUI desired-state convergence. The installer must not publish OWUI through boot/nginx before package apply/status is verified, the Quadlet `[Install]` drop-in has regenerated `open-webui.service` with `WantedBy=multi-user.target`, and nginx publication succeeds. Do not use `systemctl enable open-webui.service`: Quadlet-generated services are transient. Any failure in apply/status/boot-link verification/nginx publication must return to the held state.

## 1. Focused FR→DE integrity regression

Exact source:

`Les employés peuvent utiliser la salle de réunion jusqu'à 18:00. Ils ne peuvent pas modifier l'identifiant AX-88-P. Le responsable doit rendre la clé ensuite.`

Expected faithful target accepted by the filter:

`Die Mitarbeiter können den Besprechungsraum bis 18:00 Uhr nutzen. Sie dürfen die Kennung AX-88-P nicht ändern. Der Verantwortliche muss den Schlüssel anschließend zurückgeben.`

Also repeat recommendation/obligation, permission/prohibition, negated recommendation, no-obligation (`muss nicht` / `n'êtes pas obligé`), adjacent/non-adjacent modalities and same-clause modal ordering. Include these German scoped-negation cases explicitly:

- faithful pass: `Sie darf die Küche nicht nutzen und muss sie reinigen.` -> `Vous ne pouvez pas utiliser la cuisine et devez la nettoyer.`
- unsafe hold: `Sie muss zahlen und darf nicht unterschreiben.` -> `Vous n'êtes pas obligé de payer et ne pouvez pas signer.`

Unsafe recommendation->obligation, obligation->permission, permission->obligation, polarity loss, clause swaps and lost/weakened prohibition must still be withheld.

## 2. Advanced 6144

Prove stored and effective contract:

```text
max_tokens=6144
think=true
temperature=0.7
top_p=0.8
top_k=20
min_p=0
presence_penalty=0
repeat_penalty=1

OWUI -> Ollama options.num_predict=6144
no root-level Ollama max_tokens
```

Run arithmetic, structured JSON, constraint/schedule reasoning, two-turn history, ordinary office writing, bounded reasoning/short-answer and the Advanced side of Advanced+Deep. Record completion-token use. Clean ceiling exhaustion with no visible answer is `INCOMPLETE / production-contract-budget`; repetitive/degenerate reasoning at the ceiling is a quality defect.

## 3. Final integrated OWUI release qualification

Run one full OWUI release qualification only after convergence succeeds. Preserve resource/residency/final-restoration evidence. Deep is a preservation check: exact 0.12.2-0.4 already qualified pre-Deep task/embed eviction, `keep_alive=2m`, reuse, expiry and cold reload with no OOM after convergence.

## Closed investigations — do not replay merely for closure

- Tika genuine DOCX list serialization: `· item` is confirmed Tika 4 output; headings/tables/list ordering/facts survive extraction and retrieval. No package change.
- Title/tag persistence: repeated single-model and Advanced+Deep testing was stable. No task-lane change.
- Old native long-run: not required solely for this translation/6144 delta.

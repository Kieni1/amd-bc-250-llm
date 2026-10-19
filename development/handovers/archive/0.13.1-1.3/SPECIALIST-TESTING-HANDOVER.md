# BC-250 specialist testing handover — 0.13.1-1.3

## Use this file to choose the right side chat

Do not open a specialist chat simply because an old handover exists.

Current specialist lanes:

### 04 — exact RPM build / device closure

Open when:

- building/installing the final 0.13.1-1.3 RPM;
- proving live-CU-only behavior;
- running final verify/revalidate;
- deciding release freeze/tag.

This is the default next specialist lane.

### 05 — integrated structured-output policy

Open only when:

- final product request construction needs implementation/review;
- final RPM changed the structured trigger path;
- effective parameter evidence is needed.

Do not use it to rerun model discovery.

### 06 — RAG product qualification

Open when:

- testing `bc250 rag`;
- Tika/embedding/product retrieval behavior changes;
- RAG exact-device product smoke is needed.

RAG is ACTIVE.

### 07 — greenfield appliance/API/layout

Open when:

- checking installed command/file footprint;
- verifying removed aliases/assets;
- checking libexec/public boundary;
- evaluating upgrade residue;
- checking installed docs.

### 08 — optional Agent / specialist add-ons

Open only for:

- optional-Agent semantics;
- intentional Agent installed coverage;
- direct boundary changes to MTP/coding-agent/OCR.

Do not make optional domains mandatory.

## Closed specialist topics

Do not create active chats for:

```text
Advanced 6144 diagnosis
Advanced think A/B
Standard structured discovery
Documents extra denominator
Deep structured discovery
translation model tournament
EuroLLM Round 2
multi-device board ranking
Tika bullet formatting
title/tag anomaly
Qwen3.6 35B
kernel-patch 40-CU workflow
broad RAG model tournament
```

Their conclusions are incorporated into current product policy.

## Shared test rules

Every specialist should:

1. record exact source/NVR;
2. state scope;
3. distinguish source vs exact-device evidence;
4. preserve raw evidence;
5. classify harness defects separately;
6. restore state;
7. clean synthetic data;
8. avoid secrets;
9. avoid replaying closed campaigns;
10. return a concise handover to main integration when a cross-stream decision is needed.

## Model-output vs harness exit

Model-quality findings generally remain evidence.

Non-zero harness exit should be reserved for:

- infrastructure/API failure;
- safety condition;
- harness/config failure;
- cleanup failure;
- restoration failure;
- archive/evidence integrity failure;

unless the specialist's explicit contract defines otherwise.

## Evidence ownership

Main integration owns:

- production model/preset policy;
- release acceptance;
- version/release metadata;
- cross-stream decisions.

Specialists own:

- bounded evidence;
- narrowly justified implementation changes;
- exact findings/limitations.

Specialists should not independently promote a model or redefine release scope.

## Stop rules

Stop a specialist campaign when:

- the pre-agreed decision rule is met;
- the behavioral question is already answered;
- a regression clearly rejects the challenger;
- further repetitions would only increase denominator without changing policy;
- the finding belongs to another current lane.

EuroLLM is the current example: the Round 1 English-output regression met the stop rule; no Round 2.

## Final-release routing

If uncertain which specialist should own a release issue:

```text
build/install/runtime -> 04
structured policy -> 05
RAG/Tika/embed -> 06
files/commands/layout -> 07
optional Agent/specialist add-on -> 08
cross-cutting decision -> main integration
```

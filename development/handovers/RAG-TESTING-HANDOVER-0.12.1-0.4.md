# BC-250 0.12.1-0.4 RAG lifecycle testing handover

## Purpose

This is the bounded specialist handover for the new `bc250-rag` lifecycle. Test the package behavior and operator UX; do not reopen embedding/answer-model selection. The production answer role remains `bc250-office-documents` / Gemma E4B and the embedding model remains Jina v5 small retrieval on :11437.

The new function exists primarily to bootstrap the initial private DE/FR corpus with less repetitive manual work while retaining a hard human-review boundary.

## Source/release identity

```text
VERSION       0.12.1
RPM Release   0.4
candidate     bc250-llm-server-0.12.1-0.4
```

Record the exact installed NEVRA before testing. Source qualification does not qualify the installed package.

## Product boundary

The authoritative lifecycle is:

```text
inbox/{german,french,bilingual}
        |
        | local pdfinfo/pdftotext + local exclusive agent lane
        v
working/                 <- generated/editorial proposal only
        |
        | explicit interactive human review
        v
active/                  <- only reviewed Markdown is ingestible
        |
        | bc250-rag ingest
        v
Open WebUI Knowledge     <- derived/disposable index

sources/                 <- immutable received source evidence
superseded/              <- prior reviewed revisions/evidence
```

Automation must never move a generated draft directly from inbox/working to active.

`bc250-rag-import plan|sync` remains a compatibility interface for older corpora. New lifecycle testing should use `bc250-rag`.

## Folder/security expectations

Create one disposable public-source collection and one disposable confidential collection:

```bash
sudo bc250-rag init public rag-test-public
sudo bc250-rag init confidential rag-test-private
```

Expected:

```text
sources/
working/
active/
superseded/
inbox/german/
inbox/french/
inbox/bilingual/
```

Public collection default mode: `0750`.
Confidential collection default mode: `0700`.

Symlinked lifecycle/inbox directories must be rejected. The command must not send source text to a remote agent URL; `prepare-batch --agent-url` is loopback-only. Open WebUI API access occurs only during explicit plan/sync/ingest operations.

## Test documents

Use synthetic/non-sensitive fixtures for the first functional pass, then a small representative real-office set if available.

Prepare at least:

1. one selectable-text German PDF with headings, article numbers, dates, amounts and percentages;
2. one selectable-text French PDF corresponding to a German family;
3. one selectable-text bilingual PDF containing both languages;
4. one image-only/scanned PDF;
5. one deliberately oversized text-native PDF above the configured single-pass character limit;
6. one replacement revision of the German document with the same document family and a later effective date.

Do not use confidential production content to test failure paths.

## Batch preparation

Populate the three inbox lanes, then first run:

```bash
sudo bc250-rag prepare-batch public rag-test-public --dry-run
```

Expected:

- no files move;
- no agent mode change;
- lane + filename inventory is clear;
- no Open WebUI request occurs.

Then run the real preparation:

```bash
sudo bc250-rag prepare-batch public rag-test-public
```

If normal topology was active before the command, expected behavior is:

1. enter exclusive agent mode only when necessary;
2. verify the configured agent model exists;
3. process bounded text-native PDFs locally;
4. restore normal main/task/embedding topology after the batch, including after a per-file failure.

The default model is the packaged current agent baseline. Do not substitute another model during release acceptance unless the default cannot run; return that as a defect instead.

Expected lane behavior:

```text
german     -> one de-CH authoritative working Markdown
french     -> one fr-CH translation working Markdown
bilingual  -> separate de-CH authoritative + fr-CH translation working Markdown
```

The bilingual outputs should share source provenance. They must not become one mixed-language indexed Markdown file.

## Deliberate refusal paths

The new function intentionally does not absorb every document-processing problem.

Image-only/near-empty extraction must remain in the inbox and clearly instruct the operator to use the local OCR workflow. It must not invent text.

A document beyond the bounded single-pass character limit must remain for a genuine chapter/document split and clearly say why. Automatic LLM chunk/reassembly was deliberately not implemented in 0.4 because source-faithfulness is more important than coverage automation.

These are PASS conditions if the refusal is clear and no partial active content is created.

## Source fidelity review

For at least the German, French and bilingual examples compare the generated `working/*.md` against representative PDF pages visually.

Check specifically:

- all substantive sections are represented;
- source article/paragraph numbering is preserved, not replaced with invented retrieval numbering;
- dates, amounts, percentages, currency and legal references are exact;
- true hyphens remain while line-wrap hyphenation is repaired appropriately;
- repeated decorative page headers/footers are removed where safe;
- no summaries, interpretations or commentary were inserted into the authoritative body;
- German content was not translated;
- French content was not translated from German in a bilingual source; it must come from the French source text;
- tables remain understandable and values are not silently rewritten.

The printed critical-token coverage is a diagnostic only, not proof of fidelity. Human review remains the authority.

## Interactive review UX

Run:

```bash
sudo bc250-rag review public rag-test-public
```

Exercise at least one correction to:

- title;
- `document_family`;
- effective date or edition;
- French `translation_of` counterpart.

Expected UX:

- source filename, language, proposed title/family and authority role are shown before prompts;
- unsafe family IDs containing path separators/spaces are not accepted as ready identifiers;
- authority is `authoritative` or `translation` (`original` may normalize to authoritative for compatibility);
- a draft cannot be marked ready without an effective date or edition/version;
- French/bilingual counterpart suggestion is useful when an unambiguous German draft exists;
- reviewed filename becomes canonical and deterministic;
- `review_required=false` appears only after explicit approval.

No source PDF may be modified.

## Validation

Run:

```bash
sudo bc250-rag validate public rag-test-public --include-working
```

Expected failures include malformed/missing source SHA, source escape/symlink, duplicate document ID, duplicate active family+language revision and active `review_required=true`.

Expected warnings rather than hard failures include deliberately retained `currentness-not-verified` and a translation whose reviewed German counterpart has not yet been activated/resolved.

Unknown arbitrary YAML keys should still fail. Package-reserved future metadata keys beginning `bc250_` should remain accepted/preserved.

## Activation/supersession

Activate only reviewed drafts:

```bash
sudo bc250-rag activate public rag-test-public FILE.md
# or after reviewing several:
sudo bc250-rag activate public rag-test-public --all-ready
```

Expected:

- plan shows what will activate and what prior active revision will be superseded;
- interactive confirmation is required unless `--yes` is explicit;
- an unreviewed draft cannot activate;
- only one active revision exists for a document family/language;
- the prior Markdown moves to `superseded/`;
- an old source moves to `superseded/` only when no active/working document still references it;
- a shared bilingual source is retained while either active language still references it;
- post-activation validation runs and reports warning/failure counts.

Then test explicit:

```bash
sudo bc250-rag supersede public rag-test-public FILE.md
```

It must accept a filename only, not a path traversal.

## Status UX

Run:

```bash
sudo bc250-rag status
sudo bc250-rag status public rag-test-public
```

The operator should be able to understand at a glance:

- source/working/active/superseded counts;
- german/french/bilingual inbox counts;
- number of working drafts still requiring review;
- number of active DE/FR paired families.

Judge clarity, not merely return code.

## Open WebUI ingestion

Use a disposable Open WebUI API key owned by the intended test account and mode 0600 token file.

First inspect the plan:

```bash
sudo bc250-rag plan /srv/bc250-documents
```

Then:

```bash
sudo bc250-rag ingest --token-file /root/owui-rag-test.key
```

Expected:

- new lifecycle validation runs before any Open WebUI mutation;
- only `active/*.md` is considered;
- no `sources/`, `working/`, `superseded/` or inbox content is uploaded;
- German authoritative files route to `[SCOPE] COLLECTION — Originals`;
- French translations route to `[SCOPE] COLLECTION — Français`;
- unchanged second sync is idempotent;
- changed Markdown replaces remote content only after successful upload/processing;
- locally removed documents are reported but are not remotely removed without explicit `--prune`;
- token content is never printed or stored in corpus metadata.

Verify ordinary-user permissions/isolation through Open WebUI separately from filesystem scope. The word `public` is a local corpus classification, not an instruction to make an Open WebUI knowledge base public.

## RAG product smoke

After ingesting a tiny test collection, exercise `bc250-office-documents` with:

- one exact German fact;
- one exact French fact through the French knowledge collection;
- one cross-section question;
- one appendix/general-rule distinction if the fixture supports it;
- one absent-information question;
- one DE query whose answer is sourced from German;
- one FR query whose answer is sourced from the French translation.

This release does not change Jina, chunking defaults or the answer model, so this is a lifecycle integration smoke rather than a new RAG model tournament.

## Markdown-escaped marker regression

The benchmark acceptance normalizer now treats simple Markdown presentation escapes such as:

```text
BC250\_RAG\_MARKER
```

as equivalent to:

```text
BC250_RAG_MARKER
```

for deterministic synthetic acceptance. Confirm the exact marker case no longer produces the previous false negative. Do not broaden normalization to hide genuinely changed text/numbers.

## Privacy/support bundle check

Create a support bundle after the disposable corpus exists. Confirm it does not include PDF/Markdown body content, Open WebUI uploads/vector data, API token material or confidential corpus contents. Metadata/count-style diagnostics are acceptable if content-free.

## Restoration

Before handoff completion:

- delete disposable Open WebUI knowledge/file objects;
- remove disposable filesystem collections;
- return normal topology;
- ensure no agent model remains resident unintentionally;
- run authenticated `bc250-verify` and record the final result;
- preserve the test transcript/evidence archive, not the disposable corpus.

## Stop rules / defects to return to main

Stop and return evidence if any of these occur:

- source is modified;
- generated draft reaches active without explicit review;
- remote/non-loopback agent URL accepts document text;
- scan/oversized refusal leaves a partial active document;
- source SHA/provenance can be bypassed;
- activation loses the only copy of a source still referenced by another language/revision;
- agent mode fails to restore normal topology;
- ingestion uploads non-active content;
- confidential/source content appears in support evidence;
- a real source-fidelity omission cannot be explained by extraction limitations.

## Required handoff

```text
RAG 0.12.1-0.4 -> MAIN INTEGRATION
installed NEVRA:
collection fixtures + SHA-256:
three-lane prepare result:
source-fidelity review:
scan/oversize refusal result:
review UX result:
validation result:
activation/supersession result:
status UX result:
Open WebUI plan/sync/idempotence/prune result:
DE/FR product queries:
privacy/support-bundle result:
topology restoration:
final authenticated verifier:
observed defects:
recommended source changes:
evidence archive + SHA-256:
```

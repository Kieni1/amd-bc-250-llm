# DE/FR Knowledge-scoped RAG testing choices (opt-in only)

These are **two separate administrator-private testing choices**, not production roles.
Read `de-fr-rag-testing-recipes.json` for the two complete operator recipes:
`BC250 TEST - Documents DE` and `BC250 TEST - Documents FR`. Both use the
**same already installed** Gemma E4B base as `Office - Documents / RAG`.
No additional model or model source is downloaded. Neither test role is
created during RPM install or `bc250 advanced openwebui apply`.

## Operator setup (Open WebUI 0.13.3)

1. In Workspace → Knowledge, prepare **one private DE-only** collection and
   **one private FR-only** collection from externally held, approved DEVICE
   test documents. Do not put corpus PDFs, collection/file IDs or answers in Git,
   RPM artifacts or main-chat handovers.
2. In Workspace → Models, create two administrator-private presets using the
   recipe names, base model, short language instruction and *one corresponding*
   Knowledge collection each. Keep the production `Office - Documents / RAG`
   model and all retrieval defaults unchanged. Disable unrelated tools.
3. **Crucial:** after creating each preset, edit it through the UI, detach and
   reattach only its intended collection and save. A stored `meta.knowledge`
   association from a model-creation API is **not** proof of live chat scoping.
   Do not enable broad `list_knowledge_bases` access as a substitute for binding.
4. Start separate fresh administrator chats. Do not inherit chat/folder Knowledge.
   Inspect **actual Knowledge tool calls and retrieved source IDs**: each chat
   must be limited to the single attached collection (`list_knowledge` scope),
   answer in the expected language and cite consulted sources. Repeat for FR;
   a DE-only successful test does not prove FR. Reject tool-only traces that
   never produce a final answer.
5. Run matched control queries against the existing combined Documents/RAG
   role separately. This is **not** proof of a DE/FR quality improvement.
   Delete testing presets and collections explicitly when finished.

These JSON recipes are intentionally **not Open WebUI import payloads** and
contain no collection IDs. They cannot be automatically applied safely to
operator-owned private data. Presets remain private and are not shipped as
ordinary-user selectable roles until a separate product/DEVICE decision.

### Version-specific DEVICE checks

Open WebUI 0.13.3 incorporates upstream escaped-punctuation Knowledge grep fix
`ad95407a1b44794357144a4b04fec619d3afdf9f`. Test both `Art. 40` and
`Art\. 40` searches, with actual UUID-based file viewing. Confirm correct
citations (a source-text line number is not automatically a PDF page number).
Open WebUI 0.13.3 migration, runtime scope and this fix remain **NOT_TESTED**
on the exact new RPM until DEVICE evidence is returned.

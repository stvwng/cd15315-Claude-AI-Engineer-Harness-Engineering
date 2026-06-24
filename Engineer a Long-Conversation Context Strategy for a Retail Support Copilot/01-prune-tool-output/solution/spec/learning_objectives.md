# Learning Objectives → Acceptance Criteria Mapping

**Purpose.** This document is the traceability bridge between Module 2's seven learning objectives and the gradable acceptance criteria in [`PRD.md`](PRD.md) / [`prd.json`](prd.json). It is the working draft for the project rubric (per Udacity rubric guidance: criteria, submission requirements, reviewer tips). Every LO must trace to at least one acceptance criterion that produces observable evidence in the submission.

**Module:** 2 — Context Engineering Foundations
**Course:** 1 — Harness Engineering
**Exam domain support:** Domain 5 (Context Management & Reliability), Task 5.1 (cross-cutting foundation)

---

## LO 1 — Diagram the context window anatomy

**SWBAT.** *Students will be able to diagram the complete context window anatomy: system prompt → CLAUDE.md → memory → conversation history → current turn, and explain what occupies each layer.*

**Exam task.** Task 5.1 (Knowledge) — context window composition.

**Rubric criterion (draft).** Diagram the context window anatomy and explain what content lives at each layer.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-06.4 | `runs/<run_id>/context.md` is the *executable* form of one of those layers (the assembled conversation block) — the learner has produced a real artifact corresponding to a labeled layer of the diagram. |
| AC-08.5 | README contains a context-window anatomy diagram (ASCII or Mermaid) showing the five layers: system prompt → CLAUDE.md → memory → conversation history → current turn. |
| AC-08.7 | README's before/after token table localizes the project's work to one specific layer (conversation history) and quantifies the budget at that layer. |
| AC-08.8 | "What I'd do next" section names the *adjacent* layers (CLAUDE.md, memory, `--resume`) and how this project's strategy would interact with them — demonstrates the learner can locate this work in the broader anatomy. |

**Reviewer artifact.** The README's anatomy diagram + the `context.md` produced by a graded run. The diagram is the conceptual artifact; `context.md` is the concrete one — the learner should be able to point from a labeled box in the diagram to the corresponding section of `context.md`.

**Common failure modes that block mastery.**
- Diagram labels the five layers but the README never connects them to *this project's* work — the learner has copied a generic diagram without locating their own code in it.
- "What I'd do next" section is generic ("could add CLAUDE.md, could add memory") rather than describing the *interaction* — e.g., "the case-facts block is what would survive `--clear`; the verbatim active segment is not."
- Diagram includes only four layers (omits memory) — common gap because memory is the newest mechanic and not covered in prerequisites.

---

## LO 2 — Explain how the harness assembles, maintains, and compresses context

**SWBAT.** *Students will be able to explain how the harness assembles context at session start, maintains it as turns accumulate, and compresses it when budgets are exceeded — and identify which of those mechanisms is implemented in their project.*

**Exam task.** Task 5.1 (Knowledge + Skills) — context assembly and maintenance.

**Rubric criterion (draft).** Implement a compression strategy that distinguishes high-fidelity (verbatim) from low-fidelity (summarized) zones, and articulate the rationale.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-05.1 | `summarize_segment` produces a ≤ 500-token summary — observable in `runs/<run_id>/context.md`. |
| AC-05.2 | Each summary has the prescribed structure (one-sentence outcome → 3–6 facts → resolution sentence) — verified by reading the artifact. |
| AC-05.3 | Compression prompt template is committed at `retail_context/prompts/compression_prompt.md` — reviewer audits the *intent*, not the output. |
| AC-05.4 | Active segment preserved byte-exact — `test_active_segment_preserved_verbatim` asserts equality with the raw turns. This is the load-bearing distinction: the learner chose *not* to compress where fidelity matters. |
| AC-05.5 | Combined resolved-summary cost ≤ 1,000 tokens vs ~20,000 raw → ≥ 95% reduction on the resolved portion, quantified in `budget.json`. |
| AC-07.4 | Eval passes ≥ 5/6 against the compressed context — direct evidence that compression maintained answerability. |
| AC-07.5 | Control eval (case-facts removed) makes Q1 and Q6 fail — proves the *case-facts block* (not the active verbatim) is doing the recall work on those questions, separating assembly from compression. |
| AC-08.6 | README "Why this layout?" section explains the resolved-vs-active fidelity tradeoff in 3–5 sentences. |

**Reviewer artifact.** `context.md`, `budget.json`, `eval.jsonl` (compressed + control), the compression prompt template, and the README writeup. A reviewer should be able to diff a single summary against its source turns and see plausible information preservation, and read the eval JSONL to see compression didn't drop facts.

**Common failure modes that block mastery.**
- Summary is grammatical but content-thin ("The customer had an issue and it was resolved") — passes the 500-token cap but fails the eval because no specific facts survived. The structured-prompt requirement (AC-05.2) is the defense against this.
- Learner over-compresses *and* compresses the active segment "for consistency" — AC-05.4 catches this.
- Compression succeeds but the README writeup is generic ("we summarize old stuff") — fails to articulate *why* the active segment is exempt, which is the core LO.
- Control eval is wired up but Q1/Q6 still pass without case facts — indicates the case-facts block is redundant with the verbatim section, meaning the learner duplicated information rather than partitioning it. (Likely the answers happen to be quoted in turns 29–48.)

---

## LO 3 — Calculate token cost implications

**SWBAT.** *Students will be able to calculate token costs for context design decisions and compare alternative strategies on a token budget.*

**Exam task.** Task 5.1 (Skills) — token economics.

**Rubric criterion (draft).** Measure context token costs end-to-end and report per-section and total budgets against a stated target.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-02.3 | Baseline transcript token count is in the engineered range [32,000, 38,000] — confirms the learner is measuring, not estimating. |
| AC-02.4 | Token counting goes through a single canonical function backed by `tiktoken cl100k_base` or Anthropic `count_tokens` — `len // 4` is explicitly forbidden. |
| AC-03.3 | Case-facts block ≤ 600 tokens — measured, not asserted. |
| AC-04.4 | Pruned `lookup_order` ≤ 200 tokens — measured, not asserted. |
| AC-05.5 | Combined resolved-summary cost ≤ 1,000 tokens — measured against the raw resolved-segment cost. |
| AC-05.6 | Compression API spend ≤ $0.10, estimated from token counts × Haiku pricing — the learner did the arithmetic. |
| AC-06.2 | Total assembled context ≤ 16,000 tokens (≥ 54% reduction). |
| AC-06.6 | `budget.json` records baseline / assembled / reduction% / per-section counts; reduction is *computed*, not hardcoded. |
| AC-08.1 | AST anti-pattern: `len(text) // 4` and `len(text) / 4` are forbidden in `tokens.py`. |
| AC-08.7 | README before/after token table is sourced from `budget.json`, not narrated. |

**Reviewer artifact.** `budget.json` + the README token table. A reviewer should be able to re-run the pipeline and see `budget.json` regenerated with the same shape and approximately the same numbers (token counts are deterministic for `tiktoken`; have a few percent of drift if the Anthropic endpoint is used).

**Common failure modes that block mastery.**
- README quotes round-number token figures ("about 35k → about 16k") with no `budget.json` to back them up.
- Token counting is *inconsistent* — baseline measured one way, per-section another, post-compression a third. AC-08.1's consistency audit is the trip-wire. (Note: the Exam Guide out-of-scopes tokenization specifics, so the *algorithm* doesn't matter — but mixing them means the reduction percentage is incoherent.)
- README fails to name the chosen methodology in one sentence (AC-02.5), making the reported numbers uninterpretable.
- Reduction percentage is hardcoded in the README ("we achieve 54% reduction") rather than computed — the learner has *targeted* the number rather than *measured* it.
- Per-section counts are present but don't sum to the assembled total (off by header / formatting bytes) — indicates measurement is approximate rather than canonical.

---

## LO 4 — Apply the "lost in the middle" effect to placement

**SWBAT.** *Students will be able to apply the "lost in the middle" attention effect to information placement: high-priority content at context boundaries, lower-priority content in the middle.*

**Exam task.** Task 5.1 (Skills) — position-aware structuring.

**Rubric criterion (draft).** Order context sections so that high-priority content occupies the top and bottom boundaries and lower-priority content occupies the middle, and explain the rationale.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-06.1 | Assembled `context.md` has sections in exact order: Case Facts → Resolved Refund → Resolved Subscription → Active Payment Update. Case facts at the top boundary, resolved (compressible) in the middle, active at the bottom boundary against the new user turn. |
| AC-06.3 | The active segment occupies the bottom boundary byte-exact — the highest-attention position holds the highest-fidelity content. |
| AC-06.5 | No interleaving between resolved and active sections — section boundaries are exclusive, preserving the position contract. |
| AC-08.3 | Static audit confirms the section order matches the contract — regression-safe. |
| AC-08.6 | README "Why this layout?" section explicitly cites the "lost in the middle" effect (LO 4) and the resolved-vs-active fidelity tradeoff (LO 2). |

**Reviewer artifact.** `context.md` (the layout), the AST/regex audit output, and the README rationale. A reviewer should be able to read the README, look at `context.md`, and see the same argument expressed in two media.

**Common failure modes that block mastery.**
- Section order is right but the README writeup explains it in terms of "logical reading order" rather than the position-attention effect — fails the *rationale* part of the rubric.
- Learner places case facts at the bottom (next to the user turn) "for relevance" — confuses *recency* with *boundary attention*. Both are real effects; the LO is the latter.
- Verbatim active section is placed in the middle with case facts at the top *and* a "decision template" at the bottom — three boundaries instead of two. Plausible but not what the LO targets; the section-order audit (AC-06.1) catches this.
- README's "Why this layout?" section is exactly 1 sentence ("we put important stuff at the boundaries") — fails the 3–5 sentence floor.

---

## LO 5 — Extract case facts into a persistent block

**SWBAT.** *Students will be able to extract transactional facts (IDs, amounts, statuses, dates) from conversation history into a persistent structured block placed outside the summarizable region.*

**Exam task.** Task 5.1 (Skills) — "case facts" extraction.

**Rubric criterion (draft).** Build a case-facts block that survives compression and demonstrably carries the transactional facts the agent needs to recall.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-03.1 | `case_facts.extract(transcript)` returns a typed model with the 12 required fields populated. |
| AC-03.3 | Block is ≤ 600 tokens — bounded so it can sit at the top boundary without dominating budget. |
| AC-03.4 | Block is rendered as Markdown with explicit section headers and a fixed key order — reviewer-readable, not raw JSON. |
| AC-03.5 | `test_case_facts_extraction` asserts every required field is populated and non-null. |
| AC-03.6 | Missing-field behavior raises `CaseFactExtractionError` listing missing fields — silent `null` fill is forbidden. (Forces the learner to *notice* extraction failure.) |
| AC-06.1 | Case facts occupy the top of the assembled context — outside the resolved-summary middle zone, where the LO says they belong. |
| AC-07.5 | Control eval (case facts removed) makes Q1 (refund amount) and Q6 (current card last-4) fail — evidence that the block is the *only* place those facts survive after compression, which is exactly the LO's claim. |

**Reviewer artifact.** The case-facts section of `context.md`, `case_facts_call.json` (if Claude-driven extraction was used), the unit test output, and the control eval comparison. A reviewer should be able to remove the case-facts block from `context.md` by hand and re-run `--eval` to see Q1 and Q6 break — that's the empirical demonstration of the LO.

**Common failure modes that block mastery.**
- All 12 fields are populated but several are stringified `"None"` or `"unknown"` — passes a naïve null check, fails the *no-silent-fill* contract (AC-03.6).
- Case-facts block is rendered as JSON inside a Markdown fence — passes the token cap but fails the *reviewer-readable* spirit of AC-03.4. The fixed key order and section headers are the requirement.
- Block contains the 12 required fields plus 20 additional narrative ones — bloated, exceeds the 600-token cap, indicates the learner conflated "facts" with "summary."
- Control eval succeeds (Q1/Q6 pass even without case facts) — means the active-verbatim section happens to contain the answer, so the case-facts block is redundant on those questions. The fixture is engineered to prevent this, but learners who alter the fixture can re-introduce the problem.

---

## LO 6 — Trim verbose tool outputs to relevant fields

**SWBAT.** *Students will be able to trim verbose tool outputs to the fields relevant for the immediate decision before those outputs accumulate in context.*

**Exam task.** Task 5.1 (Skills) — tool context pruning (Playbook: Tool Context Pruning).

**Rubric criterion (draft).** Implement deterministic field selection for a verbose tool response and justify each kept field against the decision the tool supports.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-04.1 | `prune_lookup_order(raw)` returns exactly the 5 contracted keys, in order. |
| AC-04.2 | The fixture has ≥ 40 top-level fields — the pruner is genuinely making a selection, not trivially passing through. |
| AC-04.3 | Pruner is deterministic field selection — no `anthropic` import in `pruner.py`. (Verified by AC-08.2 / AST audit.) |
| AC-04.4 | Pruned output ≤ 200 tokens — quantified savings vs the raw response. |
| AC-04.5 | `test_prune_lookup_order` asserts the exact kept set and that a missing required field raises `PrunerMissingFieldError`. |
| AC-04.6 | Pruner module docstring explains *why* each of the 5 kept fields matters for return/refund reasoning — the *justification* is graded, not just the selection. |
| AC-08.2 | AST audit: no `anthropic` client import in `pruner.py` — the LO is deterministic context engineering, not LLM-driven filtering. |

**Reviewer artifact.** `pruner.py` source + its docstring + the unit test output + a side-by-side of the raw vs pruned `lookup_order` response. A reviewer should be able to read the 5 "why" lines and agree they map to return/refund reasoning (not generic "looks important").

**Common failure modes that block mastery.**
- Pruner is implemented as `for k in raw: if k in KEEP: out[k] = raw[k]` — correct, but the docstring is empty. Fails the justification requirement (AC-04.6) which is the LO's actual graded surface.
- Learner extends the kept set to 8 or 10 fields "to be safe" — defeats the LO. Exactly 5, no others.
- Pruner is implemented via a Claude call that "decides" which fields to keep — passes the kept-set assertion, fails AC-08.2's AST audit. The LO targets *deterministic* pruning specifically; LLM-driven field selection is a different (slower, costlier, nondeterministic) discipline.
- Docstring justifications are generic ("important for orders") — the rubric wants explicit traceability to the return/refund decision (e.g., "`return_eligible_until` is the deadline the agent must compare against today's date to decide eligibility").

---

## LO 7 — Place key findings at context boundaries with section headers

**SWBAT.** *Students will be able to place key findings at context boundaries and use explicit section headers to make context structure legible to the model.*

**Exam task.** Task 5.1 (Skills) — position-aware structuring with section headers.

**Rubric criterion (draft).** Use explicit section headers to demarcate context regions and place key findings at the top boundary.

**Acceptance criteria providing evidence**

| AC | Evidence the reviewer sees |
|---|---|
| AC-03.4 | Case-facts block uses Markdown section headers and a fixed key order — structure is legible to the model and the reviewer. |
| AC-06.1 | Assembled context uses the prescribed section headers `# Case Facts`, `# Resolved: …`, `# Active issue: …` in exact order. |
| AC-06.5 | Section boundaries are exclusive — no interleaving — so headers actually demarcate. |
| AC-08.3 | Static audit verifies the header sequence regex-matches the contract. |
| AC-08.6 | README "Why this layout?" section connects header use to model attention (key findings at the top boundary, sectioned middle, verbatim against the user turn). |

**Reviewer artifact.** `context.md` (visual inspection) + the section-order audit output + the README rationale. The Markdown headers are the artifact the model actually sees, so this is one of the few LOs where the *artifact itself* is the primary evidence.

**Common failure modes that block mastery.**
- Section headers use ambiguous text (`## Stuff`, `## More`) — passes the order regex if the regex is loose enough, but the model has no semantic anchor. Exact-text matching on the header strings (AC-06.1) is the defense.
- Case-facts block uses headers but the fields are in a different order on every run (because the learner used a `dict` without ordering) — fails the *fixed key order* requirement of AC-03.4.
- Active-issue section has no header — the learner concatenated turns 29–48 with the original turn markers but skipped the section title, breaking the contract.
- README explains headers as "for readability" rather than as a *model-attention* mechanism — fails the LO 7 framing in the writeup.

---

## Traceability matrix

Every acceptance criterion in `prd.json` traces to at least one LO (or is explicitly tagged infrastructure). The grid below makes the coverage visible.

| AC | LO 1 | LO 2 | LO 3 | LO 4 | LO 5 | LO 6 | LO 7 | Notes |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| AC-01.1–01.6 | | | | | | | | (Docker scaffold — infrastructure) |
| AC-02.1 | | | ✓ | | | | | function signature exposes `.token_count` |
| AC-02.2 | | | | | | | | (fixture shape — infrastructure) |
| AC-02.3 | | | ✓ | | | | | baseline measurement |
| AC-02.4 | | | ✓ | | | | | canonical token-count function, consistent across measurements (algorithm choice is the learner's — Exam Guide out-of-scopes tokenization specifics) |
| AC-02.5 | ✓ | | ✓ | | | | | README documents chosen token-counting methodology (so reviewer can interpret numbers) |
| AC-02.6 | | | ✓ | | | | | test enforces measurement |
| AC-03.1 | | | | | ✓ | | | extraction function exists |
| AC-03.2 | | | | | ✓ | | | extraction mechanism (deterministic or logged Claude call) |
| AC-03.3 | | | ✓ | | ✓ | | | bounded block token cost |
| AC-03.4 | | | | | ✓ | | ✓ | headers + fixed order = section structure |
| AC-03.5 | | | | | ✓ | | | every field populated |
| AC-03.6 | | | | | ✓ | | | no silent null fill |
| AC-04.1 | | | | | | ✓ | | exact kept set |
| AC-04.2 | | | | | | ✓ | | fixture is genuinely verbose |
| AC-04.3 | | | | | | ✓ | | deterministic, not LLM |
| AC-04.4 | | | ✓ | | | ✓ | | token savings |
| AC-04.5 | | | | | | ✓ | | test enforces contract |
| AC-04.6 | | | | | | ✓ | | justification docstring |
| AC-05.1 | | ✓ | | | | | | compression function exists |
| AC-05.2 | | ✓ | | | | | | summary structure |
| AC-05.3 | | ✓ | | | | | | auditable prompt template |
| AC-05.4 | | ✓ | | | | | | byte-exact active preservation |
| AC-05.5 | | ✓ | ✓ | | | | | quantified reduction on resolved portion |
| AC-05.6 | | | ✓ | | | | | API cost ceiling |
| AC-06.1 | | | | ✓ | ✓ | | ✓ | section order — top boundary case facts, headers, exclusive sections |
| AC-06.2 | | | ✓ | | | | | total token cap |
| AC-06.3 | | | | ✓ | | | | active at bottom boundary, byte-exact |
| AC-06.4 | ✓ | | | | | | | `context.md` is the artifact mapped in the anatomy diagram |
| AC-06.5 | | | | ✓ | | | ✓ | exclusive section boundaries |
| AC-06.6 | | | ✓ | | | | | computed `budget.json` |
| AC-07.1 | | ✓ | | | | | | eval pipeline runs against assembled context |
| AC-07.2 | | | | | | | | (eval mechanics — infrastructure) |
| AC-07.3 | | | | | | | | (eval pass rule — infrastructure) |
| AC-07.4 | | ✓ | | | | | | ≥ 5/6 = compression preserved answerability |
| AC-07.5 | | ✓ | | | ✓ | | | control eval proves case-facts block is load-bearing |
| AC-07.6 | | | ✓ | | | | | API cost ceiling |
| AC-08.1 | | | ✓ | | | | | static check: every budget.json count flows through the canonical tokens.count (consistency, not algorithm) |
| AC-08.2 | | | | | | ✓ | | AST: no `anthropic` in pruner |
| AC-08.3 | | | | ✓ | | | ✓ | section-order audit |
| AC-08.4 | | ✓ | | | | | | active byte-exact audit (compression-discipline check) |
| AC-08.5 | ✓ | | | | | | | anatomy diagram |
| AC-08.6 | | ✓ | | ✓ | ✓ | | ✓ | "Why this layout?" — addresses lost-in-the-middle, fidelity tradeoff, AND the pass-complete-history tension; uses "scratchpad" synonym (LO 5 link) |
| AC-08.7 | ✓ | | ✓ | | | | | before/after token table sourced from `budget.json`; methodology named |
| AC-08.8 | ✓ | ✓ | | | | | | "What I'd do next" — adjacent layers + server-side context-editing betas (clear_tool_uses_20250919, compact_20260112) as the modern alternative |
| AC-08.9 | | ✓ | | | | | | eval pass/fail table |

**Per-LO coverage count.**

| LO | # of ACs | Strength |
|---|:-:|---|
| LO 1 (anatomy diagram) | 4 | Adequate — covered by README artifacts + `context.md` as labeled-layer instance. |
| LO 2 (assembly / maintenance / compression) | 9 | **Strongest** — source, prompt template, byte-exact test, two eval runs, and writeup. |
| LO 3 (token cost) | 10 | **Strongest** — measured at every step + AST anti-pattern + computed `budget.json`. |
| LO 4 (lost in the middle) | 5 | Strong — observable in `context.md`, audit, and writeup. |
| LO 5 (case facts) | 7 | Strong — extraction, structure, control eval that empirically isolates the block. |
| LO 6 (tool pruning) | 6 | Strong — deterministic implementation, exact set, justification docstring, AST audit. |
| LO 7 (boundaries + headers) | 5 | Adequate — header-text contract + section-order audit + writeup. |

No LO has fewer than four evidencing acceptance criteria. LO 2 and LO 3 are over-instrumented because they are the two cross-cutting LOs that all the per-feature stories funnel into.

---

## From this document to the rubric

This document is the **bridge artifact**. To produce the actual rubric (per [`project_guidance.md`](../../content-guidance-files/project_guidance.md)):

1. **Criteria column.** Take each LO's "Rubric criterion (draft)" line, written in *"The student will be able to..."* form, project-context-free per the guidance. There are 7 criteria — within the 3–9 range Udacity prefers.
2. **Submission Requirements column.** Take the "Acceptance criteria providing evidence" tables and rewrite each AC as a measurable, present-tense, binary requirement (e.g., *"The assembled `context.md` contains the section headers `# Case Facts`, `# Resolved: Refund inquiry`, `# Resolved: Subscription cancellation`, and `# Active issue: Payment-method update` in that exact order."*).
3. **Reviewer Tips column.** Take the "Common failure modes that block mastery" lists and rewrite as testing suggestions and edge-case guidance.
4. **Stand Out Suggestions.** Pull from PRD Section 7 (Open Questions) leans:
   - OQ-3: ship a "lost in the middle" *negative* variant with case facts placed mid-history and quantify the position effect against eval.
   - OQ-6: run Q3/Q4 against a variant where the active segment is *also* summarized, demonstrating the fidelity loss the verbatim choice avoids.
   - **OQ-7: run the same scenario through the server-side context-editing betas (`clear_tool_uses_20250919`, `compact_20260112`) and compare token-budget outcomes against this project's application-side pruning. This is the contrast Exam Task 5.1 emphasizes ("before they accumulate in context") — a publishable result for LO 2 + LO 6.**
   - Any of these is a one-day extension.

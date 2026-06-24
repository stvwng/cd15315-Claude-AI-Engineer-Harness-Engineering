# PRD — Retail Customer Support Context Strategy

**Module:** 2 — Context Engineering Foundations
**Course:** 1 — Harness Engineering
**Industry Vertical:** Retail
**Status:** Draft v0.2
**Estimated learner effort:** ~4 hours
**Runtime budget:** Docker container, $25 Anthropic API credit (project consumes ≤ $3)

**Revision history**
- v0.2.1 — Fixture-grounded target update: the engineered 48-turn transcript fixture is 47k tokens (Sonnet authored at the upper edge of realism — ~980 tokens/turn). Baseline range updated to [42000, 52000], assembled cap to ≤ 24000, reduction floor to ≥ 50%. Numbers are now grounded in the actual exemplar, not a pre-fixture estimate.
- v0.2 — Exam-guide / Playbook / cookbook alignment pass:
  - Token-counting mechanics softened (AC-02.4, AC-08.1, OQ-1) — Exam Guide explicitly out-of-scopes "token counting algorithms or tokenization specifics."
  - "Why this layout?" writeup must address the *pass-complete-history* tension (AC-08.6) — Exam Guide Task 5.1 Knowledge bullet on conversational coherence.
  - Server-side context-editing (`clear_tool_uses_20250919`, `compact_20260112`) named as the modern API-level alternative (new OQ-7, extended AC-08.8) — the assigned cookbooks teach the server-side pattern and learners should see the contrast.
  - Case-facts ↔ "scratchpad" synonym recognized in README (AC-08.6) — Playbook uses "scratchpad," exam guide uses both.
  - NG-12 added: Claude Code `/compact` mechanism is out of scope (Module 8).
  - Default model `claude-haiku-4-5` retained but justified as a learning-budget choice; labs use Sonnet 4.6 (FR-2 note).

---

## 1. Overview

A retail support team has a single customer conversation that has run **48 turns** across **three issues**: a refund inquiry (turns 1–14, resolved), a subscription cancellation (turns 15–28, resolved), and a payment-method update (turns 29–48, **still active**). The raw transcript is ~**47,000 tokens**. If naively appended to every next assistant turn, it (a) blows past the cheap-tier context budget on every call, (b) makes Claude scan thousands of tokens of *resolved* narrative to answer a question about the *current* issue, and (c) suffers the "lost in the middle" effect — the most relevant facts (current order ID, payment failure code) are buried mid-history.

The learner's job is to **design and implement a context-management strategy** that compresses this transcript into a context block which:

1. **Extracts transactional case facts** (order IDs, amounts, statuses, dates) into a persistent structured block placed at the top of context.
2. **Prunes verbose tool outputs** — the support team's `lookup_order` MCP tool returns 40+ fields per order, but only 5 are relevant to a return/refund decision.
3. **Compresses resolved issues** into short factual summaries (≤ 500 tokens each).
4. **Preserves the active issue verbatim** so the model can reason over the live turn-by-turn nuance.
5. **Lays out the assembled context position-aware** — key findings at the top boundary, resolved-issue summaries in the middle (the "compressible zone"), active issue verbatim at the bottom boundary, ahead of the new user turn.

The strategy must demonstrably reduce the context block from ~47,000 tokens to ≤ **24,000 tokens** (≥ 50% reduction) **without losing answerability** on a fixed set of evaluation questions whose answers span all three issues.

This is a **Layer 1 + Layer 2** exercise. There is no MCP server, no multi-agent coordinator, no hooks. The harness owns context assembly, compression, and pruning. The model is only invoked twice — once to summarize each resolved issue, and once per evaluation question to verify answerability — and never to make routing or control-flow decisions.

**What the learner submits:** a Python package that runs inside the provided Docker image, ingests the fixture transcript, produces a compressed context block (`runs/<run_id>/context.md`), and runs 6 evaluation questions against that block, writing per-question results to `runs/<run_id>/eval.jsonl`.

## 2. Goals

- **G1.** Make the layers of context-window assembly *executable and inspectable* — the learner produces a real artifact (`context.md`) they can diff against the raw transcript.
- **G2.** Force position-aware design: case facts at the top, resolved summaries in the middle, active issue at the bottom — observable in the assembled artifact.
- **G3.** Demonstrate that compression does not erase answerability — eval questions whose answers come from compressed segments must still be answerable.
- **G4.** Stay buildable in ~4 hours and well under $3 of API spend across development, testing, and grading.

## 3. User Stories

User stories follow the form *"As a [role], I want [feature] so that [benefit]."* Each story carries an acceptance-criteria checklist of verifiable items. The Definition of Done for a story is: **all criteria met + quality checks (typecheck, tests, lint) green + changes committed**. State is tracked in `prd.json` via `passes: true|false` per story.

> **Roles used below:** *learner* (the student building the project), *support lead* (the business stakeholder the strategy serves), *reviewer* (the Udacity rubric reviewer).

---

### US-01 — Project scaffold runs in Docker

**As a** learner, **I want** a runnable Docker-based project skeleton **so that** I can start building without fighting environment setup.

**Acceptance criteria**
- [ ] `docker compose up` (or `docker build && docker run`) starts the container without error.
- [ ] `ANTHROPIC_API_KEY` is read from env; the container fails fast with a clear message if it is missing.
- [ ] `python -m retail_context --version` prints a semver string and exits 0.
- [ ] `pyproject.toml` pins `anthropic` to a specific version.
- [ ] `pytest` runs and reports at least one passing smoke test (`test_hello_claude` that issues a 1-token call and asserts `stop_reason in {"end_turn","max_tokens"}`).
- [ ] `mypy` (or `pyright`) passes on the `retail_context/` package.

---

### US-02 — Transcript loader and baseline token accounting

**As a** learner, **I want** to load the 48-turn transcript and measure its baseline token cost **so that** every later compression step has a concrete number to beat.

**Acceptance criteria**
- [ ] `retail_context.transcript.load(path) -> Transcript` returns a typed object exposing `.turns` (list of `{turn, role, text, issue_id}`), `.segments` (the three issue-partitioned slices), and `.token_count` (int).
- [ ] The fixture `data/transcript_48turns.json` contains exactly **48 turns**, partitioned into `issue_id ∈ {"refund","subscription","payment_update"}` with the boundary turns documented as `refund: 1–14`, `subscription: 15–28`, `payment_update: 29–48`.
- [ ] Baseline `.token_count` for the full transcript is ≥ **42,000** and ≤ **52,000** tokens (engineered fixture target ~47,000).
- [ ] Token counting uses a single canonical function `retail_context.tokens.count(text)` that is invoked consistently for every measurement in the project (baseline, per-section, post-compression). The *algorithm* is the learner's choice (Anthropic `count_tokens` endpoint, `tiktoken cl100k_base`, or a documented deterministic estimator); the *consistency* is what's graded. (Exam Guide explicitly out-of-scopes "token counting algorithms or tokenization specifics," so we grade methodology, not arithmetic.)
- [ ] Chosen token-counting methodology is documented in README in one sentence so the reviewer can interpret the reported numbers.
- [ ] Unit test `test_transcript_loader` asserts turn count, partition boundaries, and that `.token_count` lies in the engineered range.

---

### US-03 — Case-facts extraction into a persistent block

**As a** support lead, **I want** the structured transactional facts of the conversation pulled into a single block at the top of context **so that** the model never has to scan 47k tokens of narrative to recover an order ID, refund amount, or payment status.

**Required extracted fields** (across the three issues):

| Field | Example | Source issue |
|---|---|---|
| `customer_id` | `CUST-88421` | refund (turn 3) |
| `refund_order_id` | `ORD-77310` | refund (turn 5) |
| `refund_amount_usd` | `22.14` | refund (turn 10, after the agent corrects the customer's misread of a section subtotal) |
| `refund_status` | `processed` | refund (turn 14) |
| `subscription_id` | `SUB-22119` | subscription (turn 16) |
| `subscription_plan` | `Pantry Plus Monthly` | subscription (turn 17) |
| `subscription_cancel_reason` | `duplicate_charge` | subscription (turn 23) |
| `subscription_status` | `cancelled_with_prorated_refund` | subscription (turn 28) |
| `active_payment_method_last4` | `4242` | payment_update (turn 31) |
| `new_payment_method_last4` | `7782` | payment_update (turn 39) |
| `payment_update_failure_code` | `AVS_MISMATCH` | payment_update (turn 44) |
| `payment_update_status` | `in_progress` | payment_update (active) |

**Acceptance criteria**
- [ ] `retail_context.case_facts.extract(transcript) -> CaseFacts` returns a dataclass / pydantic model containing the 12 fields above.
- [ ] Extraction may be implemented either deterministically (regex/parse) or via a single Claude call against the transcript. If a Claude call is used, the call is **logged** (input + output) to `runs/<run_id>/case_facts_call.json` and uses `claude-haiku-4-5` by default.
- [ ] The serialized case-facts block is ≤ **600 tokens** (verified by `retail_context.tokens.count`).
- [ ] The block is rendered with explicit section headers and a fixed key order; the format is human-readable Markdown, not raw JSON. (Reviewer reads the artifact directly.)
- [ ] Unit test `test_case_facts_extraction` asserts every required field is populated and is non-null for the fixture transcript.
- [ ] Missing-field behavior: if any required field cannot be located in the transcript, extraction raises `CaseFactExtractionError` listing the missing fields — it does **not** silently fill with `null` or `"unknown"`.

---

### US-04 — Tool-output pruning for verbose `lookup_order` responses

**As a** support lead, **I want** the `lookup_order` MCP tool's 40+ field response trimmed to the 5 fields relevant for return-eligibility reasoning **so that** verbose tool outputs do not balloon context as the conversation accumulates.

**Pruning contract.** The fixture `data/lookup_order_response.json` contains a single order record with **≥ 40 fields** including marketing flags, geo metadata, fulfillment partner identifiers, internal warehouse codes, etc. The pruner must return exactly the following five fields for downstream context:

| Kept field | Why it matters for return/refund reasoning |
|---|---|
| `order_id` | identity |
| `order_date` | return-window eligibility |
| `order_total_usd` | refund-amount cap |
| `fulfillment_status` | whether the item shipped / was delivered |
| `return_eligible_until` | the deadline the agent must reason about |

**Acceptance criteria**
- [ ] `retail_context.pruner.prune_lookup_order(raw: dict) -> dict` returns a dict with exactly the 5 keys above, in that order, and no others.
- [ ] `data/lookup_order_response.json` contains ≥ 40 distinct fields at the top level.
- [ ] Pruner is implemented as **deterministic field selection**, not an LLM call. (Cost and reproducibility — verified by US-07's anti-pattern audit.)
- [ ] Pruned output is ≤ **200 tokens** (`retail_context.tokens.count`).
- [ ] Unit test `test_prune_lookup_order` asserts the kept set is exactly `{order_id, order_date, order_total_usd, fulfillment_status, return_eligible_until}` and that pruning a response that is missing one of these raises `PrunerMissingFieldError`.
- [ ] Pruner module contains a docstring explaining **why** each of the 5 fields is kept (each "why" must reference return/refund reasoning, not a generic "looks important").

---

### US-05 — Tiered compression: resolved issues summarized, active issue verbatim

**As a** learner, **I want** resolved issues compressed into short factual summaries while the active issue is preserved verbatim **so that** the model has high-fidelity context where decisions are still being made and low-cost context where they are not.

**Acceptance criteria**
- [ ] `retail_context.compressor.summarize_segment(segment: Segment) -> Summary` produces a ≤ **500-token** factual summary for the `refund` and `subscription` segments.
- [ ] Each summary contains: an opening one-sentence outcome statement, a bulleted list of the 3–6 most decision-relevant facts, and a closing one-sentence resolution statement. (Structure is enforced by a system-prompt template, not by post-hoc parsing.)
- [ ] Compression is implemented as a Claude call using `claude-haiku-4-5` by default, model configurable via env / CLI. The exact prompt template lives at `retail_context/prompts/compression_prompt.md` so reviewers can audit it.
- [ ] The active `payment_update` segment is **never summarized** — it is preserved byte-exact. Unit test `test_active_segment_preserved_verbatim` asserts `compressor.compress(transcript).active_text == "".join(turn.text for turn in transcript.active_turns)`.
- [ ] Combined token cost across both resolved-issue summaries is ≤ **1,000 tokens**, vs ≥ ~20,000 raw tokens for the same content — i.e., the compressor delivers ≥ 95% reduction on the *resolved* portion.
- [ ] Cost guard: total API spend for one full compression pass on the fixture (both summaries) is ≤ **$0.10** as estimated from token counts × Haiku pricing.

---

### US-06 — Position-aware context assembly

**As a** support lead, **I want** the final assembled context to place key findings at the top boundary, resolved-issue summaries in the compressible middle, and the active issue immediately above the new user turn **so that** the "lost in the middle" attention effect works in our favor rather than against us.

**Required layout** (top to bottom, in the assembled `context.md`):

```
# Case Facts                  ← top boundary, most attention
(structured block from US-03, ≤ 600 tokens)

# Resolved: Refund inquiry    ← middle, compressible zone
(summary from US-05, ≤ 500 tokens)

# Resolved: Subscription cancellation
(summary from US-05, ≤ 500 tokens)

# Active issue: Payment-method update   ← bottom boundary, full attention
(verbatim turns 29–48, ~14,500 tokens)
```

**Acceptance criteria**
- [ ] `retail_context.assemble.build(transcript) -> AssembledContext` produces a context object whose `.markdown` property matches the layout above, with section headers `# Case Facts`, `# Resolved: …`, `# Active issue: …` in that exact order.
- [ ] Total assembled token count is ≤ **24,000 tokens** (≥ 50% reduction from baseline).
- [ ] Active-issue section's body is byte-exact equal to the raw turns 29–48 concatenated with their original turn headers (`Turn 29 (customer): …`, etc.).
- [ ] `runs/<run_id>/context.md` is the assembled artifact written to disk for the reviewer to read directly.
- [ ] Anti-pattern: assembler does **not** interleave resolved-issue summaries with active-issue text (no "weaving"). Section boundaries are exclusive.
- [ ] `runs/<run_id>/budget.json` records `baseline_tokens`, `assembled_tokens`, `reduction_pct`, and per-section token counts. The reduction percentage is computed, not hardcoded.

---

### US-07 — Evaluation: compressed context preserves answerability

**As a** reviewer, **I want** a fixed set of evaluation questions answered against the compressed context **so that** I can grade whether the compression strategy preserved the information the agent will actually need.

**Evaluation questions** (`data/eval_questions.json`):

| # | Question | Expected answer fragment | Source segment |
|---|---|---|---|
| Q1 | "What was the actual refund amount processed for order ORD-77310?" | `22.14` | case facts (the agent's corrected figure, not the customer's misread of $48.99) |
| Q2 | "Why did the customer cancel their subscription?" | `duplicate_charge` or "duplicate charge" | subscription summary |
| Q3 | "What is the failure code on the current payment-method update?" | `AVS_MISMATCH` | active (verbatim) |
| Q4 | "What is the last-4 of the new card the customer is trying to add?" | `7782` | active (verbatim) |
| Q5 | "Did the customer receive their subscription proration refund?" | `yes` / `cancelled_with_prorated_refund` | subscription summary |
| Q6 | "What is the structured status of the payment-method update issue (exact status token)?" | `in_progress` | case facts (the active verbatim narrates the issue in prose but never uses the structured status token) |

**Acceptance criteria**
- [ ] `python -m retail_context.run --eval` loads the assembled context (US-06), then issues one Claude call per question with the assembled context as the system prompt and the question as a user turn.
- [ ] Per-question results are written to `runs/<run_id>/eval.jsonl` with fields `{question_id, question, expected_fragment, model_answer, passed, input_tokens, output_tokens}`.
- [ ] A question passes when `expected_fragment.lower()` appears as a substring in `model_answer.lower()`. (Substring match is intentionally lenient — this story tests *information preservation*, not exact answer formatting.)
- [ ] **Pass threshold:** ≥ **5/6** questions pass. Failing 2+ indicates compression lost decision-relevant information.
- [ ] The eval suite also runs a **control** variant where the same questions are issued against the assembled context with the case-facts block *removed*. At least **one** of Q1/Q6 must fail in the control. Q6 is the strict test (its expected fragment `in_progress` appears only in the case-facts block — the active verbatim describes the state in prose but never uses the structured token), so Q6 failing is required; Q1's behavior depends on whether the resolved-refund summary preserved the numeric value verbatim. (Verifies the case-facts block is doing real work for at least one structured-token answer, not redundant with the summaries and verbatim section.)
- [ ] Total API spend for one `--eval` pass (6 questions + 2 control questions) is ≤ **$0.25**.

---

### US-08 — Anti-pattern audit + README writeup

**As a** reviewer, **I want** automated checks plus a README writeup that confirm the learner avoided Module 2's anti-patterns and can articulate the context-engineering rationale **so that** grading is consistent.

**Acceptance criteria**
- [ ] `pytest tests/test_antipatterns.py` passes with the following checks:
  - Static: every token count in `runs/<run_id>/budget.json` is produced by the single canonical `retail_context.tokens.count` function (no ad-hoc `len(...)` or alternative counter elsewhere in the package). Consistency, not algorithm, is enforced.
  - AST: `retail_context/pruner.py` contains no `anthropic` client import — pruning is deterministic, not LLM-driven.
  - Static: `retail_context/assemble.py` builds sections in the order Case Facts → Resolved → Active. (Regex check on the section header sequence in the assembled output.)
  - Static: the verbatim active segment in `context.md` matches the raw turns 29–48 byte-for-byte (no whitespace normalization, no token stripping).
- [ ] `README.md` includes:
  - A **context-window anatomy diagram** (ASCII or Mermaid) showing the five layers: system prompt → CLAUDE.md → memory → conversation history → current turn (LO 1).
  - A **"Why this layout?"** section (4–6 sentences) that (a) explains the position choices in terms of the "lost in the middle" effect (LO 4), (b) explains the resolved-vs-active fidelity tradeoff (LO 2), and (c) explicitly addresses the *pass-complete-history* default — naming the tension between "preserve full conversation history for coherence" (the Exam Guide Task 5.1 baseline) and this project's deliberate compression of *resolved* threads only, with the active thread preserved verbatim. One sentence must use the word "scratchpad" so learners recognize the synonym used in the Architect's Playbook for what this project calls the case-facts block.
  - A **before/after token table** showing per-section token counts pre-compression vs post-compression (LO 3), pulled from `runs/<run_id>/budget.json`. Token-counting methodology is named in one sentence so the reviewer can interpret the numbers.
  - A **"What I'd do next"** section (4–6 bullets) that names at least: (a) session resumption (Module 9 preview), and (b) **server-side context editing** as the modern API-level alternative — specifically `clear_tool_uses_20250919` (beta `context-management-2025-06-27`) and `compact_20260112` (beta `compact-2026-01-12`) — and contrasts when application-side pruning (this project) is preferable vs when to let the API manage it.
- [ ] README links the eval results (`eval.jsonl`) and shows the per-question pass/fail table for one graded run.

---

## 4. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Single Python package `retail_context/` runnable as `python -m retail_context`. |
| FR-2 | All Claude calls go through `retail_context.client` which reads `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` from env. Default model `claude-haiku-4-5` (learning-budget choice — Module 2 cookbooks default to `claude-sonnet-4-6`, which is the easy upgrade if Haiku underperforms on summarization quality). |
| FR-3 | Token counting uses `retail_context.tokens.count(text)` — a single canonical function — invoked consistently for every measurement in the project. Algorithm choice (Anthropic `count_tokens`, `tiktoken`, deterministic estimator) is the learner's; consistency is what's graded. |
| FR-4 | Compression of resolved segments is implemented as Claude calls; pruning of tool outputs is deterministic field selection. These two MUST NOT swap mechanisms. |
| FR-5 | Assembled context is written to `runs/<run_id>/context.md` as the canonical reviewer artifact. Token accounting is written to `runs/<run_id>/budget.json`. Eval results are written to `runs/<run_id>/eval.jsonl`. |
| FR-6 | Active segment (turns 29–48) is preserved byte-exact in the assembled output. Verified by `tests/test_antipatterns.py`. |
| FR-7 | Total project API spend across one `--all` pipeline run (compress + eval + control) is ≤ **$0.50**. |

## 5. Non-Goals

- **NG-1.** No live customer chat. The 48-turn transcript is the only input.
- **NG-2.** No dynamic / automatic compression triggers (e.g., compress when context > 50k). The compression strategy is *static* — it knows resolved vs active a priori from the fixture's `issue_id` annotations. Dynamic triggers are Module 9 territory.
- **NG-3.** No MCP servers. `lookup_order` is represented by a static JSON fixture, not a running MCP tool. MCP is Course 2.
- **NG-4.** No session resumption (`--resume`), no `/clear`. Layer 2 maintenance is *explained* in the README writeup but not *implemented* — Module 9.
- **NG-5.** No multi-agent orchestration, no sub-agents, no hooks. (Course 4 territory.)
- **NG-6.** No prompt caching, no batch API, no streaming. (Optional stretch, not graded.)
- **NG-7.** No PII redaction or compliance posture. Fixture data is synthetic.
- **NG-8.** No fine-tuned summarizer, no local LLM. Compression goes through the Anthropic API.
- **NG-9.** No CLAUDE.md / memory file integration. Those layers are *diagrammed* in the README but not used by this project — Module 8.
- **NG-10.** No Claude Code `/compact` slash command. `/compact` is a Claude Code harness mechanism (Exam Task 5.4) — not an API-level surface — and is taught in Module 8.
- **NG-11.** No **server-side** context-editing beta APIs (`clear_tool_uses_20250919`, `compact_20260112`). The Module 2 labs *demonstrate* these; this project deliberately teaches the **application-side** counterpart so learners can compare the two strategies. README "What I'd do next" names the server-side alternative explicitly (AC-08.8).

## 6. Success Metrics

| Metric | Target |
|---|---|
| Baseline transcript token count (fixture) | ≥ 42,000 and ≤ 52,000 |
| Assembled context token count | ≤ 24,000 |
| Reduction vs baseline | ≥ 50% |
| Resolved-segment summaries token cost | ≤ 1,000 combined |
| Case-facts block token cost | ≤ 600 |
| Pruned `lookup_order` response token cost | ≤ 200 |
| Active-segment byte-exact preservation | passes |
| Eval pass rate (compressed context) | ≥ 5/6 |
| Control eval (Q1, Q6 without case facts) | both fail (compression-block is load-bearing) |
| Anti-pattern audit | passes |
| Total API spend per full pipeline run | ≤ $0.50 |
| Total learner API spend (dev + tests + grading) | ≤ $3 of $25 budget |
| Learner build time, end to end | ~4 hours |
| All `prd.json` stories with `passes: true` | 8/8 |

## 7. Open Questions

- **OQ-1.** Token counter: any consistent methodology works (Exam Guide out-of-scopes the algorithm). One-line README sentence names the choice. *Resolved as informational; no scaffolding decision required.*
- **OQ-2.** Should the case-facts block be extracted by Claude (one extra API call per run) or by deterministic parsing of the fixture (zero API cost, but the fixture is "annotated" — less realistic)? Current lean: Claude extraction, since the LO is *extraction*, not parsing. Cost is bounded by US-03's ≤ $0.10 ceiling.
- **OQ-3.** Should we ship a "lost in the middle" *negative* variant — same context but with case facts placed mid-history — and run eval against both to show the position effect quantitatively? *Stand-out suggestion, not required.*
- **OQ-4.** The active-issue boundary is currently fixed at turn 29. Should learners be required to *detect* the boundary (last unresolved issue) themselves, or is the fixture annotation acceptable? Detection is a richer exercise but moves into Module 9 territory.
- **OQ-5.** Compression prompt template (`prompts/compression_prompt.md`) — do we provide it as a starter or require learners to write their own? Current lean: provide a starter; the *strategy* is the LO, not prompt-craft.
- **OQ-6.** Should Q3 and Q4 (active-segment questions) be tested against a context where the active segment is also summarized, to show the fidelity loss? Would strengthen LO 2 evidence. *Stand-out suggestion.*
- **OQ-7.** Application-side pruning (this project) vs server-side context editing (`clear_tool_uses_20250919`, `compact_20260112`). The Module 2 cookbooks teach the server-side pattern; this project teaches the application-side counterpart that Exam Task 5.1 emphasizes ("Trimming verbose tool outputs to only relevant fields **before they accumulate in context**"). Should we ship an optional appendix lab that runs the same scenario through the server-side beta and compares token-budget outcomes? *Stand-out suggestion; would strengthen LO 2 + LO 6 contrast.*
- **OQ-8.** Default model: Haiku 4.5 keeps the project under $0.50/run; Sonnet 4.6 matches the cookbook labs and may produce higher-fidelity summaries. Decision deferred to build team after first full pass on the fixture. (Learners may override via `--model`.)

---

## Appendix A — Repo layout (informative)

```
module-02-retail-context-strategy/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── retail_context/
│   ├── __init__.py
│   ├── __main__.py
│   ├── client.py               # Anthropic client + model config
│   ├── tokens.py               # canonical token-count function (US-02)
│   ├── transcript.py           # loader + segmentation (US-02)
│   ├── case_facts.py           # extraction into persistent block (US-03)
│   ├── pruner.py               # tool-output pruning (US-04)
│   ├── compressor.py           # resolved-segment summarization (US-05)
│   ├── assemble.py             # position-aware assembly (US-06)
│   ├── evaluate.py             # eval-question runner (US-07)
│   ├── run.py                  # CLI entry point
│   └── prompts/
│       └── compression_prompt.md
├── data/
│   ├── transcript_48turns.json
│   ├── lookup_order_response.json
│   └── eval_questions.json
├── tests/
│   ├── test_transcript.py
│   ├── test_case_facts.py
│   ├── test_pruner.py
│   ├── test_compressor.py
│   ├── test_assemble.py
│   ├── test_evaluate.py
│   └── test_antipatterns.py
└── spec/
    ├── PRD.md
    ├── prd.json
    └── learning_objectives.md
```

## Appendix B — Definition of Done (per story)

A story flips `passes: true` in `prd.json` when **all** of the following hold:

1. Every acceptance-criteria checkbox is checked.
2. `pytest` is green for the test files this story touches.
3. `mypy` (or `pyright`) is green for the package.
4. `ruff` (or equivalent) is green.
5. Changes for this story are committed with a message referencing the story ID (e.g., `US-04: deterministic lookup_order pruner`).

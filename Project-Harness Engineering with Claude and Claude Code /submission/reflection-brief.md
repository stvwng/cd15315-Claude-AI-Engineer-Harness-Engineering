# Reflection Brief — Harness Engineering Capstone

**Name:** Steve Wang
**Date:** 2026-07-25

**Environment**

- Model(s): `claude-haiku-4-5-20251001` (System 1 baseline, System 2 all calls); `claude-sonnet-4-6` (System 1 comparison run); System 4 run fully offline against `fixtures/recorded_responses/shift_C_2026-04-30.json`; System 3 needs no API.
- OS / Python: macOS (Darwin 25.5.0, arm64) / Python 3.12.3, one `uv` venv per system.
- Approx. API spend: **~$1.10**. System 1 is exact from its own estimator — $0.1338 (Haiku baseline `20260725_180221`) + $0.1332 (Haiku re-run) + $0.4180 (Sonnet `20260725_180619`) + $0.2006 (nudged re-run `20260725_182216`) = **$0.8856**. System 2 adds an estimated ~$0.21 (compression 23,809 in / 904 out from `budget.json`, plus one case-facts call and 8 eval calls). Systems 3 and 4 cost $0 — System 4 ran fully offline against a recorded response.

**Test results — all four suites, matching the expected counts**

| System | Suite | Result | Evidence |
|---|---|---|---|
| 1 — Claims intake | `pytest tests/ -v` | **29 passed** | `system-1-claims-intake/pytest-output.txt` |
| 2 — Context strategy | `pytest tests/ -v` | **30 passed** | `system-2-retail-context/pytest-output.txt` |
| 3 — Claude Code config | `pytest tests/ -v` | **35 passed** | `system-3-claude-code-config/pytest-output.txt` |
| 4 — Orchestration | `pytest tests/ -v` | **33 passed** | `system-4-shift-monitor/pytest-output.txt` |

> **Flag up front, detailed in Q19 and Q20:** the **unmodified** System 1 reference implementation did **not** get all 8 claims to a terminal tool — the best baseline run routed 4 of 8 and the rest ended `incomplete`, reproducibly, on two different models. I root-caused it, then implemented the harness fix I propose in Q20 and re-ran: **8/8 terminated, 7 routed + 1 escalated, every outcome matching its fixture's expectation.** Both sets of artifacts are submitted — the baseline failure and the fix — because the contrast is the most useful thing I produced. Everything below cites what actually happened.

---

## Part 1 — Per-system

### System 1 — Agentic loop

**1. Loop control.** From `system-1-claims-intake/traces-haiku-20260725_180221/claim_05_auto_collision.jsonl`, the full `stop_reason` sequence is:

```
turn 1: tool_use  → lookup_policy, record_claim_fact ×6
turn 2: tool_use  → classify_claim
turn 3: tool_use  → assess_severity
turn 4: tool_use  → route_to_adjuster        ← terminal tool
turn 5: end_turn  → (no tool calls)          ← loop returns
```

The decision lives in `claims_intake/loop.py`, function `run()`. It is a three-way branch on `response.stop_reason` and nothing else: line 103 `if response.stop_reason == "end_turn"` appends the assistant message and `return`s a `FinalState`; line 113 `if response.stop_reason == "tool_use"` executes every `tool_use` block, appends the results as a `user` message, and `continue`s; anything else falls through to line 130 and raises `UnexpectedStopReason`. Note what the loop does *not* inspect — it never reads the assistant's text, never checks which tool was called, and never counts to a limit. `route_to_adjuster` at turn 4 does not stop the loop; the *model* stops it at turn 5 by emitting `end_turn`.

**2. Anti-pattern.** `tests/test_antipatterns.py::test_no_integer_literal_iteration_cap_in_loop` walks `loop.py`'s AST and fails on any `for _ in range(<int literal>)` or `while <x> < <int literal>`. Budgets are allowed only when sourced from a `Budget` instance rather than a literal. Had the loop used `for _ in range(5)`, my own run would have silently truncated `claim_03_water_damage`, which took **8 turns** in the Haiku re-run because it spent a turn on `request_clarification` — an arbitrary cap of 5 would have cut it off mid-conversation and reported failure for a claim that was actually progressing. The real guard is `Budget(max_input_tokens=500_000, max_wall_clock_s=180.0)`, which bounds cost rather than conversation shape.

**3. Tool design.** `route_to_adjuster` and `escalate_to_human` are the overlapping pair — both are terminal, both accept the accumulated case file, and either could plausibly end a claim. The descriptions disambiguate with a numeric threshold rather than a vibe: `route_to_adjuster` says "Call this exactly once when classification confidence is at least 0.6 and severity has been assessed," while `escalate_to_human` says "when classification confidence is below 0.6 even after clarification, or when the claim cannot be routed safely." Both are prefixed `TERMINAL TOOL.` and both close with "After this, your next response should be a brief confirmation and stop with end_turn" — so the description carries the loop contract, not just the semantics. On errors, `tools.py::_err()` returns `{"is_error": true, "error_category": ..., "is_retryable": ..., "message": ...}`. The `is_retryable` flag is what a bare string could not give: the model can distinguish "this will never work, escalate" from "transient, try once more," without parsing prose. The system prompt leans on exactly this — "Tool errors return JSON with `is_error: true`. Read the message and adapt — do not retry blindly."

**4. Your numbers.** From `summary-haiku-20260725_180221.md`, `claim_05_auto_collision`: **5 turns, 18,696 input / 921 output tokens, $0.0233, 9.4s**, outcome `routed` (auto, high). Against the Sonnet run (`summary-sonnet-20260725_180619.md`) the same claim took **6 turns, 22,212 / 1,122 tokens, $0.0835** — 3.6× the cost for one extra turn and the same routing decision. The token growth is superlinear in turns because every turn resends the whole transcript plus accumulated tool results: turn 1 costs ~3.5k input, but by turn 5 the conversation carries all six `record_claim_fact` results and the policy record. This is why the run's total ($0.1338 across 8 claims) is dominated by the claims that took 5+ turns — the three 2-turn `incomplete` claims cost $0.0084–$0.0090 each, roughly a third of a completed one.

### System 2 — Context strategy

**5. The reduction.** From `system-2-retail-context/budget.json` (run `20260725-181019`): **baseline 38,708 tokens → assembled 16,905 tokens, a 56.33% reduction**, comfortably past the 50% bar. Token counts come from the Anthropic `messages.count_tokens` endpoint, recorded in the artifact as `"token_counter_methodology": "Anthropic messages.count_tokens endpoint (model-authoritative)"` — not a heuristic. The `active` section dominates at **15,789 of 16,905 tokens (93.4%)**. It stays verbatim because it is the unresolved payment-method thread — the thing the copilot is still working on. Summarizing an open issue would destroy exactly the detail the next turn needs: the `AVS_MISMATCH` code, the card last-4 `7782`, and what has already been tried.

**6. Summarize vs preserve.** The rule the numbers reveal: **resolved threads get summarized, the open thread and the structured facts stay byte-exact.** The two resolved segments compress to `resolved_refund` **363 tokens** and `resolved_subscription` **567 tokens** — together 930 tokens, down from the 12,334 and 11,475 input tokens the compressor consumed to produce them (`budget.json` → `compression_api`). That is a ~96% cut on the resolved material. Meanwhile `case_facts` is only **204 tokens** but is never compressed, because it holds the exact tokens an answer must reproduce. The asymmetry is the point: the biggest savings come from the segments where only the outcome matters, and the smallest section is the one you must not touch.

**7. Facts block.** `eval.jsonl` shows **6/6 passed**. `eval_control.jsonl` re-runs Q1 and Q6 with the case-facts block stripped: **Q1 still passes, Q6 fails.** Q6 asks for "the structured status of the payment-method update issue (use the exact status token from the case record, not a paraphrase)" and the control answer states there is "no structured status token or case record information" available. Q1 (the $22.14 refund amount) survives because that figure is also recoverable from the surviving conversational text. That contrast is the actual proof: the facts block is not redundant compression padding — it is load-bearing for precisely the questions whose answers are *tokens* rather than *narrative*. A summary can paraphrase "the refund went through"; it cannot be trusted to preserve `AVS_MISMATCH` verbatim.

### System 3 — Claude Code config

**8. Path-scoped rules.** From `system-3-claude-code-config/claude-config/.claude/rules/tests.md`:

```yaml
---
description: Conventions for test files (co-located *.test.ts and *.test.tsx)
paths:
  - "**/*.test.tsx"
  - "**/*.test.ts"
---
```

The `**/` glob is the whole argument. Test files in this monorepo are co-located next to the code they test, so they are scattered across `src/components/`, `src/pages/`, and `src/api/`. A directory-level `CLAUDE.md` attaches conventions to a *location*; this rule attaches them to a *file shape*, wherever it lives. Reproducing the same effect with directory files would mean copying identical testing conventions into every directory that happens to contain a test — three copies today, and a silent drift problem the first time someone edits one. The other two rules scope by location precisely because their conventions *are* locational: `react.md` uses `src/components/**/*` and `src/pages/**/*`, `api.md` uses `src/api/**/*`.

**9. Forked skill.** From `.claude/skills/deploy-check/SKILL.md`:

```yaml
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git rev-parse:*)
  - Bash(git ls-files:*)
```

`context: fork` buys context isolation: the check reads a pile of diffs and git history, and none of that noise lands in the main session's window — only "a single pass/fail summary" comes back, per the skill's own description. The `allowed-tools` list buys the safety half, and note it is enforced at the *argument* level, not the tool level: `Bash(git status:*)` permits `git status` but not `git push`. There is no `Write`, no `Edit`, no unrestricted `Bash`. Without the fork, a pre-deploy check would burn the main context on transcript the user never asked to see, and the interesting failure mode is subtle — the main session would then reason over half-remembered diff fragments. Without the allowlist, a "check" could mutate the tree it is supposed to be inspecting.

**10. Scope.** The validator (`validator-output.txt`: `OK`, exit code 0) enforces this via `distinguishes_project_vs_user_scope()` in `ecommerce_team_config/claude_md.py`, which requires `CLAUDE.md` to mention user level, mention project level, state that user-level config is not version-controlled, and give a concrete user-scope example. The config's own scope table satisfies it — **project-level:** `./CLAUDE.md`, `.claude/standards/`, `.claude/rules/`, described as "Lives in git. Shared with the whole team," e.g. the `/review` command every teammate gets. **User-level:** `~/.claude/CLAUDE.md`, `~/.claude/commands/`, described as "**Not shared via version control**," with the worked example of "a personal `/morning` summary command." The distinction is a collaboration boundary: project scope is a promise to teammates, user scope is a preference that must never silently change a colleague's behavior.

### System 4 — Orchestration

**11. Push work down.** From `system-4-shift-monitor/run-console-output.txt`, section 4: the warm tier holds **40 defects total**; the shift query returned **17**; **23 were withheld from the model entirely**. The query is `WarmStore.defects_since()` in `shift_monitor/warm.py` — `SELECT * FROM defects WHERE ts > ? ORDER BY ts DESC LIMIT ?` — and `EXPLAIN QUERY PLAN` confirms it is indexed rather than scanned:

```
SEARCH defects USING INDEX idx_defects_ts (ts>?)
```

The model never sees full history because the filter runs in SQLite, before assembly. This is a correctness argument as much as a cost one: token spend would grow without bound as the plant accumulates defects, but more importantly a model handed 40 rows and asked to "consider only recent ones" is being asked to do reliably what an index does deterministically. `SEARCH … USING INDEX` rather than `SCAN` is the artifact that proves the work moved down a layer.

**12. Crash recovery.** `shift_monitor/recovery.py::decide()` returns `fresh` if the manifest has no steps, `fresh` if the manifest is complete, and otherwise compares the last step's timestamp against `STALE_RESUME_THRESHOLD_MINUTES = 30`, resuming only within the window. My run exercised all four branches (section 6 of the console log):

```
last step  5m old -> resume
last step 30m old -> resume     ← inclusive at the boundary
last step 31m old -> fresh
after complete step: complete=True -> decide=fresh
```

The threshold's rationale is documented in `recovery.py`: a shift is 8 hours and the working set rolls over with it, so 30 minutes is about one-sixteenth of a shift — still the same operational reality. A fresh start with an injected summary beats resuming when the partial state has gone stale, because resumption re-asserts old premises as current: the model picks up mid-reasoning about a line whose readings have since moved, and it has no way to notice. A fresh run with a one-paragraph summary of prior findings is both cheaper and *more* accurate, because every fact it reasons over was read after the gap.

**13. Small state.** My `system-4-shift-monitor/hot_state.json` is **965 bytes against a 5,120-byte budget — 18.8% used, 4,155 bytes of headroom**. The budget matters precisely because this system runs once per shift forever: every field in hot state is re-sent on every future invocation, so an unbounded field is not a one-time cost but a permanent per-shift tax that compounds three times a day, indefinitely. The two structural defenses are visible in the artifact: `recent_defect_hashes` holds 17 ids and is capped at `MAX_RECENT_HASHES = 20` by a Pydantic `Field(max_length=...)`, and `HotState.write_atomic()` *raises* rather than truncating if the payload exceeds the budget. That is deliberate — a system that silently dropped alerts to fit would degrade invisibly across thousands of shifts.

---

## Part 2 — Synthesis

**14. Three layers.**

- **Model** — `Build a Claims Intake Agent…/solution/claims_intake/system_prompt.py`. It is the only place the insurance *domain* exists in prose: four claim types, three severity buckets with dollar thresholds, and the 0.6 confidence rule. Its own docstring makes the separation explicit: "The harness is generic; the prompt teaches the model how to use the tools and when to escalate." Change this file and behavior changes with zero code change.
- **Harness** — `claims_intake/loop.py::run()` plus `Configure Claude Code…/solution/.claude/skills/deploy-check/SKILL.md`. The loop is the tool-execution harness: it branches on `stop_reason`, executes tool blocks, appends results, enforces a `Budget`. The skill is the same layer in Claude Code's own configuration surface — `allowed-tools` is a harness-level allowlist that constrains what the model may reach for at all.
- **Orchestration** — `Build a Multi-Shift…/solution/shift_monitor/pipeline.py::run_shift()`, with `manifest.py` and `recovery.py`. This is the layer above any single conversation: it decides what a session even *sees* (the 17-of-40 SQL slice), persists state across sessions (`hot_state.json`, 965 bytes), and decides whether a *new* session should resume or start fresh. `decide()` is orchestration in its purest form — it is a control decision made when no model is running at all.

**15. Deterministic vs prompt.** **Deterministic:** `HotState.write_atomic()` in `shift_monitor/state.py` raises `ValueError` when the payload exceeds 5,120 bytes, and writes via a temp file + `os.fsync` + `os.replace`. My hot state came in at 965 bytes — but the guarantee is that if it ever hit 5,121, the run fails loudly instead of persisting a state that would quietly bloat every future prompt. **Prompt-based:** the 0.6 confidence threshold that separates `route_to_adjuster` from `escalate_to_human` exists only in `system_prompt.py` and the tool descriptions. Nothing in the code enforces it — `route_to_adjuster` will happily accept a claim classified at 0.3. The distinction is enforceability: a byte budget is a property of the artifact, checkable without running a model, so it belongs in code. "Is 0.55 confidence too low to route this fire claim?" is a judgment over facts that cannot be enumerated in advance, so it belongs in the prompt. My own System 1 results are the cautionary note, and I got to test it both ways. The prompt says "Choose exactly one terminal action"; on 4 of 8 claims the model simply did not — the failure mode prompt-based guidance cannot rule out. Moving that one requirement from prompt to code took it from 4/8 to 8/8 (Q20). The lesson is not "prompts are bad" — the 0.6 confidence judgment still belongs in the prompt and still worked — it is that *"a decision must be made"* is a checkable property and belongs in code, while *"which decision"* is not and does not.

**16. Context, two faces.** System 2 manages context *within* one conversation: 48 turns, **38,708 → 16,905 tokens (56.33%)**, achieved by compressing resolved segments (`resolved_refund` 363 tokens, `resolved_subscription` 567) while keeping the active thread verbatim at **15,789 tokens**. System 4 manages context *across* sessions: each shift is a fresh session that begins from a **965-byte** `hot_state.json` plus a **17-of-40** SQL slice, with the other 23 defects left in SQLite. Same principle — *carry forward conclusions, leave the raw material where it lives* — at two very different scales, and the scale difference is the interesting part. System 2's compressed context is still 16,905 tokens because a support conversation must stay coherent turn to turn. System 4 gets away with 965 bytes because a shift boundary is a legitimate amnesia point: the mechanism differs (LLM summarization vs. a Pydantic-capped struct on disk) because System 2 must preserve *conversational* continuity while System 4 need only preserve *operational* continuity. System 4 can afford to be brutal; System 2 cannot.

**17. Reliability you can't see in one run.** `test_hotstate_atomic_write` (System 4) guarantees that `write_atomic()` never leaves a partially written `hot_state.json` — it writes to a temp file, fsyncs, then `os.replace`s. My successful run produced a valid 965-byte file, and would have looked identical under a naive `open(path, "w")`. The behavior only differs when the process dies *between* the truncate and the write, which no successful run can exhibit. This matters before shipping because the failure is both rare and maximally destructive: a shift monitor that crashes mid-write leaves corrupt state, and the *next* shift then fails to start — one transient crash becomes a permanent outage. The same argument covers `test_merge_findings_appends_without_rewriting_existing`, which pins that merging fork findings never rewrites existing bytes. My run showed the main scratchpad going from 1 to 3 entries; only the test proves the first entry's bytes were untouched rather than coincidentally re-serialized identically.

**18. Blast radius.** Take System 4. If it misbehaves it writes a wrong `current_shift_summary` and wrong `threshold_statuses` into `hot_state.json` — and because every subsequent shift starts from that file, a single bad shift **poisons every later shift**, not just its own. My artifact shows the concrete danger: `threshold_statuses` currently reads `defect_rate_per_shift: ALARM` and `lot_defect_concentration: ALARM`, and those propagate forward untouched unless a later run overwrites them. The containment is real but partial: the model has *no tools at all* here — `pipeline.py` makes exactly one `client.complete()` call and the code, not the model, does every write, so it can corrupt state but cannot touch the warm tier, the cold summaries, or anything outside `data/`. The kill switches are, in order: `hot_state.json` is a 965-byte plain-text file that a human can read and hand-correct in under a minute; the warm tier is append-only and authoritative, so hot state can be rebuilt from SQLite; and `Manifest` + `decide()` bound how far a bad partial run propagates, since anything older than 30 minutes forces a fresh start rather than resuming from poisoned context. Forked investigations are contained by construction — my run verified the base `hot_state.json` sha256 (`110086f286fa379d…`) was byte-identical before and after forking two hypotheses.

---

## Part 3 — Honest assessment

**19. What broke.** Three things, in increasing order of interest.

*(a) Environment — fixed.* System 1's first run died immediately with `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`. Cause: `pyproject.toml` pins `anthropic==0.39.0` but leaves `httpx` unpinned, so it resolved to `httpx 0.28.1`, which removed the `proxies` argument that `anthropic` 0.39.0 still passes. Fixed with `uv pip install "httpx<0.28"` (resolved to 0.27.2) — an environment fix, not a code change. The 29 tests passed both before and after, because they use fakes and never construct a real client.

*(b) Test-count discrepancy — explained.* System 2 initially reported **28 passed, 2 skipped** against an expected 30. `pytest -rs` gave the reason: `no run artifacts available — run python -m retail_context.run --build first`. Both skips are in `test_antipatterns.py` and assert over the assembled context. After the run they execute and the suite reports **30 passed**, which is what `pytest-output.txt` shows. Worth noting as a harness design point: those two tests silently *skip* rather than fail when their input is missing, so a careless reader sees green and misses that two checks never ran.

*(c) The interesting one — root-caused, then fixed.* The unmodified System 1 does not get all 8 claims to a terminal tool. Haiku left 4 of 8 `incomplete` on two consecutive runs; Sonnet left **5 of 8**, so it is not a model-capability ceiling. I instrumented `claim_01_kitchen_fire` and found the mechanism: the model calls `lookup_policy` and four `record_claim_fact`s, then asks its clarifying question **as plain text** — "What is your estimated cost of repair or replacement…?" — instead of calling the `request_clarification` tool. That text emission is an `end_turn`, `loop.py` correctly returns, and `session.outcome` reports `incomplete` because `terminal_called` is False. The loop behaved exactly as specified; the *prompt contract* is what the model broke. Claims 01, 06, and 07 failed on all three baseline runs; 04, 05, and 08 succeeded on all three. The fix and its measured result are Q20 — and the diagnosis is what made the fix a two-line branch rather than a guess.

**20. What you'd change — and what changing it proved.** I made System 1's terminal step enforced rather than requested, and measured it. The change (`system-1-claims-intake/terminal-nudge.patch`, 110 lines) adds an optional `termination_check` callback to `loop.py::run()`: on `end_turn`, the loop asks the caller whether the task actually finished, and if not, appends the returned correction and continues instead of returning. The claims-specific definition of "finished" stays in `run.py::_terminal_check()` — `session.terminal_called` — so `loop.py` remains domain-agnostic and never inspects assistant text or tool names. A `DEFAULT_MAX_TERMINAL_NUDGES = 2` allowance bounds the repair path; the `Budget` remains the only bound on the conversation itself. All four anti-pattern tests still pass, and so do all 29.

The result (`summary-nudge-20260725_182216.md`) is unambiguous:

| | Baseline `20260725_180221` | Nudged `20260725_182216` |
|---|---|---|
| Terminated | **4 / 8** | **8 / 8** |
| Routed / escalated | 4 / 0 | **7 / 1** |
| Matched expected outcome | 4 / 8 | **8 / 8** |
| Cost | $0.1337 | $0.2006 |

Five claims needed exactly one nudge, three needed none, none needed a second. `claim_01_kitchen_fire`'s trace shows the mechanism precisely: `tool_use` → `end_turn` at turn 2 (identical to the baseline failure) → **nudge** → `request_clarification` → `classify_claim` + `assess_severity` → `route_to_adjuster` → `end_turn` at turn 6. `claim_06_low_confidence_escalation` — which never once escalated across three baseline runs — produced a fully structured escalation with `reason: "unresolved_ambiguity"` and both candidate types named.

The economics invert. Baseline: the four `incomplete` claims cost **$0.0461 of $0.1337 — 34.5% of spend for zero output**, no routing, no escalation, no queue entry (`claim_03_water_damage` alone burned 5 turns and $0.0202 before ending in prose). Nudged: 50% more total spend, and *all* of it produced a decision. Paying $0.067 more to convert a third of the run from waste into 4 additional correct outcomes is not a close call.

The general principle is the one System 4 already follows and System 1 did not: if a property must hold for the system to be correct, enforce it where it can be checked, and reserve the prompt for judgment that genuinely cannot be enumerated. `HotState.write_atomic()` raises when the byte budget is blown rather than truncating; `run()` should be — and now is — equally unwilling to accept a claim that never terminated. Note what the fix does *not* do: it never tells the model *which* terminal tool to pick. Whether `claim_06` routes or escalates is still a judgment call left to the model, and it made the right one. That is the line — enforce that a decision is made, let the model decide what it is.

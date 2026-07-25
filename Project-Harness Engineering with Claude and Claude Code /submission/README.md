# Capstone Submission — Harness Engineering with Claude and Claude Code

**Steve Wang — 2026-07-25**

All four systems were built in isolated `uv` virtualenvs, tested, and run on
macOS (Darwin 25.5.0, arm64) / Python 3.12.3.

- **Reflection brief:** [`reflection-brief.md`](reflection-brief.md)
- **Evidence:** one folder per system, below.

---

## Test results — all four suites

| System | Expected | Result | Log |
|---|---|---|---|
| 1 — Claims Intake Agent | 29 | **29 passed** | [`system-1-claims-intake/pytest-output.txt`](system-1-claims-intake/pytest-output.txt) |
| 2 — Retail Context Strategy | 30 | **30 passed** | [`system-2-retail-context/pytest-output.txt`](system-2-retail-context/pytest-output.txt) |
| 3 — Claude Code Config | 35 | **35 passed** | [`system-3-claude-code-config/pytest-output.txt`](system-3-claude-code-config/pytest-output.txt) |
| 4 — Multi-Shift Orchestration | 33 | **33 passed** | [`system-4-shift-monitor/pytest-output.txt`](system-4-shift-monitor/pytest-output.txt) |

Each log carries a header naming its system, source path, command, timestamp,
and host so it is identifiable on its own.

---

## System 1 — Insurance Claims Intake Agent

`Build a Claims Intake Agent with a stop_reason-Driven Loop/exercises/03-dynamic-decomposition/solution`
Run: `python -m claims_intake.run --all`

Two variants are submitted: the **unmodified baseline**, and a **fixed re-run**
with a 110-line harness patch. The contrast is the point — see brief Q19(c) and Q20.

| File | What it shows |
|---|---|
| `pytest-output.txt` | **29 passed** (with the patch applied; also 29/29 unmodified) |
| `summary-nudge-20260725_182216.md` | **Fixed run: 8/8 terminated, 7 routed + 1 escalated** |
| `traces-nudge-20260725_182216/*.jsonl` | Turn-by-turn `stop_reason` + `terminal_nudge` events |
| `queues-nudge-20260725_182216/*.jsonl` | Routed claims by queue, plus `escalations.jsonl` |
| `terminal-nudge.patch` | The exact diff to `loop.py` + `run.py` |
| `summary-haiku-20260725_180221.md` | Baseline Haiku: 4/8 terminated ($0.1338) |
| `summary-sonnet-20260725_180619.md` | Baseline Sonnet: 3/8 terminated ($0.4180) |
| `traces-haiku-20260725_180221/*.jsonl` | Baseline traces for all 8 claims |
| `queues-haiku-20260725_180221/*.jsonl` | Baseline routed claims |
| `runs-index.txt` | Run directory listing |

**Loop control evidence** — `traces-haiku-20260725_180221/claim_05_auto_collision.jsonl`
shows the loop continuing on `tool_use` and terminating on `end_turn`:

```
turn 1  tool_use   lookup_policy, record_claim_fact ×6
turn 2  tool_use   classify_claim
turn 3  tool_use   assess_severity
turn 4  tool_use   route_to_adjuster
turn 5  end_turn   ← loop returns
```

**End-to-end termination** — every claim in `summary-nudge-20260725_182216.md`
reaches a terminal action, and every outcome matches its fixture's expectation:
7 routed (`claim_01`–`05`, `07`, `08`) + 1 escalated (`claim_06`, the escalation
fixture). The structured escalation record is in
`queues-nudge-20260725_182216/escalations.jsonl`.

<details>
<summary><b>Why the patch exists</b> (baseline behavior and the fix)</summary>

The unmodified reference left **4 of 8** claims `incomplete` on Haiku and
**5 of 8** on Sonnet, reproducibly — so not a model-capability ceiling. Cause:
the model asks its clarifying question in plain text rather than calling
`request_clarification`; that is an `end_turn`, the loop correctly returns, and
no terminal tool ever fires.

`terminal-nudge.patch` adds an optional `termination_check` callback to
`loop.py::run()`. On `end_turn` the loop asks the caller whether the task really
finished; if not, it appends the correction and continues. The claims-specific
definition of "finished" (`session.terminal_called`) stays in `run.py`, so
`loop.py` never inspects assistant text or tool names and remains generic. A
`DEFAULT_MAX_TERMINAL_NUDGES = 2` allowance bounds the repair path; `Budget`
still bounds the conversation. All 4 anti-pattern tests and all 29 tests pass.

`claim_01_kitchen_fire`, which failed on every baseline run:

```
turn 1  tool_use   lookup_policy, record_claim_fact ×4
turn 2  end_turn                              ← identical to the baseline failure
turn 2  NUDGE      end_turn without a terminal action
turn 3  tool_use   request_clarification
turn 4  tool_use   classify_claim, assess_severity
turn 5  tool_use   route_to_adjuster
turn 6  end_turn                              ← loop returns, terminal_called=True
```

5 claims needed exactly one nudge, 3 needed none, none needed a second.
Cost went $0.1337 → $0.2006, but baseline spent 34.5% of its budget on claims
that produced no decision at all.

</details>

---

## System 2 — Retail Support Context Strategy

`Engineer a Long-Conversation Context Strategy for a Retail Support Copilot/04-assemble-and-locate/solution`
Run: `python -m retail_context.run --all` → run id **`20260725-181019`**

| File | What it shows |
|---|---|
| `pytest-output.txt` | 30 passed |
| `budget.json` | 38,708 → 16,905 tokens = **56.33% reduction** (≥50% required) |
| `eval.jsonl` | **6/6** evaluation questions passed (≥5/6 required) |
| `eval_control.jsonl` | Case-facts-stripped control: **Q6 regresses** (≥1 required) |
| `context.md` | The assembled context (4 sections) |
| `case_facts_call.json` | The fact-extraction call |

Per-section token split from `budget.json`: `active` 15,789 · `resolved_subscription` 567 ·
`resolved_refund` 363 · `case_facts` 204.

---

## System 3 — E-Commerce Team Claude Code Config

`Configure Claude Code for a Multi-Surface Monorepo Team/04-plan-mode-and-explore-decision-doc/solution`
Run: `python -m ecommerce_team_config .`

| File | What it shows |
|---|---|
| `pytest-output.txt` | 35 passed |
| `validator-output.txt` | **`OK`, exit code 0** |
| `claude-config-structure.txt` | `.claude/` tree, `@import` lines, all frontmatter blocks |
| `CLAUDE.md` | Hierarchy entry point with `@.claude/standards/*` imports |
| `claude-config/.claude/` | Full config: 3 rules, 4 standards, 1 command, 1 skill |

Rubric-relevant excerpts are collected in `claude-config-structure.txt`:
`@import` lines in `CLAUDE.md`; glob `paths:` frontmatter in all three
`.claude/rules/*.md`; the project-scoped `/review` command; and the
`deploy-check` skill's `context: fork` plus its read-only `allowed-tools`.

---

## System 4 — Multi-Shift Quality Monitoring

`Build a Multi-Shift Quality Monitoring System with Claude Orchestration/04-fork-scratchpad/solution`
Run offline against a recorded response — **no API spend**.

| File | What it shows |
|---|---|
| `pytest-output.txt` | 33 passed |
| `run-console-output.txt` | Full 6-part run: seed, shift, budget, SQL slice, fork, recovery |
| `hot_state.json` | **965 bytes** against a 5,120-byte budget (18.8% used) |
| `shift_scratchpad.jsonl` | Main stream, 3 entries after fork merge |
| `manifest_C.jsonl` | Crash-recovery manifest, one JSON line per step |
| `forks/H1-lot-2026-0430-B/`, `forks/H2-vp4-vent-cycle/` | Two isolated investigations |

**Push work down:** warm tier holds **40 defects**; the shift used a **17-defect**
SQL slice; **23 were never sent to the model**. Plan confirms the index is used:
`SEARCH defects USING INDEX idx_defects_ts (ts>?)`.

**Fork isolation:** base `hot_state.json` sha256 `110086f286fa379d…` byte-identical
before and after forking; neither fork's scratchpad contains the other's findings;
merge took the main scratchpad from 1 → 3 entries by pure append.

**Crash recovery:** `STALE_RESUME_THRESHOLD_MINUTES = 30`, inclusive at the
boundary — 30m → `resume`, 31m → `fresh`, completed manifest → `fresh`.

---

## Reproducing

Per system, from its `solution/` directory:

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -v
```

System 1's fixed run additionally requires `terminal-nudge.patch` applied to
`claims_intake/loop.py` and `claims_intake/run.py`; the baseline runs are from
the unmodified tree.

Two environment notes, both detailed in the brief's Q19:

1. **System 1** needs `uv pip install "httpx<0.28"`. Its `pyproject.toml` pins
   `anthropic==0.39.0` but leaves `httpx` unpinned; `httpx` 0.28 removed the
   `proxies` argument that `anthropic` 0.39.0 still passes, so any live API call
   dies with `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`.
2. **System 2** reports 28 passed + 2 skipped until `python -m retail_context.run`
   has produced run artifacts; the two skipped tests assert over the assembled
   context. After a run it reports 30 passed.

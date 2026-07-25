# Primer 0 — Harness Engineering: The Big Picture

> **How to use these primers.** Each one moves in three passes: **concepts** (what
> problem is being solved and why this shape), **architecture** (the module map,
> enough to orient), then **code detail** (line-level walkthrough of the parts that
> carry the ideas). Read pass 1 to review, pass 2 to re-orient, pass 3 when you need
> to actually change something. Every primer ends with gotchas and self-check
> questions.

| # | Primer | System | Core idea |
|---|---|---|---|
| 0 | This file | — | The three layers; what unifies the four systems |
| 1 | [Agentic loops](01-agentic-loops.md) | Claims Intake | `stop_reason` drives control flow |
| 2 | [Context strategy](02-context-strategy.md) | Retail Copilot | Position-aware compression |
| 3 | [Claude Code config](03-claude-code-config.md) | E-Commerce Monorepo | Configuration as a harness |
| 4 | [Layer 3 orchestration](04-layer-3-orchestration.md) | Shift Monitor | State across sessions |

---

## 1. The central question

Every system in this course answers one question differently:

> **Where does the decision live — in the model, or in the code?**

That question has a wrong answer in both directions. Push too much into code and you
have a rigid pipeline that can't handle the case you didn't anticipate. Push too much
into the model and you have a system that mostly works, fails unpredictably, and
can't be debugged.

"Harness engineering" is the discipline of drawing that line deliberately, and then
*enforcing* it structurally so it doesn't drift.

---

## 2. The three layers

The course's organizing frame. Every piece of an LLM system sits in one of three
layers, and confusion about which layer you're working in is the source of most bad
architecture.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — ORCHESTRATION                                    │
│  Above any single conversation.                             │
│  • What does a session even see?                            │
│  • What persists between sessions?                          │
│  • Should this session resume or start fresh?               │
│  Runs when no model is running.                             │
│  → shift_monitor/pipeline.py, recovery.py, manifest.py      │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2 — HARNESS                                          │
│  Around one conversation.                                   │
│  • The loop that executes tools and feeds results back      │
│  • What tools exist at all (the action space)               │
│  • Budgets, allowlists, tracing                             │
│  → claims_intake/loop.py, .claude/skills/*/SKILL.md         │
├─────────────────────────────────────────────────────────────┤
│  LAYER 1 — MODEL                                            │
│  Inside one turn.                                           │
│  • The system prompt: domain knowledge, judgment rules      │
│  • Tool descriptions: when to reach for what                │
│  Changes behavior with zero code change.                    │
│  → claims_intake/system_prompt.py, tool descriptions        │
└─────────────────────────────────────────────────────────────┘
```

**The diagnostic question for each layer:**

- Layer 1 — *"Could I change this by editing prose?"*
- Layer 2 — *"Does this constrain what the model can do within a conversation?"*
- Layer 3 — *"Does this run when no conversation is happening?"*

A concrete walk down the stack, from System 1:

| Layer | Artifact | What it decides |
|---|---|---|
| 1 | `system_prompt.py` | Four claim types; severity thresholds; "escalate below 0.6 confidence" |
| 2 | `loop.py::run()` | Continue on `tool_use`, return on `end_turn`, raise otherwise |
| 2 | `tools.py::TOOL_SCHEMAS` | The seven things the model is *able* to do |
| 3 | `run.py::main()` | Which fixtures run, where artifacts land, the per-claim budget |

---

## 3. The recurring pattern: enforce what's checkable

The single most transferable idea across all four systems:

> **If a property must hold for the system to be correct, and it can be checked
> mechanically, enforce it in code. Reserve the prompt for judgment that genuinely
> cannot be enumerated.**

Watch it recur:

| System | Enforced in code | Left to the model |
|---|---|---|
| 1 — Claims | A terminal decision *must* be made | *Which* decision (route vs. escalate) |
| 2 — Context | Active segment preserved byte-exact | What to say in a summary |
| 3 — Config | `allowed-tools` allowlist | How to conduct a review |
| 4 — Shift | Hot state ≤ 5,120 bytes; atomic write | What the shift summary says |

The failure mode when you get this wrong is instructive, and this repo has a
*measured* example. System 1's system prompt says "Choose exactly one terminal
action." Across three baseline runs on two models, the model simply didn't, on
roughly half the claims — it asked its clarifying question in prose instead of via
the tool, which reads as `end_turn`, and the loop correctly returned with no decision
made. Moving that one requirement from prompt to code took the run from 4/8 to 8/8.

The lesson is *not* "prompts are unreliable." The 0.6-confidence judgment stayed in
the prompt and worked fine. The lesson is that **"a decision must be made" is a
checkable property and belongs in code; "which decision" is not and does not.**

---

## 4. The four systems at a glance

### System 1 — Claims Intake Agent (Layer 2 focus)

An agentic loop that processes insurance claims. The model calls tools to look up
policies, record facts, classify, assess severity, and finally either routes to an
adjuster queue or escalates to a human.

- **Teaches:** loop control via `stop_reason`; tool schemas as the action space;
  dynamic decomposition; AST audits as anti-pattern enforcement.
- **Signature artifact:** a JSONL trace showing `tool_use → tool_use → … → end_turn`.

### System 2 — Retail Context Strategy (Layer 2 focus)

Compresses a 48-turn, three-issue support conversation to under half its tokens while
still answering evaluation questions correctly.

- **Teaches:** deterministic pruning vs. LLM summarization; the scratchpad/case-facts
  pattern; position-aware layout around the lost-in-the-middle effect; control
  variants as evidence.
- **Signature artifact:** `budget.json` — 38,708 → 16,905 tokens, 56.33% reduction.

### System 3 — Claude Code Config (Layer 2, configuration surface)

A `CLAUDE.md` hierarchy, path-scoped rules, a slash command, and a forked skill —
with a Python validator that mechanically checks the whole thing.

- **Teaches:** configuration *is* harness engineering; scope hierarchy;
  glob-scoped rules; read-only allowlists; forked context.
- **Signature artifact:** `ecommerce-team-config .` → `OK`, exit 0.

### System 4 — Multi-Shift Quality Monitor (Layer 3 focus)

Runs once per 8-hour shift, forever. Fresh session each time. Tiered storage keeps
per-session state tiny; a manifest makes crashes survivable; forking lets
investigators chase competing hypotheses in isolation.

- **Teaches:** hot/warm/cold tiers; pushing work down to SQL; crash-recovery
  manifests; resume-vs-fresh; state forking.
- **Signature artifact:** a 965-byte `hot_state.json` and a 17-of-40 SQL slice.

---

## 5. Cross-cutting themes

### 5.1 Push work down

Do the work at the cheapest, most deterministic layer that can do it correctly.

- System 2 prunes 57 tool fields to 5 **in Python**, no LLM call.
- System 4 filters 40 defects to 17 **in SQLite**, using an index, before assembly.

Both are cost arguments *and* correctness arguments. A model asked to "consider only
recent defects" will mostly comply; `WHERE ts > ?` always does. `EXPLAIN QUERY PLAN`
showing `SEARCH … USING INDEX` rather than `SCAN` is the artifact that proves the work
actually moved down.

### 5.2 Structured errors beat strings

System 1's tools return `{"is_error": true, "error_category": …, "is_retryable": …,
"message": …}`. `is_retryable` is the field a bare string can't give you: the model
can distinguish "never going to work, escalate" from "transient, try again" without
parsing prose.

### 5.3 Tests catch what runs cannot

A successful run and a correct system are different claims. Atomic writes only differ
from naive writes when the process dies mid-write. Append-only merges only differ from
rewrites when you check the bytes. These are invisible to any single green run — which
is precisely why they need tests.

### 5.4 AST audits enforce architecture

Systems 1 and 2 both ship tests that parse source and fail on forbidden constructs:
no `"done" in text` in the loop, no `for _ in range(10)` cap, no `anthropic` import in
the pruner. Regular tests check behavior on the paths they exercise; an AST audit
checks a property across *all* paths, including ones no test covers.

### 5.5 Fail loudly, never silently degrade

- `HotState.write_atomic()` **raises** when over budget rather than truncating.
- `case_facts.extract()` **raises** listing missing fields rather than null-filling.
- `loop.py` **raises** `UnexpectedStopReason` rather than guessing.

A system that quietly drops alerts to fit a budget degrades invisibly across thousands
of runs. One that crashes gets fixed.

---

## 6. Suggested review order

**Refreshing everything:** 0 → 1 → 2 → 3 → 4. Systems 1 and 2 build intuition for a
single conversation; 3 generalizes to configuration; 4 lifts to across-session.

**Targeted:**

| You want to remember… | Go to |
|---|---|
| How the agentic loop terminates | [Primer 1 §3](01-agentic-loops.md) — `loop.py` in detail |
| Why tool descriptions matter | [Primer 1 §4](01-agentic-loops.md) — the action space |
| The four anti-patterns and the AST audit | [Primer 1 §1.5, §6](01-agentic-loops.md) |
| Where to put facts in context | [Primer 2 §1.3](02-context-strategy.md) — lost in the middle |
| The assembly layout contract | [Primer 2 §8](02-context-strategy.md) — `assemble.py` |
| Token counting methodology | [Primer 2 §4](02-context-strategy.md) — `tokens.py` |
| Path-scoped rules vs directory CLAUDE.md | [Primer 3 §1.4, §4](03-claude-code-config.md) |
| What `context: fork` buys | [Primer 3 §1.5, §5](03-claude-code-config.md) |
| Read-only allowlists | [Primer 3 §7](03-claude-code-config.md) — `tool_allowlist.py` |
| Mechanically validating prose | [Primer 3 §8](03-claude-code-config.md) |
| Hot/warm/cold tiering | [Primer 4 §1.2](04-layer-3-orchestration.md) |
| Atomic writes and the byte budget | [Primer 4 §3](04-layer-3-orchestration.md) — `state.py` |
| Pushing work down to SQL | [Primer 4 §1.3, §4](04-layer-3-orchestration.md) |
| Crash recovery and staleness | [Primer 4 §6](04-layer-3-orchestration.md) |

---

## 7. Self-check

1. Name the three layers and give the diagnostic question for each.
2. A teammate wants to add `if claim_type == "auto": queue = "auto_queue"` to the
   harness. Which layer does that belong to, and what's wrong with putting it in
   Python?
3. Give one property from each of the four systems that is enforced in code, and one
   that is left to the model.
4. Why does an AST audit catch things a unit test cannot?
5. Both System 2 and System 4 "manage context." What's the difference in mechanism,
   and why does the difference exist?

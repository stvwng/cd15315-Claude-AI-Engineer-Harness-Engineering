# Primers — Harness Engineering with Claude and Claude Code

Review notes for the four systems in this repo. Written to be re-read: each primer
moves from **concepts** → **architecture** → **line-level code detail**, then closes
with gotchas and self-check questions.

**Start here → [00-overview.md](00-overview.md)** for the three-layer frame and the
themes that recur across all four systems.

| Primer | System | Core idea | Code |
|---|---|---|---|
| [00 — Overview](00-overview.md) | all four | The three layers; enforce what's checkable | — |
| [01 — Agentic loops](01-agentic-loops.md) | Claims Intake | `stop_reason` drives control flow | `claims_intake/` |
| [02 — Context strategy](02-context-strategy.md) | Retail Copilot | Position-aware compression | `retail_context/` |
| [03 — Claude Code config](03-claude-code-config.md) | E-Commerce Monorepo | Configuration as a harness | `.claude/` + validator |
| [04 — Layer 3 orchestration](04-layer-3-orchestration.md) | Shift Monitor | State across sessions | `shift_monitor/` |

## Reading paths

- **Full refresh** — 00 → 01 → 02 → 03 → 04. Systems 1–2 build intuition for a single
  conversation, 3 generalizes to configuration, 4 lifts to across-session.
- **Targeted lookup** — see the jump table in [00-overview.md §6](00-overview.md).
- **Before changing code** — read that primer's §gotchas first; most of them are
  failures that were actually hit and diagnosed, not hypotheticals.

## What these cover

Every claim is grounded in the reference implementations under each project's final
`solution/`, and the numbers come from real runs captured in
`Project-Harness Engineering with Claude and Claude Code /submission/`:

- 29 + 30 + 35 + 33 passing tests
- 38,708 → 16,905 tokens (56.33% reduction), 6/6 evals, control regression on Q6
- Validator `OK`, exit 0
- 965-byte hot state, 17-of-40 SQL slice, verified fork isolation
- The System 1 termination gap (4/8 → 8/8) and its fix

Where a primer quotes code, it quotes the **solution**, not the starter exercises.

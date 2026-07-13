# Plan mode vs. direct execution — team decision guide

Choosing between Claude Code's **plan mode** (investigate and propose before changing anything) and **direct execution** (change code immediately) is the single biggest leverage point in how the team uses the harness day-to-day. The wrong mode at either extreme costs us: plan mode for trivial fixes is friction; direct execution for architectural changes burns context and produces rework.

<!--
TODO: Add a blockquote citation for the Knight-Webb "SWE Is Becoming Plan and Review"
      anchor talk that frames this decision.

      IMPORTANT: source the citation from the Module 8 curriculum doc's anchor-talks
      table. Do NOT cite the Architect's Playbook — the Playbook contains zero
      plan-mode content and citing it would be a fabrication. The Knight-Webb talk
      lives in the curriculum doc, not the Playbook.
-->

> **Framing.** This guide operationalizes Knight-Webb, *"SWE Is Becoming Plan and Review"* — the Module 8 curriculum anchor-talk. Its thesis: as agents take over the keystrokes, the engineer's leverage shifts to **planning before** and **reviewing after**. Investing in a good plan up front is how you prevent costly rework downstream, and the mode you pick per task is the practical expression of that thesis.

This doc walks four concrete decisions against our codebase: one plan-mode example, one direct-execution example, one Explore-subagent example, and one combined-workflow example.

---

## 1. Plan-mode example

<!--
TODO: Write a plan-mode worked example against this codebase. Requirements:

  - Touch AT LEAST THREE real files in src/. A natural candidate is extracting a
    shared `useCart(userId)` hook into src/hooks/ from three components that
    currently duplicate the pattern:
      - src/components/Cart/Cart.tsx
      - src/components/Checkout/Checkout.tsx
      - src/components/MiniCart/MiniCart.tsx
    (All three exist in this repo — confirm before referencing.)

  - State the reasoning that maps to Task 3.4: large-scale changes, multiple
    valid approaches, architectural decisions, multi-file modifications.

  - EXPLICITLY cite "prevent costly rework" (or equivalent phrasing) as the value
    of planning before committing. This is the Knight-Webb principle.

  - File-path rule: if you mention a file in backticks, it must actually exist
    in the repo. For hypothetical/future files (e.g. the extraction target that
    doesn't exist yet), use PROSE form (no backticks) instead. Otherwise the
    validator will flag a dangling reference.
-->

**Task:** three components duplicate the same cart-loading logic — `src/components/Cart/Cart.tsx`, `src/components/Checkout/Checkout.tsx`, and `src/components/MiniCart/MiniCart.tsx` each fetch and memoize cart state inline. We want to extract a shared useCart(userId) hook into the src/hooks directory (a new file that does not exist yet, so it appears here in prose, not backticks) and rewire all three call sites to consume it.

**Why plan mode:** this is a **multi-file modification** with **more than one valid approach** — the hook could expose raw state plus setters, or a reducer-style action API, or wrap the existing `CartContext`. That is an **architectural decision** (the hook's surface becomes a contract every future consumer depends on) at a **large-enough scale** that committing to the wrong shape is expensive. Plan mode lets Claude investigate all three current implementations, surface the differences, and propose one hook signature for the team to approve *before* any file is edited.

**The payoff:** approving the interface on paper is how we **prevent costly rework** — if we let direct execution pick a shape and edit all three components, and the shape is wrong, we redo three files instead of one paragraph. Plan first, edit once.

---

## 2. Direct-execution example

<!--
TODO: Write a direct-execution worked example. Requirements:

  - Target a single, well-scoped change in ONE function. A natural candidate is
    adding a `min: 0` validation to the quantity field in the orders schema or
    handler:
      - src/api/orders/handler.ts (or src/api/_schemas/orders.ts)
    Confirm the file exists before referencing it.

  - State the reasoning that maps to Task 3.4: simple, well-scoped changes.

  - Convey the bar for "direct execution": you (the author) already know what
    the diff looks like before invoking Claude. If you can describe the change
    in one sentence and predict the patch, skip planning.
-->

**Task:** the quantity field in `src/api/_schemas/orders.ts` accepts negative numbers. Add a `min: 0` constraint to the `zod` schema so the boundary rejects them.

**Why direct execution:** this is a **simple, well-scoped change to one function** — a single line in one schema. There is no design question and no second valid approach worth debating.

**The bar:** you already know exactly what the diff looks like before you invoke Claude — `quantity: z.number()` becomes `quantity: z.number().min(0)`, plus a one-line test. When you can **describe the change in one sentence and predict the patch**, planning adds latency without adding safety. Execute directly and review the diff.

---

## 3. Explore-subagent example

<!--
TODO: Write an Explore-subagent worked example. Requirements:

  - A real discovery task in this codebase. A natural candidate: "find every
    place we call `processRefund`" — the answer touches src/api/orders/refund.ts,
    src/api/billing/issue.ts, and src/services/payment.ts. Confirm the files
    and the call sites exist before referencing them.

  - State the reasoning that maps to Task 3.4: isolating verbose discovery output
    and returning summaries to preserve main conversation context.

  - REFERENCE THE SCRATCHPAD PATTERN (Architect's Playbook). The Explore sub-agent
    should write its working notes to a scratchpad file (e.g. tmp/refund-callsites.md)
    so the inventory survives the main session's context window. Name it
    explicitly — "scratchpad pattern" should appear in your text.
-->

**Task:** before touching the refund flow, inventory every place we call `processRefund`. The answer spans `src/services/payment.ts` (the definition), `src/api/orders/refund.ts`, and `src/api/billing/issue.ts` (the two call sites).

**Why an Explore subagent:** discovery is verbose — grepping, reading each hit, checking whether a call is direct or wrapped. That intermediate output has no lasting value. Dispatching an Explore subagent is about **isolating verbose discovery output** in a child agent and returning only a tight summary, which **preserves the main conversation context** for the actual change.

**Scratchpad pattern:** per the Architect's Playbook **scratchpad pattern**, the Explore subagent writes its working notes to a scratchpad file — e.g. `tmp/refund-callsites.md` — listing each call site with file, line, and arguments. The inventory then survives the main session's context window: even after the discovery turns are compacted away, the file persists on disk for the implementation step to read back.

---

## 4. Combined workflow — plan mode for investigation, then direct execution

<!--
TODO: Write a combined-workflow worked example. This is the most subtle of the
      four — developers often see plan mode and direct execution as binary. The
      combined workflow uses plan mode for the DISCOVERY part (where you don't
      yet know the call-site list) and direct execution for the MECHANICAL part
      (where the rename is keystrokes once the list is known).

      Requirements:

      - A real change in this codebase where investigation should precede edits.
        A natural anchor: renaming `ordersRepo.findById` → `ordersRepo.getById`
        in src/db/orders.ts to align with a team naming convention
        (get* for single-row reads, find* for multi-row). The investigation
        question is "where is findById called, and are any of them dynamic
        (constructed string lookups grep would miss)?" — plan mode handles that.
        Once the call-site list is in hand, the rename itself is mechanical:
        direct execution.

      - State the reasoning that maps to Task 3.4: "Combining plan mode for
        investigation with direct execution for implementation."

      - Show the flow as a 3-step sequence: (1) plan mode investigates and
        proposes; (2) you approve the plan; (3) direct execution applies the
        rename and runs tests.
-->

**Task:** rename `findById` → `getById` on the orders repository in `src/db/orders.ts`, aligning with the team convention that `get*` is for single-row reads and `find*` is for multi-row queries.

**Why combine the modes:** developers often treat plan mode and direct execution as binary, but the best move here **combines plan mode for investigation with direct execution for implementation**. The risky part is *discovery*, not editing: a plain grep finds `ordersRepo.findById` in `src/api/orders/refund.ts` and `src/api/billing/issue.ts`, but could miss a dynamic call built from a string (e.g. `ordersRepo[method]`). Plan mode reasons about that; the rename itself is pure keystrokes once the list is confirmed.

The flow is three steps:

1. **Plan mode investigates and proposes** — Claude enumerates every `findById` call site, explicitly checks for dynamic/constructed lookups grep would miss, and proposes the full rename set plus which test files must change.
2. **You approve the plan** — you confirm the call-site inventory is complete and the convention mapping is right, so the mechanical step operates on a trusted list.
3. **Direct execution applies the rename and runs tests** — with the list approved, Claude renames the definition and every call site in one pass and runs the suite to confirm nothing broke.

Plan mode buys certainty about scope; direct execution then moves fast because the uncertainty is already gone.

---

## Quick reference

| Situation | Mode |
|-----------|------|
| Single function, fix is obvious, you can predict the diff | Direct execution |
| Multi-file refactor, API shape is debatable | Plan mode |
| Discovery / inventory across the codebase, you'll throw away the intermediate steps | Explore subagent |
| Investigation-then-mechanical-change | Plan mode → direct execution |
| Architectural decision (which database, which queue) | Plan mode, possibly with a fork to compare options |

When in doubt: plan mode is recoverable (you can switch to execution), but direct execution on a complex change is not. Default to plan when uncertain.

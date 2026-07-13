---
description: Rules for co-located *.test.ts / *.test.tsx files across the tree
paths:
  - "**/*.test.tsx"
  - "**/*.test.ts"
---

# Test file rules

Loads when editing any co-located test file, anywhere in the tree. Because tests sit next to their source (`Cart.tsx` beside `Cart.test.tsx`), these globs deliberately cross-cut both the components tree and the API tree — so a component test also picks up `react.md`, and an API-adjacent test also picks up `api.md`. These rules layer on top.

## Structure

- One top-level `describe` per unit under test, named after the exported symbol (`describe("Cart", ...)`). Nest `describe` blocks for distinct behaviors, not for every assertion.
- Each `it`/`test` states a behavior in plain language: `it("disables checkout when the cart is empty")`, not `it("test1")`.

## Assertions

- Assert on user-visible output and return values, not internal state. For components, query through `@testing-library/react` roles/text — never reach into hook internals or component instance fields.
- API handler tests call the handler function directly with a request shape and assert on the returned `{ status, body }`. Never spin up the HTTP layer or bind a port.

## Forbidden

- No snapshot tests (`toMatchSnapshot`). They rubber-stamp regressions instead of encoding intent — write explicit assertions.
- No real timers. Replace `setTimeout`/polling with fake timers or awaited promises so tests are deterministic.
- Do not mock the database layer. Repository tests hit the real PostgreSQL test instance — a mocked DB once hid a broken migration, and that rule is not negotiable.
- No conditional assertions (`if (x) expect(...)`). A branch that might skip the check is a test that can silently pass without verifying anything.
- No shared mutable state across `it` blocks. Build fresh fixtures per test in `beforeEach` so ordering never changes the outcome.

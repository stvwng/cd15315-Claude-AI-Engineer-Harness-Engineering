---
# TODO: Write the YAML frontmatter for this command. It must include:
#
#   description:   one line, ≥10 characters, naming what the command does
#   argument-hint: short description of how to pass a target (PR ref, diff range, or file path)
#   allowed-tools: a list of READ-ORIENTED tools only — no Edit, Write, NotebookEdit, or
#                  unrestricted Bash.
#
# Granular Bash sub-command allowlisting is the canonical pattern. For example:
#   - Bash(git diff:*)
#   - Bash(git log:*)
#   - Bash(gh pr view:*)
# This lets you allow READ operations on git without unlocking the full shell. The
# command should be able to run `git diff`, `git log`, `gh pr view`, `gh pr checks`,
# etc. — but NOT `git push`, `git commit`, or arbitrary `Bash(...)`.
description: Review a PR or diff against this repo's shared conventions
argument-hint: <pr-ref | diff-range | path> — e.g. "#482", "main...HEAD", or "src/api/orders/refund.ts"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git show:*)
  - Bash(git status:*)
  - Bash(gh pr view:*)
  - Bash(gh pr diff:*)
  - Bash(gh pr checks:*)
---

# /review — team PR review

You are reviewing the diff identified by `$ARGUMENTS` against this repository's conventions. Apply the path-scoped rules in `.claude/rules/` (they auto-load based on the files touched) and the shared standards in `.claude/standards/`.

First, resolve `$ARGUMENTS` to a concrete diff: a PR ref → `gh pr diff`, a range like `main...HEAD` → `git diff`, a path → `git diff` scoped to that path. If it is empty, review the working-tree diff (`git diff` + `git diff --staged`).

## Phase 1 — Interview pattern

<!--
TODO: Write the interview-pattern subsection. The reviewer agent should ask clarifying
      questions BEFORE reporting findings whenever the author's intent is ambiguous.

      Why this matters (and why it's not obvious on first read): without an interview
      step, the reviewer commits to a confidently-wrong verdict on ambiguous changes —
      e.g. a refactor that touched no test files. The author then has to argue against
      a "no test coverage" finding when the behavior was already covered upstream. The
      interview pattern asks first.

      Name at least three concrete trigger conditions where the reviewer should
      interview rather than report. Suggested triggers:
        - dependency changes (package.json or pyproject.toml diffs)
        - public API response shape changes or DB column changes
        - refactors with no corresponding test changes
        - changes that touch multiple surfaces (API + components + DB) at once
-->

Before reporting findings, decide whether the author's intent is clear. When it is **not**, ask clarifying questions first and hold the finding until you have an answer — a confidently-wrong verdict on an ambiguous change costs more author trust than a slightly slower review.

Interview (ask, don't report) when any of these triggers fire:

- **Dependency changes** — the diff touches `package.json`, `pyproject.toml`, or a lockfile. Ask: is this a deliberate upgrade, a transitive bump, or an accidental commit? Don't flag a version change as a "risk" until you know why it happened.
- **Public contract changes** — an API response shape in `src/api/_schemas/` changed, or a DB column was added/renamed/dropped. Ask: is there a consumer or migration coordinated with this, and is the old shape still served during rollout?
- **Refactor with no test changes** — behavior-adjacent code changed but no `*.test.ts(x)` file did. Ask: is the behavior already covered by an existing/upstream test, or is coverage genuinely missing? Don't open with a "no test coverage" finding.
- **Multi-surface changes** — one diff spans API + components + DB at once. Ask which surface is the source of truth for the change so you review the others as followers, not as independent edits.

If none of the triggers fire and intent is obvious from the diff, skip the interview and proceed to Phase 2.

## Phase 2 — Review criteria

<!--
TODO: Write the explicit must-report vs. skip taxonomy. The point of explicit criteria
      (vs vague "be thorough" instructions) is that two teammates running this command
      on the same PR should reach the same verdict.

      Must report: at minimum, name categories for bugs (logic errors, missing await,
      race conditions, off-by-one), security (raw SQL with user input, missing auth,
      secrets in code, dangerouslySetInnerHTML), convention violations the path-scoped
      rules catch, breaking changes, and migration safety.

      Skip: at minimum, name categories the reviewer should NOT block on — minor
      formatting (Prettier handles it), naming bikeshed when the name is fine, personal
      stylistic preferences not encoded in rules/standards, and TODOs that already have
      tracked tickets.

      The skip list is what keeps false positives from destroying author trust.
-->

Report only what fits the taxonomy below, so two teammates running `/review` on the same PR reach the same verdict.

**Must-report** — always raise these:

- **Bugs** — logic errors, a missing `await` on a promise, race conditions, off-by-one, unhandled null/undefined.
- **Security** — raw SQL interpolating user input, a handler missing an auth check, secrets or tokens committed in code, `dangerouslySetInnerHTML`.
- **Convention violations** the path-scoped rules catch — e.g. a handler returning `{ status: 404 }` instead of throwing `ApiError`, a handler importing `pool` directly, a snapshot test, a mocked DB in a repository test.
- **Breaking changes** — response-shape or exported-signature changes without a coordinated consumer update.
- **Migration safety** — a non-forward migration, or a column drop that runs before its readers are gone.

**Skip** — do not report, and do not let these change the verdict:

- Minor formatting (spacing, quotes, import order) — Prettier owns it.
- Naming bikeshedding when the existing name is clear enough.
- Personal stylistic preferences not encoded in `.claude/rules/` or `.claude/standards/`.
- `TODO`/`FIXME` comments that already reference a tracked ticket.

The skip list is not optional. Reporting items from it is what erodes author trust in the command.

## Phase 3 — Bundling: interacting vs. independent findings

<!--
TODO: Write the bundling guidance. The contrast is hard to internalize without a
      concrete pair of examples (which you'll write in the Examples section below).

      Interacting findings: those that overlap or affect the same fix. Bundle into
      ONE detailed message with all context. Example: a missing `await` and a missing
      transaction wrapper on the same function — the author needs to see them together
      because the fix changes both lines.

      Independent findings: separate functions, separate files, no shared fix. Report
      SEQUENTIALLY as discrete items so each piece of feedback is actionable.

      Give a one-line heuristic for telling them apart (e.g. "if fixing A changes the
      code B references, they are interacting").
-->

Group findings by whether their fixes touch the same code.

- **Interacting findings** overlap on a single fix. **Bundle** them into one detailed message that carries all the context together, because the author edits the same lines to resolve every point. Example: a missing `await` and a missing `withTransaction` wrapper on the same function — fixing one changes the very lines the other refers to, so splitting them forces the author to reconcile two messages against one edit.
- **Independent findings** live in separate functions or files and share no fix. Report them **sequentially** as discrete, separately-actionable items so each can be addressed and resolved on its own.

Heuristic: *if fixing A changes the code B points at, they are interacting — bundle them; otherwise they are independent — report them separately.*

## Phase 4 — Output format

For each finding, produce:

```
[severity] path/to/file.ts:line
finding: <one-sentence description>
fix: <one-sentence recommendation>
```

Severity is `bug` | `security` | `convention` | `breaking`. End with a one-line verdict: `approve`, `comment`, or `request-changes`.

## Examples

<!--
TODO: Write at least TWO concrete input/output examples using the format above.

Per Task 3.5, examples are the difference between a command that produces
consistent output across team members and one that produces wildly varying output.

Example 1 — INDEPENDENT findings. Show a diff with two unrelated convention
violations on the same file (e.g. a handler returning a `{ status: 404 }` shape
instead of throwing ApiError, AND a raw SQL call that bypasses the repository
layer). Report each as a separate `[convention]` finding. End with a verdict.

Example 2 — INTERACTING findings. Show a diff where multiple problems share a
single fix (e.g. a refundOrder handler that has missing awaits AND no transaction
wrapper AND wrong ordering between paymentService and DB writes). Bundle them
into ONE `[bug]` finding that lists the three issues together because the fix
changes the same three lines. End with a verdict.
-->

### Example 1 — independent findings (report separately)

**Input** — diff of `src/api/orders/handler.ts`:

```diff
 export async function getOrder(req) {
-  const order = await orders.findById(req.params.id);
-  if (!order) return { status: 404, body: { error: "not found" } };
+  const order = await pool.query(`SELECT * FROM orders WHERE id = ${req.params.id}`);
+  if (!order) return { status: 404, body: { error: "not found" } };
   return { status: 200, body: order };
 }
```

**Output** — two unrelated violations, reported as discrete items:

```
[convention] src/api/orders/handler.ts:3
finding: Handler returns a bare { status: 404 } shape for a not-found instead of throwing ApiError.
fix: Throw ApiError(404, "order_not_found", "Order not found") and let the middleware format it.

[security] src/api/orders/handler.ts:2
finding: Raw SQL interpolates req.params.id directly, bypassing the repository layer and opening SQL injection.
fix: Call orders.findById(req.params.id) from src/db/orders.ts — handlers never touch pool or raw SQL.

verdict: request-changes
```

### Example 2 — interacting findings (bundle into one)

**Input** — diff of `src/api/orders/refund.ts`:

```diff
 export async function refundOrder(req) {
-  return withTransaction(async (tx) => {
-    await paymentService.refund(req.body.orderId);
-    await orders.markRefunded(tx, req.body.orderId);
-  });
+  orders.markRefunded(req.body.orderId);
+  paymentService.refund(req.body.orderId);
 }
```

**Output** — three problems that share one fix, bundled together:

```
[bug] src/api/orders/refund.ts:2-3
finding: The refund path has three interacting defects that must be fixed as one change: (1) neither call is awaited, so errors are swallowed and the response returns before work completes; (2) the two writes are no longer wrapped in withTransaction, so a payment failure leaves the order marked refunded; (3) the order is marked refunded BEFORE the payment succeeds, inverting the safe ordering.
fix: Restore a single withTransaction block, await paymentService.refund(...) first, then await orders.markRefunded(tx, ...) — the same three lines resolve all three issues.

verdict: request-changes
```

## Notes

- This command is project-scoped (`.claude/commands/review.md`) so everyone on the team gets the same review. If you want to layer personal preferences (e.g. a stricter accessibility check on your own PRs), put a `~/.claude/commands/review-strict.md` in your home directory — it will not affect teammates.
- If a finding requires running code or modifying files to verify, ask the author to run a specific check rather than attempting it from the review session. This command's `allowed-tools` are read-only by design.

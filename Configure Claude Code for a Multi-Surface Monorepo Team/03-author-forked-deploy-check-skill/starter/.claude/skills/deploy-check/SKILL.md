---
# TODO: Write the YAML frontmatter for this skill. It must include:
#
#   name: deploy-check
#   description: (one line naming what the skill does)
#   context: fork                    ← runs in a forked sub-agent (the key piece)
#   argument-hint: "..."             ← QUOTE any value containing a colon. Unquoted
#                                      `argument-hint: <foo: bar>` parses as a NESTED
#                                      MAPPING and breaks frontmatter loading.
#   allowed-tools: a READ-ONLY allowlist (Read, Grep, Glob, granular Bash sub-commands
#                  like Bash(git status:*) and Bash(gh pr view:*) — no Edit, Write,
#                  NotebookEdit, or unrestricted Bash).
#
# A note on schema drift: the current Claude Code IDE LSP (2026-05) may not list
# `context` or `allowed-tools` in its skill-frontmatter completions. That's the LSP
# lagging the product spec, not a problem with your file — see Troubleshooting in
# the exercise instructions.
name: deploy-check
description: Read-only pre-deployment validation checklist for the current branch
context: fork
argument-hint: "[check-name] — optional; omit to run all checks, or pass one (e.g. \"uncommitted\", \"migrations\", \"ci\")"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git ls-files:*)
  - Bash(gh pr view:*)
  - Bash(gh pr checks:*)
---

# /deploy-check

Runs the team's pre-deployment validation checklist against the current working tree and the branch you're about to ship. Read-only by design — this skill never modifies files, never pushes, never deploys. It returns a single structured summary so the calling session can decide whether to proceed.

## Why this is a skill (not a CLAUDE.md addition)

<!--
TODO: Write a 2-3 line decision rubric explaining why /deploy-check is a SKILL
      rather than always-loaded CLAUDE.md guidance.

      The contrast you must convey:
        - Skill: on-demand, forked, task-specific. You only need it right before a
          deploy. It produces verbose intermediate output (file enumeration, diff
          parsing, check execution traces) that has no value once the summary is
          known.
        - CLAUDE.md: always-loaded, universal. Conventions that need to be present
          in every session (e.g. "tests are co-located", "throw ApiError for
          validation failures") belong here.

      Without this contrast, teammates default to dumping everything into CLAUDE.md
      and end up with a 600-line monolith that wastes context on every session.

      Rule-of-thumb summary at the end: on-demand / forked / task-specific → skill;
      always-loaded / universal → CLAUDE.md.
-->

A **skill** is the right home for `/deploy-check` because the work is **on-demand, forked, and task-specific**: you only need it in the few minutes before a deploy, and its execution produces verbose intermediate output (file enumeration, diff parsing, check traces) that has no value once the verdict is known. Loading any of that into every session would be pure waste.

`CLAUDE.md`, by contrast, is **always-loaded and universal** — it should hold only the conventions that must be present in *every* session regardless of task (e.g. "tests are co-located", "throw `ApiError` for validation failures"). Deploy-check logic is neither always-relevant nor universal, so it does not belong there.

**Rule of thumb:** on-demand / forked / task-specific → **skill**; always-loaded / universal → **CLAUDE.md**. Follow it and `CLAUDE.md` stays scannable instead of growing into a 600-line monolith that taxes context on every session.

## Why `context: fork`

<!--
TODO: Write the rationale paragraph for `context: fork`. It MUST do two things:

  (a) Explicitly state that the goal is to keep verbose intermediate output OUT OF
      THE MAIN SESSION / conversation. A deploy check walks the working tree,
      inspects diffs, and runs several enumeration passes — none of that has any
      value to the calling session once we know whether to ship. Only the
      structured summary should return to the main conversation.

  (b) Note that `context: fork` is a Claude Code PRODUCT FEATURE operating at the
      skill-invocation layer, conceptually analogous to the Architect's Playbook
      *Branching Reality* pattern (which describes session-level forking via
      `fork_session`). Mention both so a reader who knows the Playbook can map the
      mental model.
-->

`context: fork` runs the entire checklist in a forked sub-agent so that its verbose intermediate output stays **out of the main session**. A deploy check walks the working tree, inspects diffs, and runs several enumeration passes; none of that noise has any value to the calling conversation once we know whether it is safe to ship. Only the structured verdict summary crosses back — the raw traces are discarded with the fork.

Mechanically, `context: fork` is a Claude Code **product feature** operating at the skill-invocation layer. It is conceptually analogous to the Architect's Playbook **Branching Reality** pattern, which describes session-level forking via `fork_session`: both spin up an isolated branch of execution whose scratch work never pollutes the parent. If you know the Playbook pattern, `context: fork` is that same mental model applied automatically each time this skill is invoked.

## Checks

Run all three. Each check produces a pass-or-fail verdict; if any fails, the overall summary is **fail**.

<!--
TODO: Write at least THREE pre-deployment checks. For each check, declare:

  - Detect: the exact command(s) or signal(s) that determine whether the
            condition holds.
  - Pass:   what a passing result looks like.
  - Fail:   what a failing result looks like, including what to surface in the
            verdict-summary so the author can act on it.

Suggested checks (you may substitute equivalents if your team's deploy
shape needs different ones):

  1. Uncommitted changes — `git status --porcelain` returns empty.
  2. Migrations up-to-date with code — every new repository import in the diff
     since the target branch is backed by a migration file in the same branch.
  3. CI checks green on the open PR — `gh pr view --json statusCheckRollup`
     reports all required checks as SUCCESS.
-->

### Clean working tree

- **Detect:** run `git status --porcelain` and inspect its output.
- **Pass:** the command prints nothing — every change is committed to the branch being shipped.
- **Fail:** any lines are printed. Surface the count and the first few paths (e.g. "3 uncommitted files: src/api/orders/refund.ts, …") so the author knows to commit or stash before deploying.

### Migrations match the code

- **Detect:** diff the branch against its merge base (`git diff --name-only main...HEAD`) and cross-check: for every new repository query in `src/db/` that references a new table or column, confirm a matching `NNNN__*.sql` migration file appears in the same diff.
- **Pass:** every schema-touching code change is backed by a forward migration committed on the same branch.
- **Fail:** code references a table/column with no accompanying migration (or a migration exists with no code using it). Surface the specific repository file and the missing migration so the author can add it before the deploy hits an empty schema.

### CI is green on the PR

- **Detect:** run `gh pr checks` (or `gh pr view --json statusCheckRollup`) for the branch's open PR.
- **Pass:** every required check reports SUCCESS.
- **Fail:** any required check is FAILURE, PENDING, or missing. Surface the failing check names and their URLs in the summary so the author can open them directly rather than re-deriving which check broke.

## Output format

Return exactly this shape to the main session:

```
verdict: pass | fail
checks:
  - name: <check-name>
    status: pass | fail
    detail: <one line or empty>
```

Do not include the raw `git status`, raw diff hunks, or full check logs in the returned summary — those stay in the fork. If the author wants to investigate a failed check, they can re-invoke the skill targeting that single check or run the underlying command themselves.

## Personalization

<!--
TODO: Add a short note explaining that this skill is project-scoped
      (`.claude/skills/deploy-check/`) so the whole team gets the same checks.
      Mention that a teammate who wants a stricter personal variant — say, one
      that additionally fails when the diff exceeds 500 lines without a long
      enough PR description — can create a parallel skill at
      `~/.claude/skills/deploy-check-strict/` with a different name. Their
      variant will not be committed to the repo and will not affect teammates.
-->

This skill is **project-scoped** (`.claude/skills/deploy-check/`), so it lives in git and every teammate runs the exact same three checks — that shared baseline is the point.

If you want a stricter personal gate — say, one that additionally fails when the diff exceeds 500 lines without a sufficiently detailed PR description — create a **parallel** skill under a different name at `~/.claude/skills/deploy-check-strict/`. Because it lives in your home directory rather than the repo, it is never committed and never affects teammates; it layers your extra checks on top of the shared one for your own deploys only.

## What this skill deliberately does not do

- It never pushes, deploys, or runs migrations. The `allowed-tools` allowlist is read-only by construction; even if a future maintainer adds `Write` here, the team's `/review` command should catch the change.
- It does not run the test suite. Tests have their own pre-merge gate in CI; duplicating that here would slow every deploy check without adding signal.
- It does not check for secrets in code. That's the job of the `gitleaks` pre-commit hook, which fails the commit, not the deploy.

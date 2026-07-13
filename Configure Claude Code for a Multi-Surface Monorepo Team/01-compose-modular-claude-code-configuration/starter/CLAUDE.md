# E-Commerce Platform — Shared Claude Code Conventions

This file is the **project-level** entry point for the e-commerce monorepo. Every teammate's Claude session loads it automatically.

## Scope: what belongs here vs. elsewhere

Claude Code composes its configuration from three scopes. Put each rule where its audience is:

| Scope | Location | Shared with the team? | Use it for |
|---|---|---|---|
| **Project-level** | `./CLAUDE.md` and `.claude/` (committed to the repo) | **Yes** — version-controlled, loads for every teammate | Conventions the whole team must follow: shared standards, path-scoped rules, review/deploy workflows |
| **User-level** | `~/.claude/` (your own machine) | **No — not shared with teammates via version control**; it stays local to you | Personal working preferences that should not be imposed on the team — e.g. your preferred **commit message** style, editor/theme preferences, or personal command aliases |
| **Directory-level** | a `CLAUDE.md` inside a subdirectory (e.g. `src/api/CLAUDE.md`) | Yes, if committed — but only loads when Claude works inside that subtree | Conventions specific to one area of the monorepo that would be noise elsewhere |

The split is deliberate: anything a teammate needs in order to produce team-consistent output belongs at **project-level** so it travels with the repo. Anything that is purely your own working style belongs at **user-level** so it never lands in a teammate's session — your `~/.claude/` settings are yours alone and are never committed.

## Shared standards (modular via @-imports)

The actual conventions live in focused files so this entry point stays scannable. Each line below is an `@`-import that pulls the file's contents into the session:

@.claude/standards/frontend.md
@.claude/standards/api.md
@.claude/standards/database.md
@.claude/standards/testing.md

Path-scoped rules in [.claude/rules/](.claude/rules/) layer on top of these standards and activate only when Claude is editing matching files (React components, API handlers, test files).

## Repository layout

```
src/components/   React components (functional + hooks)
src/pages/        Top-level routes
src/api/          Node.js API handlers
src/db/           PostgreSQL repository-pattern modules
```

Tests are co-located: `Foo.tsx` lives next to `Foo.test.tsx`.

## Troubleshooting

If a `CLAUDE.md` instruction isn't being followed, run **`/memory`** to see exactly which configuration files — project-level, user-level, and directory-level — actually loaded for the current session. A hierarchy or `@`-import problem almost always shows up here as a file you expected to load but that isn't listed.

## Team workflows

- `/review <pr-ref>` — codified PR review checklist. (You will author this in Exercise 2.)
- `/deploy-check` — read-only pre-deployment validation. (You will author this in Exercise 3.)

For decisions about when to use plan mode vs. direct execution on this codebase, you will produce a team decision doc in Exercise 4.

---
description: Enforcement rules for Node.js API handlers under src/api/
paths:
  - "src/api/**/*"
---

# API handler rules

Loads when editing any file under `src/api/`. These layer concrete enforcement on top of `.claude/standards/api.md` — they fire *only* while touching handler code.

## Handler signature

- Every handler is `export async function handler(req): Promise<{ status: number; body: unknown }>`. Return the `{ status, body }` object — never call `res.send`, `res.json`, or `res.end`. The adapter owns the wire.
- No default exports from handler files. A file under `src/api/` exports one or more named handlers so the router can bind them explicitly.
- Do not read `req.headers`/`req.cookies` directly for auth. Consume the already-parsed `req.auth` context the middleware attaches; if it is missing, that is a routing bug, not something to work around.

## Error discipline

- Throw `ApiError(status, code, message)` from `src/api/_lib/error.ts` for every expected failure. A bare `throw new Error(...)` in a handler is a defect — it surfaces as an opaque 500.
- Never wrap a handler body in a catch-all `try/catch` that returns `{ status: 500 }`. Let unexpected exceptions propagate to the global handler so the stack trace survives.

## Boundaries

- Handlers call repository functions from `src/db/` and services from `src/services/`. Importing `pool` from `src/db/pool.ts` or writing raw SQL inside a handler is forbidden.
- Validate the request body against the matching schema in `src/api/_schemas/` before touching any field. Do not hand-roll validation with `if (!body.foo)` checks.
- Response bodies must conform to the schema in `src/api/_schemas/`; adding a field means updating the schema in the same commit.
- Compose multi-statement writes inside `withTransaction` from `src/db/tx.ts`. A handler that issues two separate repository writes without a wrapping transaction is a correctness bug.

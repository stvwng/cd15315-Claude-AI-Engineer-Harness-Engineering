# Solution — Exercise 4

This directory contains the project state after Exercise 4. **This is the complete project module reference state** — equivalent to the team's working configuration system in production.

Compared to the starter, `docs/plan-mode-vs-direct-execution.md` is now complete:

- Knight-Webb citation block sourced via the Module 8 curriculum doc's anchor-talks table.
- Section 1 — extracting a shared `useCart` hook from `src/components/Cart/Cart.tsx`, `src/components/Checkout/Checkout.tsx`, and `src/components/MiniCart/MiniCart.tsx`. Cites "prevent costly rework."
- Section 2 — adding a `min: 0` validation to one quantity field in `src/api/orders/handler.ts`.
- Section 3 — `processRefund` call-site inventory across `src/api/orders/refund.ts`, `src/api/billing/issue.ts`, and `src/services/payment.ts`, referencing the scratchpad pattern.
- Section 4 — renaming `ordersRepo.findById` → `getById` in `src/db/orders.ts`, plan-mode for the call-site investigation followed by direct execution for the mechanical rename.

## Verify

```bash
pytest -q && ecommerce-team-config .
```

Expected: **35 passed** + `OK`.

## Differences vs. the provided reference solution

The only differences between this directory and the reference repo at `module-03-e-commerce-platform-team-configuration/` are:

- `data/.gitkeep` and `fixtures/.gitkeep` — added to keep the empty scaffold directories trackable in version control. Cleanup-only; no behavior change.
- The SME-internal `spec/` and `notes/` directories are intentionally omitted from the learner-facing copy. They are not needed to build or verify the project.

# Architect Role

You review the shared spec for design quality before implementation begins.

## Responsibilities

- Check service boundaries against `AGENTS.md`.
- Verify route, controller, service, repository, schema, and core layers stay
  in their expected responsibilities.
- Check frontend plans against the web standards when `apps/web` is involved.
- Flag cross-service coupling, unclear interfaces, missing error handling, and
  validation gaps.
- Prefer small changes that fit existing patterns.

## Output

Report one of:

- `APPROVED`: the spec is implementable.
- `NEEDS_REVISION`: list concrete spec changes needed before implementation.

Write separate architecture review notes, when needed, to
`.tmp/<topic>/reviews/architect-review.md`.

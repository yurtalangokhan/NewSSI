# Planner Role

You turn a user request into shared implementation context.

## Responsibilities

- Read `AGENTS.md`, relevant `docs/**/*.md`, and related
  `.tmp/<topic>/**/*.md`.
- Confirm a local branch exists for the spec before writing or updating
  `.tmp/<topic>/design.md`. If the working tree is already dirty, preserve the
  existing changes and record that context in the spec.
- Create or update `.tmp/<topic>/design.md` from
  `.agents/templates/spec-template.md`.
- Capture goal, scope, non-scope, architecture, data flow, error handling,
  testing strategy, implementation order, per-file changes, validation gates,
  risks, and resolved decisions.
- Keep the plan small enough that each implementation step can be validated.
- Do not start implementation until the spec is clear and approved by the
  coordinating agent or user.

## Output

Write the shared spec file and report:

- spec path
- key decisions
- implementation order
- unresolved blockers, if any

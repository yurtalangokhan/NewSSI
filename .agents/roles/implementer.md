# Implementer Role

You implement one task from the shared spec.

## Responsibilities

- Read `AGENTS.md`, your task brief, and only the relevant parts of the shared
  spec.
- Follow the task brief exactly. Do not expand scope.
- Use test-driven development for behavior changes and bug fixes: write or
  update a focused failing test first, verify it fails for the expected reason,
  then implement the smallest passing change.
- Preserve existing user changes in the working tree.
- Run the validation command named in the task brief.
- Write your report to `.tmp/<topic>/tasks/task-<n>-report.md`.

## Output

Return only:

- status: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`
- changed files
- validation commands and results
- report path
- concerns, if any

# <Topic> Design

## Goal

Describe the outcome this work must achieve.

## Scope

This design covers:

- <item>

It excludes:

- <item>

## Shared Context

- Coordinating agent:
- Local branch:
- Relevant roles from `.agents/team.yaml`:
- Related docs:
- Related existing specs:

## Architecture

Describe the services, modules, components, and boundaries involved.

## Interfaces

List route, controller, service, repository, schema, component, or tool
interfaces that will be added or changed.

## Data Flow

Describe how data moves through the system before, during, and after the
change.

## Error Handling

Describe expected errors, where they are raised, and where they are translated
for users or callers.

## Testing Strategy

List the regression tests and validation commands required for this work.
Behavior changes should use TDD.

## Implementation Order

1. Add or update focused failing tests for the first behavior.
2. Implement the smallest change that satisfies the tests.
3. Run the validation gate for the changed surface.

## Per-File Changes

| File | Change |
|---|---|
|  |  |

## Agent Handoff Notes

- This spec must live at `.tmp/<topic>/design.md`.
- This spec must start on its own local branch before implementation work
  begins.
- Progress must be tracked at `.tmp/<topic>/progress.md`.
- Task briefs must live at `.tmp/<topic>/tasks/task-<n>-brief.md`.
- Task reports must live at `.tmp/<topic>/tasks/task-<n>-report.md`.
- Task diffs, when needed, must live at
  `.tmp/<topic>/tasks/task-<n>-diff.md`.
- Task reviews must live at `.tmp/<topic>/reviews/task-<n>-review.md`.
- Re-reviews must live at
  `.tmp/<topic>/reviews/task-<n>-rereview-<m>.md`.
- Each implementer reads only the task brief, the shared spec sections named in
  the brief, and the files needed for its task.

## Validation Gates

- <command or gate>

## Acceptance Criteria

- <criterion>

## Open Questions

- <question>

## Resolved Decisions

- <decision>

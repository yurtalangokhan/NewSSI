# Web architecture

The web app uses Next.js App Router and the Onyx design system. Keep page
composition, data fetching, reusable UI, and low-level utilities separated.

## Boundaries

- Use absolute imports with `@/` for application source and `@tests/` for test
  helpers.
- Use `@/refresh-components/` or `@opal/` components for inputs and controls.
- Use `@/icons/` as the only icon source.
- Use `Text` components for visible copy instead of raw heading or paragraph
  elements.
- Use `useSWR` for client data fetching at the component level.

## Backend access

Backend calls go through configured rewrites and service-scoped paths. Do not
hardcode backend ports or legacy `/api/*` paths in new code.

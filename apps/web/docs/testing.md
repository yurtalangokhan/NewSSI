# Web testing

Use this document to choose validation for web changes.

## Commands

Run commands from `apps/web/` or use `npm --prefix apps/web` from the repository
root.

```sh
npm run lint
npm run types:check
npm test
npm run test:ci
npm run test:e2e
```

Use focused Jest paths while developing. Run lint, type checks, and the relevant
test suite before marking a frontend change ready.

## Focus areas

- Unit and integration tests are split into Jest projects.
- Use `setupUser()` from `@tests/setup/test-utils`.
- Mock HTTP with `jest.spyOn(global, "fetch")` and comment which endpoint each
  mock serves.
- Playwright end-to-end tests live under `tests/e2e/`.

Run `make quality-staged` from the repository root before committing or pushing.

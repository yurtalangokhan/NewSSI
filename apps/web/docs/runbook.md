# Web runbook

Use this runbook for local startup and frontend operational checks.

## Startup

Run commands from `apps/web/`.

```sh
npm install
npm run dev
```

The development server uses the explicit Webpack flag configured in
`package.json`. Backend traffic must go through configured rewrites or Kong
service paths.

## Production build

Use the build command before deploy-oriented changes.

```sh
npm run build
```

Sentry activates only when both `SENTRY_AUTH_TOKEN` and
`NEXT_PUBLIC_SENTRY_DSN` are configured.

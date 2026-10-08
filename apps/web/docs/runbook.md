# Web runbook

Use this runbook for local startup and frontend operational checks.

## Startup

Install Node.js and `uv`, then run commands from `apps/web/`.

```sh
npm install
npm run dev
```

The npm development, build, and start commands use `config_manager` to load the shared
`configs/.env` before launching Next.js. Existing process environment values
take precedence. Don't create an `apps/web/.env` file or use `npx next dev`
directly for local startup, because it bypasses the shared loader.

Set `GATEWAY_URL` in the central file to your APISIX gateway URL. Restart the
web process after changing environment settings. Server-only values stay in
the server environment; don't copy them into Next.js's `env` configuration.

Web service URLs must use the same origin as `GATEWAY_URL`, with these paths:

| Variables | Gateway path |
| --- | --- |
| `AGENT_SERVICE_URL` | `/agent-service` |
| `USER_SERVICE_URL` | `/user-service` |
| `RAG_SERVICE_URL` | `/rag-service` |
| `TOOLS_SERVICE_URL` | `/tools-service/mcp` |
| `MCP_INTERNAL_URL` | `/internal/tools-service/mcp` |

`INTERNAL_URL`, `LANGCONNECT_URL` and `MCP_SERVER_URL` are obsolete: the web
code does not read them and the central catalog no longer declares them.

Direct backend addresses such as `localhost:8090` fail the web routing guard.

Development uses Turbopack by default; `npm run dev:webpack` selects Webpack.
Both accept Next.js arguments, for example `npm run dev -- --port 3000`.
Backend traffic must go through APISIX service paths. Container builds read
`configs/.env` through the Compose build secret `web_env` (mounted as `/app/.env`
during `next build` only; the copy Next.js makes in the standalone output is
stripped in the same step) plus the gateway addresses as build args; the
standalone runtime receives its environment from Compose. `NEXT_PUBLIC_*` values
are inlined at build time, and that step's cache ignores the secret, so rebuild
the web image with `--no-cache` after changing one.

## Production build

Use the build command before deploy-oriented changes.

```sh
npm run build
```

Sentry activates only when both `SENTRY_AUTH_TOKEN` and
`NEXT_PUBLIC_SENTRY_DSN` are configured.

# Agent service runbook

Use this runbook for local startup, operational checks, and provider-specific
runtime setup.

## Startup

Run these commands from `apps/agent-service/` unless noted otherwise.

```sh
make dev-install
make run
```

The root stack uses Kong for external traffic. Direct local service access uses
the port configured in environment files. Do not hardcode service ports in code
or documentation snippets.

## Development without real model credentials

Set `FAKE_MODEL=true` when you need local tests or smoke checks without calling
a real LLM provider. Production and shared environments must resolve the model
through configured provider defaults.

## Provider notes

- Use [Ollama](ollama.md) for local model setup.
- Use [Google models](google-models.md) for Gemini Developer API and Vertex AI
  setup.
- Use [file-based credentials](file-based-credentials.md) for local credential
  files that must not be committed or baked into images.

## Live connector checks

Assigned connector tools require a running tools-service that advertises
`connector_list_resources` and `connector_read`. Restart tools-service after
adding tool modules, and reload agent-service to clear its tool cache. A configurable
agent refuses to run when an assigned connector tool is missing.

Set tools-service's `AGENT_SERVICE_URL` to the configured agent API base, including
`/api/v1`, and configure matching internal service authentication. The callback
resolves only connectors and operations assigned to the saved agent.

Airbyte API responses mask source passwords. For Airbyte 0.50.x using
`SECRET_PERSISTENCE=NONE`, configure these agent-service environment variables:

- `AIRBYTE_CONFIG_DATABASE_URL`: PostgreSQL URL for the **same Airbyte instance**
  configured by `AIRBYTE_API_URL`.
- `AIRBYTE_CONFIG_DATABASE_USER` and `AIRBYTE_CONFIG_DATABASE_PASSWORD`: config
  database credentials, kept in local environment configuration.
- `AIRBYTE_SECRET_PERSISTENCE`: `NONE`, only when it matches the Airbyte deployment.

This database is Airbyte's configuration store, not the connector's source database.
The reader resolves local `_secret` coordinates from the `secrets` table in the
same read-only transaction; credentials remain server-side.
Other secret persistence modes are not supported by the current configuration
reader. Missing settings produce a connector error; indexing does not resolve it.
Confirm a successful `connector_read` before treating output as source data.
If a model prints connector-call JSON instead of issuing a native tool call, the
configurable agent retries the model once per user turn. The JSON itself is never
executed. Repeated malformed output produces an explicit failure response.

When tools-service runs outside Docker, a source's Docker hostname may be
unreachable. Set tools-service's optional `CONNECTOR_POSTGRES_ENDPOINTS` to a JSON
object keyed by saved datasource ID, with `host` and integer `port` values for its
published PostgreSQL endpoint. Only that datasource's live-read host and port are
overridden; saved credentials, database, selected streams, and Airbyte indexing
configuration remain unchanged. This setting is administrator configuration and
is never accepted from model arguments.

## API reference

Use [api.md](api.md) for the human-maintained endpoint contract. The
`openapi.json` file is generated and must not be treated as default reading
material for planning tasks.

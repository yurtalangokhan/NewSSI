# Docker Setup Guide

This application is built with Next.js, which requires `NEXT_PUBLIC_` environment variables to be present **at build time** in order to be available in the browser.

## Building the Image

When building the Docker image, you **MUST** provide the Supabase configuration and API URL as build arguments.

### Command Line

```bash
docker build \
  --build-arg NEXT_PUBLIC_SUPABASE_URL="https://your-project.supabase.co" \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY="your-anon-key" \
  --build-arg NEXT_PUBLIC_LANGGRAPH_API_URL="http://localhost:8123" \
  -t open-agent-platform .
```

### Docker Compose

If you are using Docker Compose, ensure your `docker-compose.yml` passes the arguments under the `build` section:

```yaml
services:
  web:
    build:
      context: .
      args:
        NEXT_PUBLIC_SUPABASE_URL: ${NEXT_PUBLIC_SUPABASE_URL}
        NEXT_PUBLIC_SUPABASE_ANON_KEY: ${NEXT_PUBLIC_SUPABASE_ANON_KEY}
        NEXT_PUBLIC_LANGGRAPH_API_URL: ${NEXT_PUBLIC_LANGGRAPH_API_URL}
    ports:
      - "3000:3000"
```

## Common Issues

### Sign-in Redirect Not Working / Defaulting to Home
If you see behavior where:
1. You try to sign in.
2. The page refreshes or does nothing.
3. No error message appears in the UI.
4. The console might show errors related to missing Supabase URL/Key.

**Cause:** The image was built without the `NEXT_PUBLIC_` build arguments. Next.js baked in `undefined` for these values, so the client-side Supabase client cannot connect.

**Fix:** Rebuild the image ensuring you pass the `--build-arg` flags.

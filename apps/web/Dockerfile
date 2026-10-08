FROM node:22-alpine AS base

LABEL com.atlas.maintainer="founders@atlas.app"
LABEL com.atlas.description="This image is the web/frontend container of Atlas which \
contains code for both the Community and Enterprise editions of Atlas. If you do not \
have a contract or agreement with DanswerAI, you are not permitted to use the Enterprise \
Edition features outside of personal development or testing purposes. Please reach out to \
founders@atlas.app for more information. Please visit https://github.com/atlas-dot-app/atlas"

# Step 1. Install dependencies + rebuild the source code only when needed
FROM base AS builder
# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy package files first for better layer caching
# This layer will be cached unless package.json or package-lock.json changes
COPY apps/web/package.json apps/web/package-lock.json ./
COPY apps/web/lib/opal/package.json ./lib/opal/

# Install dependencies
# package-lock.json is written by npm 11 (node 24 on the developer machines).
# node:22-alpine ships npm 10, which builds a different ideal tree from the same
# lock (it still nests the optional peer @swc/helpers@0.5.23 under i18next-cli's
# and i18next-resources-for-ts' @swc/core) and rejects the lock as out of sync.
# Install the npm major that wrote the lock before reading it.
RUN npm install -g npm@11
RUN npm ci

# pull in source code / package.json / package-lock.json
COPY apps/web/ .

# needed to get the `standalone` dir we expect later
ENV NEXT_PRIVATE_STANDALONE=true

# Disable automatic telemetry collection
ENV NEXT_TELEMETRY_DISABLED=1

# Environment variables must be present at build time
# https://github.com/vercel/next.js/discussions/14030
#
# `next build` evaluates the typed env module (src/lib/env) and next.config.js,
# so it validates the whole web configuration and inlines every NEXT_PUBLIC_*
# value into the browser bundle. Locally `npm run build` gets that
# configuration from config_manager reading configs/.env; here Compose hands
# the same file in as the build secret `web_env`, mounted as /app/.env for the
# build step only (Next.js loads it like any .env file; a BuildKit secret never
# lands in a layer, and the copy `next build` puts into the standalone output
# is removed in the same step -- but the secret is not part of the step's cache
# key either, so a changed NEXT_PUBLIC_* value needs a `--no-cache` build).
#
# The gateway addresses stay build args, mirroring the runtime `environment`
# block in Compose: next.config.js bakes the in-network gateway address into
# its rewrites, the env module checks that all six share one origin, and a
# value already in the environment wins over the file. Nothing else may be
# `ENV`ed here: an unset build arg becomes the empty string, which would
# shadow the value in the file.
# NOTE: if you add something here, make sure to add it to the runner as well

ARG GATEWAY_URL
ENV GATEWAY_URL=${GATEWAY_URL}

ARG AGENT_SERVICE_URL=http://apisix:8000
ENV AGENT_SERVICE_URL=${AGENT_SERVICE_URL}

ARG USER_SERVICE_URL
ENV USER_SERVICE_URL=${USER_SERVICE_URL}

ARG RAG_SERVICE_URL=http://apisix:8000
ENV RAG_SERVICE_URL=${RAG_SERVICE_URL}

ARG TOOLS_SERVICE_URL
ENV TOOLS_SERVICE_URL=${TOOLS_SERVICE_URL}

ARG MCP_INTERNAL_URL
ENV MCP_INTERNAL_URL=${MCP_INTERNAL_URL}

ARG WEB_DOMAIN
ENV WEB_DOMAIN=${WEB_DOMAIN}

# Add NODE_OPTIONS argument
ARG NODE_OPTIONS

# Use NODE_OPTIONS in the build command. `next build` copies the .env files it
# loaded into .next/standalone (so `next start` would see them); strip that copy
# in the same step, or the runner stage below would ship configs/.env.
RUN --mount=type=secret,id=web_env,target=/app/.env \
    NODE_OPTIONS="${NODE_OPTIONS}" npx next build \
    && rm -f .next/standalone/.env .next/standalone/.env.*

# Step 2. Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

# Remove global node modules, since they are not needed by the actual app
# (all dependencies are copied over into the `/app` dir itself). These
# global modules may be outdated and trigger security scans.
RUN rm -rf /usr/local/lib/node_modules

# Not needed, set by compose
# ENV NODE_ENV production

# Disable automatic telemetry collection
ENV NEXT_TELEMETRY_DISABLED=1

# Don't run production as root
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
USER nextjs

# Add back in if we add anything to `public`
COPY --from=builder /app/public ./public

# Automatically leverage output traces to reduce image size
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Environment variables must be redefined at run time
# NOTE: if you add something here, make sure to add it to the builder as well


ARG AGENT_SERVICE_URL=http://apisix:8000
ENV AGENT_SERVICE_URL=${AGENT_SERVICE_URL}

ARG USER_SERVICE_URL
ENV USER_SERVICE_URL=${USER_SERVICE_URL}

ARG RAG_SERVICE_URL=http://apisix:8000
ENV RAG_SERVICE_URL=${RAG_SERVICE_URL}

ARG TOOLS_SERVICE_URL
ENV TOOLS_SERVICE_URL=${TOOLS_SERVICE_URL}

ARG WEB_DOMAIN
ENV WEB_DOMAIN=${WEB_DOMAIN}

# allow user to specify custom feedback options
ARG NEXT_PUBLIC_THEME
ENV NEXT_PUBLIC_THEME=${NEXT_PUBLIC_THEME}

ARG NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED
ENV NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED=${NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED}

ARG NEXT_PUBLIC_DISABLE_LOGOUT
ENV NEXT_PUBLIC_DISABLE_LOGOUT=${NEXT_PUBLIC_DISABLE_LOGOUT}

ARG NEXT_PUBLIC_CUSTOM_REFRESH_URL
ENV NEXT_PUBLIC_CUSTOM_REFRESH_URL=${NEXT_PUBLIC_CUSTOM_REFRESH_URL}

ARG NEXT_PUBLIC_POSTHOG_KEY
ARG NEXT_PUBLIC_POSTHOG_HOST
ENV NEXT_PUBLIC_POSTHOG_KEY=${NEXT_PUBLIC_POSTHOG_KEY}
ENV NEXT_PUBLIC_POSTHOG_HOST=${NEXT_PUBLIC_POSTHOG_HOST}

ARG NEXT_PUBLIC_CLOUD_ENABLED
ENV NEXT_PUBLIC_CLOUD_ENABLED=${NEXT_PUBLIC_CLOUD_ENABLED}

ARG NEXT_PUBLIC_SENTRY_DSN
ENV NEXT_PUBLIC_SENTRY_DSN=${NEXT_PUBLIC_SENTRY_DSN}

ARG NEXT_PUBLIC_GTM_ENABLED
ENV NEXT_PUBLIC_GTM_ENABLED=${NEXT_PUBLIC_GTM_ENABLED}

ARG NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED
ENV NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED=${NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED}

ARG NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK
ENV NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK=${NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK}

ARG NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=${NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY}

ARG NEXT_PUBLIC_RECAPTCHA_SITE_KEY
ENV NEXT_PUBLIC_RECAPTCHA_SITE_KEY=${NEXT_PUBLIC_RECAPTCHA_SITE_KEY}

# Default ATLAS_VERSION, typically overriden during builds by GitHub Actions.
ARG ATLAS_VERSION=0.0.0-dev
ENV ATLAS_VERSION=${ATLAS_VERSION}

# Note: Don't expose ports here, Compose will handle that for us if necessary.
# If you want to run this without compose, specify the ports to
# expose via cli

CMD ["node", "server.js"]

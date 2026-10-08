// Always require withSentryConfig
const { withSentryConfig } = require("@sentry/nextjs");
const { requireEnv } = require("./src/lib/env/requireEnv");

// The Content-Security-Policy header moved to src/proxy.ts: script-src
// needs a fresh nonce per request (replacing the 'unsafe-inline' temporary
// exception this file used to carry — see Task 38), which a static header
// here cannot generate. Every other security header below is unaffected.

const isDevelopment = process.env.NODE_ENV === "development";
const optimizePackageImportsConfig = isDevelopment
  ? {}
  : {
      optimizePackageImports: [
        "@opal/icons",
        "@opal/components",
        "@opal/layouts",
        "motion",
      ],
    };
const onDemandEntriesConfig = isDevelopment
  ? {
      maxInactiveAge: 15 * 60 * 1000,
      pagesBufferLength: 50,
    }
  : undefined;

/** @type {import('next').NextConfig} */
const nextConfig = {
  productionBrowserSourceMaps: false,
  output: "standalone",
  transpilePackages: ["@atlas/opal"],
  onDemandEntries: onDemandEntriesConfig,
  turbopack: {
    root: __dirname,
  },
  experimental: {
    ...optimizePackageImportsConfig,
  },
  typedRoutes: true,
  reactCompiler: false,
  images: {
    // Used to fetch favicons
    remotePatterns: [
      {
        protocol: "https",
        hostname: "www.google.com",
        port: "",
        pathname: "/s2/favicons/**",
      },
    ],
    unoptimized: true, // Disable image optimization to avoid requiring Sharp
  },
  async headers() {
    const isDev = process.env.NODE_ENV === "development";
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "Permissions-Policy",
            value:
              "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(), cross-origin-isolated=(), display-capture=(), document-domain=(), encrypted-media=(), execution-while-not-rendered=(), execution-while-out-of-viewport=(), fullscreen=(), geolocation=(), gyroscope=(), keyboard-map=(), magnetometer=(), microphone=(), midi=(), navigation-override=(), payment=(), picture-in-picture=(), publickey-credentials-get=(), screen-wake-lock=(), sync-xhr=(), usb=(), web-share=(), xr-spatial-tracking=()",
          },
        ],
      },
      {
        // Cache static assets (images, icons, fonts, etc.) to prevent refetching and re-renders
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: isDev
              ? "no-cache, must-revalidate" // Dev: always check if fresh
              : "public, max-age=2592000, immutable", // Prod: cache for 30 days
          },
        ],
      },
    ];
  },
  async rewrites() {
    const backendUrl = requireEnv(
      "AGENT_SERVICE_URL",
      process.env.AGENT_SERVICE_URL
    ).replace(/\/+$/, "");
    const posthogHost = requireEnv(
      "NEXT_PUBLIC_POSTHOG_HOST",
      process.env.NEXT_PUBLIC_POSTHOG_HOST
    );
    return {
      // beforeFiles: checked before any filesystem/API routes
      beforeFiles: [],
      // afterFiles: checked after filesystem routes but before dynamic routes
      afterFiles: [
        {
          source: "/ph_ingest/static/:path*",
          destination: "https://us-assets.i.posthog.com/static/:path*",
        },
        {
          source: "/ph_ingest/:path*",
          destination: `${posthogHost}/:path*`,
        },
        // For auth routes without /api prefix
        {
          source: "/auth/:path*",
          destination: `${backendUrl}/auth/:path*`,
        },
      ],
      // fallback: only matched if NO filesystem/API route matches.
      // This ensures /api/rag/* is handled by app/api/rag/[...path]/route.ts
      // (which proxies to RAG_SERVICE_URL) and NOT forwarded to the backend.
      fallback: [
        // OpenAPI documentation
        {
          source: "/api/docs/:path*",
          destination: `${backendUrl}/docs/:path*`,
        },
        {
          source: "/api/docs",
          destination: `${backendUrl}/docs`,
        },
        {
          source: "/openapi.json",
          destination: `${backendUrl}/openapi.json`,
        },
        // Proxy all remaining /api/* requests to the backend.
        // /api/rag/* will NOT reach here because the filesystem route matches first.
        {
          source: "/api/:path*",
          destination: `${backendUrl}/api/:path*`,
        },
      ],
    };
  },
  async redirects() {
    return [
      {
        source: "/chat",
        destination: "/app",
        permanent: true,
      },
      // NRF routes: Redirect to /nrf which doesn't require auth
      // (NRFPage handles unauthenticated users gracefully with a login modal)
      {
        source: "/app/nrf/side-panel",
        destination: "/nrf/side-panel",
        permanent: true,
      },
      {
        source: "/app/nrf",
        destination: "/nrf",
        permanent: true,
      },
      {
        source: "/chat/:path*",
        destination: "/app/:path*",
        permanent: true,
      },
      // Legacy /assistants → /agents redirects (added in PR #8869).
      // Preserves backward compatibility for bookmarks, shared links, and
      // hardcoded URLs that still reference the old /assistants paths.
      // TODO: Remove these redirects in v4.0 — https://linear.app/atlas-app/issue/ENG-3771
      {
        source: "/admin/assistants",
        destination: "/admin/agents",
        permanent: true,
      },
      {
        source: "/admin/assistants/:path*",
        destination: "/admin/agents/:path*",
        permanent: true,
      },
      {
        source: "/ee/assistants/:path*",
        destination: "/ee/agents/:path*",
        permanent: true,
      },
    ];
  },
};

// Sentry configuration for error monitoring:
// - Without SENTRY_AUTH_TOKEN and NEXT_PUBLIC_SENTRY_DSN: Sentry is completely disabled
// - With both configured: Capture errors and limited performance data

// Determine if Sentry should be enabled
const sentryEnabled = Boolean(
  process.env.SENTRY_AUTH_TOKEN && process.env.NEXT_PUBLIC_SENTRY_DSN
);

// Sentry webpack plugin options.
// org/project are only required when Sentry is actually enabled: with it
// disabled, dryRun below skips the real upload these identify, and a
// deployment that never configured Sentry must still build. A hardcoded
// "atlas-vl"/"atlas-web" would otherwise let an enabled-but-misconfigured
// deployment upload source maps to the wrong org silently, or just fail the
// upload with an unexplained 404 in CI.
const sentryWebpackPluginOptions = {
  org: sentryEnabled
    ? requireEnv("SENTRY_ORG", process.env.SENTRY_ORG)
    : process.env.SENTRY_ORG,
  project: sentryEnabled
    ? requireEnv("SENTRY_PROJECT", process.env.SENTRY_PROJECT)
    : process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !sentryEnabled, // Silence output when Sentry is disabled
  dryRun: !sentryEnabled, // Don't upload source maps when Sentry is disabled
  ...(sentryEnabled && {
    sourceMaps: {
      include: ["./.next"],
      ignore: ["node_modules"],
      urlPrefix: "~/_next",
      stripPrefix: ["webpack://_N_E/"],
      validate: true,
      cleanArtifacts: true,
    },
  }),
};

// Export the module with conditional Sentry configuration
module.exports = withSentryConfig(nextConfig, sentryWebpackPluginOptions);

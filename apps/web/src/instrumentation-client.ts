// This file configures the initialization of Sentry on the client.
// The added config here will be used whenever a users loads a page in their browser.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";
import { appSettings } from "@/lib/settings";

if (appSettings.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: appSettings.NEXT_PUBLIC_SENTRY_DSN,

    // Setting this option to true will print useful information to the console while you're setting up Sentry.
    debug: false,

    integrations: [],

    tracesSampleRate: 0.0,
    profilesSampleRate: 0.0,
  });
}

// This export will instrument router navigations, and is only relevant if you enable tracing.
// `captureRouterTransitionStart` is available from SDK version 9.12.0 onwards
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;

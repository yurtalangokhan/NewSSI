import "./globals.css";

import { fetchSettingsSS } from "@/components/settings/lib";
import { fetchEnterpriseSettingsSS } from "@/lib/api/domains/system/server";
import { MODAL_ROOT_ID } from "@/lib/constants";
import { Metadata } from "next";
import { Inter } from "next/font/google";
import { EnterpriseSettings, ApplicationStatus } from "@/interfaces/settings";
import AppProvider from "@/providers/AppProvider";
import { PHProvider } from "./providers";
import {
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/api/domains/session/server";
import { Suspense } from "react";
import PostHogPageView from "./PostHogPageView";
import Script from "next/script";
import { Hanken_Grotesk } from "next/font/google";
import { WebVitals } from "./web-vitals";
import { ThemeProvider } from "next-themes";
import CloudError from "@/components/errorPages/CloudErrorPage";
import Error from "@/components/errorPages/ErrorPage";
import GatedContentWrapper from "@/components/GatedContentWrapper";
import { TooltipProvider } from "@/components/ui/tooltip";
import { fetchAppSidebarMetadata } from "@/lib/navigation/app-sidebar.server";
import { fetchAppBackgroundMetadata } from "@/lib/appBackgroundSS";
import {
  CHAT_BACKGROUND_NONE,
  isCanvasBackground,
} from "@/lib/constants/chatBackgrounds";
import StatsOverlayLoader from "@/components/dev/StatsOverlayLoader";
import PerformanceMeasureGuard from "@/components/dev/PerformanceMeasureGuard";
import { getAppName } from "@/lib/appInfo";
import { resolveLocaleSS } from "@/lib/i18n/locale.server";
import { headers } from "next/headers";
import { appSettings } from "@/lib/settings";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const hankenGrotesk = Hanken_Grotesk({
  subsets: ["latin"],
  variable: "--font-hanken-grotesk",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const logoLocation = `${appSettings.HOST_URL.replace(
    /\/+$/,
    ""
  )}/logo.single.svg`;
  let enterpriseSettings: EnterpriseSettings | null = null;
  if (appSettings.SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED) {
    enterpriseSettings = await (await fetchEnterpriseSettingsSS()).json();
  }

  return {
    title: getAppName(enterpriseSettings?.application_name),
    description: "Question answering for your documents",
    icons: {
      icon: logoLocation,
    },
  };
}

export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [combinedSettings, user, authTypeMetadata, locale] = await Promise.all([
    fetchSettingsSS(),
    getCurrentUserSS(),
    getAuthTypeMetadataSS(),
    resolveLocaleSS(),
  ]);

  const { folded } = await fetchAppSidebarMetadata(user);
  const { backgroundId, backgroundOption } =
    await fetchAppBackgroundMetadata(user);
  // Set by src/proxy.ts per request; the CSP's script-src only allows
  // inline scripts carrying this exact nonce (replacing the 'unsafe-
  // inline' exception this file used to need).
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  const productGating =
    combinedSettings?.settings.application_status ?? ApplicationStatus.ACTIVE;

  const getPageContent = async (content: React.ReactNode) => (
    <html
      lang={locale}
      className={`${inter.variable} ${hankenGrotesk.variable}`}
      suppressHydrationWarning
    >
      <head>
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0, interactive-widget=resizes-content"
        />
        {backgroundOption &&
          !isCanvasBackground(backgroundOption) &&
          backgroundOption.src !== CHAT_BACKGROUND_NONE && (
            <link
              rel="preload"
              as="image"
              href={backgroundOption.src}
              fetchPriority="high"
            />
          )}
        {appSettings.CUSTOM_ANALYTICS_ENABLED &&
          combinedSettings?.customAnalyticsScript && (
            <script
              type="text/javascript"
              nonce={nonce}
              dangerouslySetInnerHTML={{
                __html: combinedSettings.customAnalyticsScript,
              }}
            />
          )}

        {appSettings.GTM_ENABLED && (
          <Script
            id="google-tag-manager"
            strategy="afterInteractive"
            nonce={nonce}
            dangerouslySetInnerHTML={{
              __html: `
               (function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
               new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
               j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
               'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
               })(window,document,'script','dataLayer','GTM-PZXS36NG');
             `,
            }}
          />
        )}
      </head>

      <body className={`relative ${inter.variable} font-hanken`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
          nonce={nonce}
        >
          <div className="text-text min-h-screen bg-background">
            <TooltipProvider>
              <PHProvider>
                <PerformanceMeasureGuard />
                {content}
              </PHProvider>
            </TooltipProvider>
          </div>
        </ThemeProvider>
      </body>
    </html>
  );

  if (!combinedSettings) {
    return getPageContent(
      appSettings.NEXT_PUBLIC_CLOUD_ENABLED ? <CloudError /> : <Error />
    );
  }

  // When gated, wrap children in GatedContentWrapper which checks the path
  // client-side and shows AccessRestrictedPage for non-billing paths.
  //
  // Trade-off: Server components still render and attempt API calls before the
  // client-side check runs. This is safe because the backend license enforcement
  // middleware returns 402 for all non-allowlisted API calls, preventing data
  // leakage. The user sees a brief loading state before being redirected.
  const content =
    productGating === ApplicationStatus.GATED_ACCESS ||
    productGating === ApplicationStatus.SEAT_LIMIT_EXCEEDED ? (
      <GatedContentWrapper>{children}</GatedContentWrapper>
    ) : (
      children
    );

  return getPageContent(
    <AppProvider
      authTypeMetadata={authTypeMetadata}
      user={user}
      settings={combinedSettings}
      folded={folded}
      initialLocale={locale}
      initialBackgroundId={backgroundId}
    >
      <Suspense fallback={null}>
        <PostHogPageView />
      </Suspense>
      <div id={MODAL_ROOT_ID} className="h-screen w-screen">
        {content}
      </div>
      {appSettings.NEXT_PUBLIC_POSTHOG_KEY && <WebVitals />}
      {appSettings.NEXT_PUBLIC_ENABLE_STATS && <StatsOverlayLoader />}
    </AppProvider>
  );
}

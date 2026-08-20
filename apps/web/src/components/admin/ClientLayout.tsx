"use client";

import HttpErrorPage from "@/components/errorPages/HttpErrorPage";

import AdminSidebar from "@/sections/sidebar/AdminSidebar";
import { usePathname, useRouter } from "next/navigation";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { ApplicationStatus } from "@/interfaces/settings";
import Button from "@/refresh-components/buttons/Button";
import { cn } from "@/lib/utils";
import {
  ADMIN_PATHS,
  getAdminRouteConfigForPathname,
} from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { useUser } from "@/providers/UserProvider";

export interface ClientLayoutProps {
  children: React.ReactNode;
  enableEnterprise: boolean;
  enableCloud: boolean;
}

export const DISABLED_ADMIN_PATHS = [
  ADMIN_PATHS.DOCUMENTS,
  ADMIN_PATHS.DOCUMENT_SETS,
  ADMIN_PATHS.DOCUMENT_EXPLORER,
  ADMIN_PATHS.DOCUMENT_FEEDBACK,
  ADMIN_PATHS.CHAT_PREFERENCES,
  ADMIN_PATHS.IMAGE_GENERATION,
  ADMIN_PATHS.CODE_INTERPRETER,
  ADMIN_PATHS.SEARCH_SETTINGS,
  ADMIN_PATHS.API_KEYS,
];

// Pages using SettingsLayouts handle their own padding/centering.
const SETTINGS_LAYOUT_PREFIXES = [
  ADMIN_PATHS.INDEXING_STATUS,
  ADMIN_PATHS.ADD_CONNECTOR,
  ADMIN_PATHS.DOCUMENT_SETS,
  ADMIN_PATHS.DOCUMENT_EXPLORER,
  ADMIN_PATHS.DOCUMENT_FEEDBACK,
  ADMIN_PATHS.AGENTS,
  ADMIN_PATHS.SLACK_BOTS,
  ADMIN_PATHS.DISCORD_BOTS,
  ADMIN_PATHS.CHAT_PREFERENCES,
  ADMIN_PATHS.LLM_MODELS,
  ADMIN_PATHS.IMAGE_GENERATION,
  ADMIN_PATHS.WEB_SEARCH,
  ADMIN_PATHS.CODE_INTERPRETER,
  ADMIN_PATHS.SEARCH_SETTINGS,
  ADMIN_PATHS.DOCUMENT_PROCESSING,
  ADMIN_PATHS.MCP_ACTIONS,
  ADMIN_PATHS.OPENAPI_ACTIONS,
  ADMIN_PATHS.KNOWLEDGE_GRAPH,
  ADMIN_PATHS.USERS,
  ADMIN_PATHS.API_KEYS,
  ADMIN_PATHS.ROLES,
  ADMIN_PATHS.TOKEN_RATE_LIMITS,
  ADMIN_PATHS.BILLING,
  ADMIN_PATHS.INDEX_MIGRATION,
  ADMIN_PATHS.DEBUG,
  ADMIN_PATHS.SYSTEM_SETTINGS,
  ADMIN_PATHS.SYSTEM_INFO,
];

export function ClientLayout({
  children,
  enableEnterprise,
  enableCloud,
}: ClientLayoutProps) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  const pathname = usePathname();
  const router = useRouter();
  const settings = useSettingsContext();
  const { hasAllPermissions, isPermissionsLoading } = useUser();
  const routeConfig = getAdminRouteConfigForPathname(pathname);
  const requiredPermissions = routeConfig?.requiredPermissions ?? [];
  const hasRoutePermissions =
    requiredPermissions.length === 0 || hasAllPermissions(requiredPermissions);
  const canViewRoute = isPermissionsLoading || hasRoutePermissions;

  useEffect(() => {
    if (!isPermissionsLoading && !canViewRoute) {
      router.replace("/error/403");
    }
  }, [canViewRoute, isPermissionsLoading, router]);

  useEffect(() => {
    router.prefetch("/app");
  }, [router]);

  // Certain admin panels have their own custom sidebar.
  // For those pages, we skip rendering the default `AdminSidebar` and let those individual pages render their own.
  const hasCustomSidebar =
    pathname.startsWith("/admin/connectors") ||
    pathname.startsWith("/admin/embeddings");

  const hasOwnLayout = SETTINGS_LAYOUT_PREFIXES.some((prefix) =>
    pathname.startsWith(prefix)
  );

  const isRouteDisabled = DISABLED_ADMIN_PATHS.some(
    (disabledPath) =>
      pathname === disabledPath || pathname.startsWith(`${disabledPath}/`)
  );

  if (isRouteDisabled) {
    return <HttpErrorPage code={404} />;
  }

  if (!canViewRoute) {
    return null;
  }

  return (
    <div className="h-screen w-screen flex overflow-hidden">
      {settings.settings.application_status ===
        ApplicationStatus.PAYMENT_REMINDER && (
        <div className="fixed top-2 left-1/2 transform -translate-x-1/2 bg-amber-400 dark:bg-amber-500 text-gray-900 dark:text-gray-100 p-4 rounded-lg shadow-lg z-50 max-w-md text-center">
          <strong className="font-bold">{t("clientLayout.warning")}</strong>{" "}
          {t("clientLayout.trialWarning")}
          <div className="mt-2">
            <Button className="w-full" href="/admin/billing">
              {t("clientLayout.updateBilling")}
            </Button>
          </div>
        </div>
      )}

      {hasCustomSidebar ? (
        <div className="flex-1 min-w-0 min-h-0 overflow-y-auto">{children}</div>
      ) : (
        <>
          <AdminSidebar
            enableCloudSS={enableCloud}
            enableEnterpriseSS={enableEnterprise}
          />
          <div
            data-main-container
            className={cn(
              "flex flex-1 flex-col min-w-0 min-h-0 overflow-y-auto",
              !hasOwnLayout && "py-10 px-4 md:px-12"
            )}
          >
            {children}
          </div>
        </>
      )}
    </div>
  );
}

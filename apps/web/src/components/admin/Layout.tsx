import { redirect } from "next/navigation";
import type { Route } from "next";
import { requireAdminAuth } from "@/lib/auth/requireAuth";
import { ClientLayout } from "./ClientLayout";
import { AnnouncementBanner } from "../header/AnnouncementBanner";
import { appSettings } from "@/lib/settings";

export interface LayoutProps {
  children: React.ReactNode;
}

export default async function Layout({ children }: LayoutProps) {
  // Check authentication and admin role - data fetching is done client-side via SWR hooks
  const authResult = await requireAdminAuth();

  // If auth check returned a redirect, redirect immediately
  if (authResult.redirect) {
    return redirect(authResult.redirect as Route);
  }

  return (
    <ClientLayout
      enableEnterprise={
        appSettings.SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED
      }
      enableCloud={appSettings.NEXT_PUBLIC_CLOUD_ENABLED}
    >
      <AnnouncementBanner />
      {children}
    </ClientLayout>
  );
}

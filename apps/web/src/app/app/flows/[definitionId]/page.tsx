import { redirect } from "next/navigation";
import type { Route } from "next";
import FlowStudioPage from "@/refresh-pages/FlowStudioPage";
import { requireAdminAuth } from "@/lib/auth/requireAuth";

export default async function Page({
  params,
}: {
  params: Promise<{ definitionId: string }>;
}) {
  const authResult = await requireAdminAuth();
  if (authResult.redirect) {
    redirect(authResult.redirect as Route);
  }

  const { definitionId } = await params;
  return <FlowStudioPage definitionId={definitionId} />;
}

import AgentEditorPage from "@/refresh-pages/AgentEditorPage";
import * as AppLayouts from "@/layouts/app-layouts";
import { requireAdminAuth } from "@/lib/auth/requireAuth";
import { redirect } from "next/navigation";
import type { Route } from "next";

export default async function Page() {
  const authResult = await requireAdminAuth();
  if (authResult.redirect) {
    redirect(authResult.redirect as Route);
  }

  return (
    <AppLayouts.Root>
      <AgentEditorPage />
    </AppLayouts.Root>
  );
}

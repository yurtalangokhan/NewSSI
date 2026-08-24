import { notFound } from "next/navigation";
"use client";

import ChatPreferencesPage from "@/refresh-pages/admin/ChatPreferencesPage";

export default function Page() {
  notFound();

  return <ChatPreferencesPage />;
}

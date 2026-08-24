"use client";

import { notFound } from "next/navigation";
import ChatPreferencesPage from "@/refresh-pages/admin/ChatPreferencesPage";

export default function Page() {
  notFound();

  return <ChatPreferencesPage />;
}

"use client";

import { ChatPreferencesSettings } from "@/refresh-pages/SettingsPage";
import { useUser } from "@/providers/UserProvider";
import { ChatPreferencesSkeleton } from "@/refresh-components/skeletons/SettingsSkeletons";

export default function ChatPreferencesPage() {
  const { user } = useUser();

  if (!user) {
    return <ChatPreferencesSkeleton />;
  }

  return <ChatPreferencesSettings />;
}

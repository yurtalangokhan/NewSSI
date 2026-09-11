"use client";

import { GeneralSettings } from "@/refresh-pages/SettingsPage";
import { useUser } from "@/providers/UserProvider";
import { GeneralSettingsSkeleton } from "@/refresh-components/skeletons/SettingsSkeletons";

export default function GeneralSettingsPage() {
  const { user } = useUser();

  if (!user) {
    return <GeneralSettingsSkeleton />;
  }

  return <GeneralSettings />;
}

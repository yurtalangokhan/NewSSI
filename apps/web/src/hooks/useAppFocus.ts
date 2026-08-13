"use client";

// "AppFocus" is the current part of the main application which is active / focused on.
// Namely, if the URL is pointing towards a "chat", then a `{ type: "chat", id: "..." }` is returned.
//
// This is useful in determining what `SidebarTab` should be active, for example.

import { AppFocusValue, parseAppFocus } from "@/hooks/appNavigation";
import { usePathname, useSearchParams } from "next/navigation";

export type AppFocusType = AppFocusValue;

export class AppFocus {
  constructor(public value: AppFocusType) {}

  isAgent(): boolean {
    return typeof this.value === "object" && this.value.type === "agent";
  }

  isProject(): boolean {
    return typeof this.value === "object" && this.value.type === "project";
  }

  isChat(): boolean {
    return typeof this.value === "object" && this.value.type === "chat";
  }

  isSharedChat(): boolean {
    return this.value === "shared-chat";
  }

  isNewSession(): boolean {
    return this.value === "new-session";
  }

  isMoreAgents(): boolean {
    return this.value === "more-agents";
  }

  isUserSettings(): boolean {
    return this.value === "user-settings";
  }

  getId(): string | null {
    return typeof this.value === "object" ? this.value.id : null;
  }

  getType():
    | "agent"
    | "project"
    | "chat"
    | "shared-chat"
    | "new-session"
    | "more-agents"
    | "user-settings" {
    return typeof this.value === "object" ? this.value.type : this.value;
  }
}

export default function useAppFocus(): AppFocus {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return new AppFocus(parseAppFocus(pathname, searchParams));
}

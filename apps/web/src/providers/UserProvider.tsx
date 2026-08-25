"use client";

import React, {
  createContext,
  useContext,
  useCallback,
  useState,
  useEffect,
  useRef,
} from "react";
import { User, UserPersonalization, ThemePreference } from "@/lib/types";
import { getCurrentUser } from "@/lib/user";
import { usePostHog } from "posthog-js/react";
import { CombinedSettings } from "@/interfaces/settings";
import { SettingsContext } from "@/providers/SettingsProvider";
import { AuthTypeMetadata } from "@/lib/userSS";
import { updateUserPersonalization as persistPersonalization } from "@/lib/userSettings";
import { useTheme } from "next-themes";
import { isAdminFromPermissions } from "@/lib/auth/roles";
import {
  hasAnyPermission as hasAnyPermissionValue,
  hasAllPermissions as hasAllPermissionsValue,
  hasPermission as hasPermissionValue,
} from "@/lib/auth/permissions";
import { authenticatedFetch } from "@/lib/fetcher";

interface UserContextType {
  user: User | null;
  isAdmin: boolean;
  isCurator: boolean;
  permissions: string[];
  permissionsError: string | null;
  isPermissionsLoading: boolean;
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: readonly string[]) => boolean;
  hasAllPermissions: (permissions: readonly string[]) => boolean;
  refreshUser: () => Promise<void>;
  authTypeMetadata: AuthTypeMetadata;
  updateUserAutoScroll: (autoScroll: boolean) => Promise<void>;
  updateUserShortcuts: (enabled: boolean) => Promise<void>;
  updateUserPinnedAssistants: (pinnedIds: number[]) => Promise<boolean>;
  toggleAgentPinnedStatus: (
    currentPinnedAgentIDs: number[],
    agentId: number,
    isPinned: boolean
  ) => Promise<boolean>;
  updateUserTemperatureOverrideEnabled: (enabled: boolean) => Promise<void>;
  updateUserPersonalization: (
    personalization: UserPersonalization
  ) => Promise<void>;
  updateUserThemePreference: (
    themePreference: ThemePreference
  ) => Promise<void>;
  updateUserChatBackground: (chatBackground: string | null) => Promise<void>;
  updateUserDefaultModel: (
    defaultModel: string | null,
    defaultProviderId?: string | null
  ) => Promise<void>;
  updateUserDefaultAppMode: (mode: "CHAT" | "SEARCH") => Promise<void>;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export function UserProvider({
  authTypeMetadata,
  children,
  user,
  settings,
}: {
  authTypeMetadata: AuthTypeMetadata;
  children: React.ReactNode;
  user: User | null;
  settings: CombinedSettings;
}) {
  const updatedSettings = useContext(SettingsContext);
  const posthog = usePostHog();

  // For auto_scroll and temperature_override_enabled:
  // - If user has a preference set, use that
  // - Otherwise, use the workspace setting if available
  function mergeUserPreferences(
    currentUser: User | null,
    currentSettings: CombinedSettings | null
  ): User | null {
    if (!currentUser) return null;
    return {
      ...currentUser,
      preferences: {
        ...currentUser.preferences,
        auto_scroll:
          currentUser.preferences?.auto_scroll ??
          currentSettings?.settings?.auto_scroll ??
          false,
        temperature_override_enabled:
          currentUser.preferences?.temperature_override_enabled ??
          currentSettings?.settings?.temperature_override_enabled ??
          false,
      },
    };
  }

  const [upToDateUser, setUpToDateUser] = useState<User | null>(
    mergeUserPreferences(user, settings)
  );
  const [permissions, setPermissions] = useState<string[]>([]);
  const [permissionsError, setPermissionsError] = useState<string | null>(null);
  const [isPermissionsLoading, setIsPermissionsLoading] = useState(
    Boolean(user?.id)
  );

  useEffect(() => {
    setUpToDateUser(mergeUserPreferences(user, updatedSettings));
  }, [
    user,
    updatedSettings?.settings?.auto_scroll,
    updatedSettings?.settings?.temperature_override_enabled,
  ]);

  useEffect(() => {
    if (!posthog) return;

    if (user?.id) {
      const identifyData: Record<string, any> = {
        email: user.email,
      };
      if (user.team_name) {
        identifyData.team_name = user.team_name;
      }
      posthog.identify(user.id, identifyData);
    } else {
      posthog.reset();
    }
  }, [posthog, user]);

  const fetchUser = async () => {
    try {
      const currentUser = await getCurrentUser();
      setUpToDateUser(currentUser);
    } catch (error) {
      console.error("Error fetching current user:", error);
    }
  };

  const fetchPermissions = useCallback(async () => {
    if (!upToDateUser?.id) {
      setPermissions([]);
      setPermissionsError(null);
      setIsPermissionsLoading(false);
      return;
    }

    setIsPermissionsLoading(true);
    setPermissionsError(null);
    try {
      const response = await authenticatedFetch(
        "/api/user-service/users/me/permissions",
        { redirectOnAuthError: false }
      );
      if (!response.ok) {
        throw new Error("Failed to fetch permissions");
      }
      const payload = (await response.json()) as { permissions?: string[] };
      setPermissions(payload.permissions ?? []);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch permissions";
      setPermissions([]);
      setPermissionsError(message);
    } finally {
      setIsPermissionsLoading(false);
    }
  }, [upToDateUser?.id]);

  useEffect(() => {
    fetchPermissions();
  }, [fetchPermissions]);

  const hasPermission = useCallback(
    (permission: string) => hasPermissionValue(permissions, permission),
    [permissions]
  );

  const hasAnyPermission = useCallback(
    (requiredPermissions: readonly string[]) =>
      hasAnyPermissionValue(permissions, requiredPermissions),
    [permissions]
  );

  const hasAllPermissions = useCallback(
    (requiredPermissions: readonly string[]) =>
      hasAllPermissionsValue(permissions, requiredPermissions),
    [permissions]
  );

  // Sync user's theme preference from DB to next-themes on load
  const { setTheme, theme } = useTheme();
  const hasSyncedThemeRef = useRef(false);

  useEffect(() => {
    // Only sync once per session
    if (hasSyncedThemeRef.current) return;

    // Wait for next-themes to initialize
    if (!theme) return;

    // Wait for user data to load
    if (!upToDateUser?.id) return;

    // Only sync if user has a saved preference
    const savedTheme = upToDateUser?.preferences?.theme_preference;
    if (!savedTheme) return;

    // Sync DB theme to localStorage
    setTheme(savedTheme);
    hasSyncedThemeRef.current = true;
  }, [
    upToDateUser?.id,
    upToDateUser?.preferences?.theme_preference,
    theme,
    setTheme,
  ]);

  const updateUserTemperatureOverrideEnabled = async (enabled: boolean) => {
    try {
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              temperature_override_enabled: enabled,
            },
          };
        }
        return prevUser;
      });

      const response = await fetch(
        `/api/temperature-override-enabled?temperature_override_enabled=${enabled}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update user temperature override setting");
      }
    } catch (error) {
      console.error("Error updating user temperature override setting:", error);
      throw error;
    }
  };

  const updateUserShortcuts = async (enabled: boolean) => {
    try {
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              shortcut_enabled: enabled,
            },
          };
        }
        return prevUser;
      });

      const response = await fetch(
        `/api/shortcut-enabled?shortcut_enabled=${enabled}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update user shortcut setting");
      }
    } catch (error) {
      console.error("Error updating user shortcut setting:", error);
      throw error;
    }
  };

  const updateUserAutoScroll = async (autoScroll: boolean) => {
    try {
      const response = await fetch("/api/auto-scroll", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ auto_scroll: autoScroll }),
      });
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              auto_scroll: autoScroll,
            },
          };
        }
        return prevUser;
      });

      if (!response.ok) {
        throw new Error("Failed to update auto-scroll setting");
      }
    } catch (error) {
      console.error("Error updating auto-scroll setting:", error);
      throw error;
    }
  };

  const updateUserPersonalization = async (
    personalization: UserPersonalization
  ) => {
    try {
      setUpToDateUser((prevUser) => {
        if (!prevUser) {
          return prevUser;
        }

        return {
          ...prevUser,
          personalization,
        };
      });

      const response = await persistPersonalization(personalization);

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update personalization settings");
      }

      await refreshUser();
    } catch (error) {
      console.error("Error updating personalization settings:", error);
      throw error;
    }
  };

  const updateUserPinnedAssistants = async (pinnedIds: number[]) => {
    setUpToDateUser((prevUser) => {
      if (!prevUser) return prevUser;
      return {
        ...prevUser,
        preferences: {
          ...prevUser.preferences,
          pinned_assistants: pinnedIds,
        },
      };
    });

    try {
      const response = await fetch(`/api/user/pinned-assistants`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ordered_assistant_ids: pinnedIds,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to update pinned assistants");
      }

      await refreshUser();
      return true;
    } catch (error) {
      console.error("Error updating pinned assistants:", error);
      await refreshUser();
      return false;
    }
  };

  const toggleAgentPinnedStatus = async (
    currentPinnedAgentIDs: number[],
    agentId: number,
    isPinned: boolean
  ) => {
    const updatedPinnedAgentsIds = isPinned
      ? [...currentPinnedAgentIDs, agentId]
      : currentPinnedAgentIDs.filter((id) => id !== agentId);
    return updateUserPinnedAssistants(updatedPinnedAgentsIds);
  };

  const updateUserThemePreference = async (
    themePreference: ThemePreference
  ) => {
    try {
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              theme_preference: themePreference,
            },
          };
        }
        return prevUser;
      });

      const response = await fetch(`/api/user/theme-preference`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ theme_preference: themePreference }),
      });

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update theme preference");
      }
    } catch (error) {
      console.error("Error updating theme preference:", error);
      throw error;
    }
  };

  const updateUserChatBackground = async (chatBackground: string | null) => {
    try {
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              chat_background: chatBackground,
            },
          };
        }
        return prevUser;
      });

      const response = await fetch(`/api/user/chat-background`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ chat_background: chatBackground }),
      });

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update chat background");
      }
    } catch (error) {
      console.error("Error updating chat background:", error);
      throw error;
    }
  };

  const updateUserDefaultModel = async (
    defaultModel: string | null,
    defaultProviderId?: string | null
  ) => {
    try {
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              default_model: defaultModel,
              ...(defaultProviderId !== undefined && {
                default_provider_id: defaultProviderId,
              }),
            },
          };
        }
        return prevUser;
      });

      const response = await fetch(`/api/user/default-model`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          default_model: defaultModel,
          ...(defaultProviderId !== undefined && {
            default_provider_id: defaultProviderId,
          }),
        }),
      });

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update default model");
      }
    } catch (error) {
      console.error("Error updating default model:", error);
      throw error;
    }
  };

  const updateUserDefaultAppMode = async (mode: "CHAT" | "SEARCH") => {
    try {
      setUpToDateUser((prevUser) => {
        if (prevUser) {
          return {
            ...prevUser,
            preferences: {
              ...prevUser.preferences,
              default_app_mode: mode,
            },
          };
        }
        return prevUser;
      });

      const response = await fetch("/api/user/default-app-mode", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ default_app_mode: mode }),
      });

      if (!response.ok) {
        await refreshUser();
        throw new Error("Failed to update default app mode");
      }
    } catch (error) {
      console.error("Error updating default app mode:", error);
      throw error;
    }
  };

  const refreshUser = async () => {
    await fetchUser();
  };

  return (
    <UserContext.Provider
      value={{
        user: upToDateUser,
        refreshUser,
        authTypeMetadata,
        updateUserAutoScroll,
        updateUserShortcuts,
        updateUserTemperatureOverrideEnabled,
        updateUserPersonalization,
        updateUserThemePreference,
        updateUserChatBackground,
        updateUserDefaultModel,
        updateUserDefaultAppMode,
        updateUserPinnedAssistants,
        toggleAgentPinnedStatus,
        isAdmin: isAdminFromPermissions(permissions),
        isCurator: false,
        permissions,
        permissionsError,
        isPermissionsLoading,
        hasPermission,
        hasAnyPermission,
        hasAllPermissions,
      }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error("useUser must be used within a UserProvider");
  }
  return context;
}

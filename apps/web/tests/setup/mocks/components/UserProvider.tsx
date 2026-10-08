/**
 * Mock for @/components/user/UserProvider
 *
 * Why this mock exists:
 * The real UserProvider requires complex props (authTypeMetadata, settings, user)
 * that are not relevant for most component integration tests. This mock provides
 * a simple useUser() hook with safe default values.
 *
 * Usage:
 * Automatically applied via jest.config.js moduleNameMapper.
 * Any component that imports from "@/components/user/UserProvider" will get this mock.
 *
 * To customize user values in a specific test:
 * You would need to either:
 * 1. Pass props to the real UserProvider (requires disabling this mock for that test)
 * 2. Extend this mock to accept custom values via a setup function
 */
import React, { createContext, useContext } from "react";

interface UserContextType {
  user: any;
  isAdmin: boolean;
  isCurator: boolean;
  permissions: string[];
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: readonly string[]) => boolean;
  hasAllPermissions: (permissions: readonly string[]) => boolean;
  refreshUser: () => Promise<void>;
  isCloudSuperuser: boolean;
  updateUserAutoScroll: (autoScroll: boolean) => Promise<void>;
  updateUserShortcuts: (enabled: boolean) => Promise<void>;
  updateUserPinnedAssistants: (pinnedIds: number[]) => Promise<boolean>;
  toggleAgentPinnedStatus: (
    currentPinnedAgentIDs: number[],
    agentId: number,
    isPinned: boolean
  ) => Promise<boolean>;
  updateUserTemperatureOverrideEnabled: (enabled: boolean) => Promise<void>;
  updateUserPersonalization: (personalization: any) => Promise<void>;
}

const mockUserContext: UserContextType = {
  user: null,
  isAdmin: false,
  isCurator: false,
  // Unprivileged by default, matching isAdmin/isCurator above: a test that
  // needs a permission-gated affordance must opt into it explicitly rather
  // than inherit it from the shared mock.
  permissions: [],
  hasPermission: () => false,
  hasAnyPermission: () => false,
  hasAllPermissions: () => false,
  refreshUser: async () => {},
  isCloudSuperuser: false,
  updateUserAutoScroll: async () => {},
  updateUserShortcuts: async () => {},
  updateUserPinnedAssistants: async () => true,
  toggleAgentPinnedStatus: async () => true,
  updateUserTemperatureOverrideEnabled: async () => {},
  updateUserPersonalization: async () => {},
};

const UserContext = createContext<UserContextType | undefined>(mockUserContext);

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error("useUser must be used within a UserProvider");
  }
  return context;
}

export function UserProvider({ children }: { children: React.ReactNode }) {
  return (
    <UserContext.Provider value={mockUserContext}>
      {children}
    </UserContext.Provider>
  );
}

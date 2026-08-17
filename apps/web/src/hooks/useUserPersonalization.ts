"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { User, UserPersonalization } from "@/lib/types";

const DEFAULT_PERSONALIZATION: UserPersonalization = {
  name: "",
  role: "",
  long_term_memory_enabled: false,
  extract_memory: true,
  user_preferences: "",
};

function derivePersonalizationFromUser(user: User | null): UserPersonalization {
  const fallbackName =
    user?.personalization?.name?.trim() ||
    user?.full_name?.trim() ||
    [user?.first_name?.trim(), user?.last_name?.trim()]
      .filter(Boolean)
      .join(" ")
      .trim() ||
    user?.first_name?.trim() ||
    "";
  const fallbackRole = user?.personalization?.role?.trim() || "";

  return {
    name: fallbackName,
    role: fallbackRole,
    long_term_memory_enabled:
      user?.personalization?.long_term_memory_enabled ??
      DEFAULT_PERSONALIZATION.long_term_memory_enabled,
    extract_memory:
      user?.personalization?.extract_memory ??
      DEFAULT_PERSONALIZATION.extract_memory,
    user_preferences: user?.personalization?.user_preferences ?? "",
  };
}

interface UseUserPersonalizationOptions {
  onSuccess?: (personalization: UserPersonalization) => void;
  onError?: (error: unknown) => void;
}

/**
 * Hook for managing user personalization settings
 *
 * Handles user personalization data including name, role, and memories.
 * Provides state management and persistence for personalization fields with
 * optimistic updates and error handling.
 *
 * @param user - The current user object containing personalization data
 * @param persistPersonalization - Async function to persist personalization changes to the server
 * @param options - Optional callbacks for success and error handling
 * @param options.onSuccess - Callback invoked when personalization is successfully saved
 * @param options.onError - Callback invoked when personalization save fails
 * @returns Object containing personalization state and handler functions
 *
 * @example
 * ```tsx
 * import useUserPersonalization from "@/hooks/useUserPersonalization";
 * import { useUser } from "@/providers/UserProvider";
 *
 * function PersonalizationSettings() {
 *   const { user, updateUserPersonalization } = useUser();
 *   const {
 *     personalizationValues,
 *     updatePersonalizationField,
 *     toggleUseMemories,
 *     updateMemoryAtIndex,
 *     addMemory,
 *     handleSavePersonalization,
 *     isSavingPersonalization
 *   } = useUserPersonalization(user, updateUserPersonalization, {
 *     onSuccess: () => console.log("Saved!"),
 *     onError: () => console.log("Failed!")
 *   });
 *
 *   return (
 *     <div>
 *       <input
 *         value={personalizationValues.name}
 *         onChange={(e) => updatePersonalizationField("name", e.target.value)}
 *       />
 *       <button
 *         onClick={handleSavePersonalization}
 *         disabled={isSavingPersonalization}
 *       >
 *         Save
 *       </button>
 *     </div>
 *   );
 * }
 * ```
 *
 * @remarks
 * - Changes are optimistic - UI updates immediately before server persistence
 * - On error, state reverts to the last known good value from the user object
 * - Memories are automatically trimmed and filtered (empty strings removed) on save
 * - The hook synchronizes with user prop changes to stay in sync with external updates
 */
export default function useUserPersonalization(
  user: User | null,
  persistPersonalization: (
    personalization: UserPersonalization
  ) => Promise<void>,
  options?: UseUserPersonalizationOptions
) {
  const [personalizationValues, setPersonalizationValues] =
    useState<UserPersonalization>(() => derivePersonalizationFromUser(user));
  const [isSavingPersonalization, setIsSavingPersonalization] = useState(false);

  const onSuccess = options?.onSuccess;
  const onError = options?.onError;

  const basePersonalization = useMemo(
    () => derivePersonalizationFromUser(user),
    [user]
  );

  useEffect(() => {
    setPersonalizationValues(basePersonalization);
  }, [basePersonalization]);

  const updatePersonalizationField = useCallback(
    (field: "name" | "role", value: string) => {
      setPersonalizationValues((prev) => ({
        ...prev,
        [field]: value,
      }));
    },
    []
  );

  const toggleUseMemories = useCallback((useMemories: boolean) => {
    setPersonalizationValues((prev) => ({
      ...prev,
      long_term_memory_enabled: useMemories,
    }));
  }, []);

  const toggleLongTermMemory = useCallback((enabled: boolean) => {
    setPersonalizationValues((prev) => ({
      ...prev,
      long_term_memory_enabled: enabled,
    }));
  }, []);

  const toggleEnableMemoryTool = useCallback((enabled: boolean) => {
    setPersonalizationValues((prev) => ({
      ...prev,
      enable_memory_tool: enabled,
    }));
  }, []);

  const updateUserPreferences = useCallback((value: string) => {
    setPersonalizationValues((prev) => ({
      ...prev,
      user_preferences: value,
    }));
  }, []);

  const handleSavePersonalization = useCallback(
    async (overrides?: Partial<UserPersonalization>, silent?: boolean) => {
      setIsSavingPersonalization(true);

      const valuesToSave = { ...personalizationValues, ...overrides };

      try {
        await persistPersonalization(valuesToSave);
        setPersonalizationValues(valuesToSave);
        if (!silent) {
          onSuccess?.(valuesToSave);
        }
        return valuesToSave;
      } catch (error) {
        setPersonalizationValues(basePersonalization);
        if (!silent) {
          onError?.(error);
        }
        return null;
      } finally {
        setIsSavingPersonalization(false);
      }
    },
    [
      basePersonalization,
      onError,
      onSuccess,
      persistPersonalization,
      personalizationValues,
    ]
  );

  return {
    personalizationValues,
    basePersonalization,
    updatePersonalizationField,
    toggleUseMemories,
    toggleLongTermMemory,
    toggleEnableMemoryTool,
    updateUserPreferences,
    handleSavePersonalization,
    isSavingPersonalization,
  };
}

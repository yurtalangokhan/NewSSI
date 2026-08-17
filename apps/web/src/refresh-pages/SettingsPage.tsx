"use client";

import { useTranslation } from "react-i18next";
import { useRef, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import * as InputLayouts from "@/layouts/input-layouts";
import { Section } from "@/layouts/general-layouts";
import { Content } from "@opal/layouts";
import { SvgMinusCircle, SvgTrash } from "@opal/icons";
import Card from "@/refresh-components/cards/Card";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import Button from "@/refresh-components/buttons/Button";
import Switch from "@/refresh-components/inputs/Switch";
import { useUser } from "@/providers/UserProvider";
import { useTheme } from "next-themes";
import { MemoryItem, ThemePreference } from "@/lib/types";
import useUserPersonalization from "@/hooks/useUserPersonalization";
import { toast } from "@/hooks/useToast";
import LLMPopover from "@/refresh-components/popovers/LLMPopover";
import { deleteAllChatSessions } from "@/app/app/services/lib";
import { useLlmManager } from "@/lib/hooks";
import useChatSessions from "@/hooks/useChatSessions";
import { Button as OpalButton } from "@opal/components";
import Separator from "@/refresh-components/Separator";
import Text from "@/refresh-components/texts/Text";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import CharacterCount from "@/refresh-components/CharacterCount";
import { InputPrompt } from "@/app/app/interfaces";
import usePromptShortcuts from "@/hooks/usePromptShortcuts";
import ColorSwatch from "@/refresh-components/ColorSwatch";
import Memories from "@/sections/settings/Memories";
import useUserMemories from "@/hooks/useUserMemories";
import {
  CHAT_BACKGROUND_OPTIONS,
  CHAT_BACKGROUND_NONE,
} from "@/lib/constants/chatBackgrounds";
import { SvgCheck } from "@opal/icons";
import { cn } from "@/lib/utils";
import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
import { useSettingsContext } from "@/providers/SettingsProvider";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";

function GeneralSettings() {
  const { t } = useTranslation();

  const {
    user,
    updateUserPersonalization,
    updateUserThemePreference,
    updateUserChatBackground,
  } = useUser();
  const { theme, setTheme, systemTheme } = useTheme();
  const { refreshChatSessions } = useChatSessions();
  const router = useRouter();
  const pathname = usePathname();
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  // `theme` is `undefined` on the server and on the client's first render
  // pass, then flips synchronously to the stored value before hydration
  // paints. Gate on `mounted` so both passes agree, avoiding a hydration
  // mismatch on the select's value/placeholder state.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const {
    personalizationValues,
    basePersonalization,
    updatePersonalizationField,
    handleSavePersonalization,
  } = useUserPersonalization(user, updateUserPersonalization, {
    onSuccess: () =>
      toast.success(t("settings.general.toastPersonalizationUpdated")),
    onError: () =>
      toast.error(t("settings.general.toastPersonalizationFailed")),
  });

  // Which field (if any) currently has an in-flight save, so only that
  // field is locked instead of both.
  const [savingField, setSavingField] = useState<"name" | "role" | null>(
    null
  );

  // Track initial values to detect changes
  const initialNameRef = useRef(basePersonalization.name);
  const initialRoleRef = useRef(basePersonalization.role);

  // Update refs only when the underlying server-sourced value changes,
  // not on every local keystroke (personalizationValues changes as the
  // user types, which would otherwise make the onBlur diff check below
  // always see "no change" and never save).
  useEffect(() => {
    initialNameRef.current = basePersonalization.name;
    initialRoleRef.current = basePersonalization.role;
  }, [basePersonalization.name, basePersonalization.role]);

  const handleDeleteAllChats = useCallback(async () => {
    setIsDeleting(true);
    try {
      const response = await deleteAllChatSessions();
      if (response.ok) {
        toast.success(t("settings.general.toastChatsDeleted"));
        await refreshChatSessions();
        setShowDeleteConfirmation(false);
      } else {
        throw new Error("Failed to delete all chat sessions");
      }
    } catch (error) {
      toast.error(t("settings.general.toastDeleteFailed"));
    } finally {
      setIsDeleting(false);
    }
  }, [pathname, router, refreshChatSessions]);

  return (
    <>
      {showDeleteConfirmation && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("settings.general.deleteChatsModalTitle")}
          onClose={() => setShowDeleteConfirmation(false)}
          submit={
            <Button
              danger
              onClick={() => {
                void handleDeleteAllChats();
              }}
              disabled={isDeleting}
            >
              {isDeleting
                ? t("settings.general.deletingButton")
                : t("settings.general.deleteButton")}
            </Button>
          }
        >
          <Section gap={0.5} alignItems="start">
            <Text>{t("settings.general.deleteChatsConfirmation1")}</Text>
            <Text>{t("settings.general.deleteChatsConfirmation2")}</Text>
          </Section>
        </ConfirmationModalLayout>
      )}

      <Section gap={2}>
        <Section gap={0.75}>
          <Content
            title={t("settings.general.profileTitle")}
            sizePreset="main-content"
            variant="section"
            widthVariant="full"
          />
          <Card>
            <InputLayouts.Horizontal
              title={t("settings.general.fullNameLabel")}
              description={t("settings.general.fullNameDescription")}
              center
            >
              <InputTypeIn
                placeholder={t("settings.general.fullNamePlaceholder")}
                value={personalizationValues.name}
                className={
                  savingField === "name"
                    ? "opacity-60 pointer-events-none"
                    : undefined
                }
                onChange={(e) =>
                  updatePersonalizationField("name", e.target.value)
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.currentTarget.blur();
                  }
                }}
                onBlur={async () => {
                  // Only save if the value has changed
                  if (personalizationValues.name !== initialNameRef.current) {
                    setSavingField("name");
                    await handleSavePersonalization();
                    initialNameRef.current = personalizationValues.name;
                    setSavingField(null);
                  }
                }}
              />
            </InputLayouts.Horizontal>
            <InputLayouts.Horizontal
              title={t("settings.general.workRoleLabel")}
              description={t("settings.general.workRoleDescription")}
              center
            >
              <InputTypeIn
                placeholder={t("settings.general.workRolePlaceholder")}
                value={personalizationValues.role}
                className={
                  savingField === "role"
                    ? "opacity-60 pointer-events-none"
                    : undefined
                }
                onChange={(e) =>
                  updatePersonalizationField("role", e.target.value)
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.currentTarget.blur();
                  }
                }}
                onBlur={async () => {
                  // Only save if the value has changed
                  if (personalizationValues.role !== initialRoleRef.current) {
                    setSavingField("role");
                    await handleSavePersonalization();
                    initialRoleRef.current = personalizationValues.role;
                    setSavingField(null);
                  }
                }}
              />
            </InputLayouts.Horizontal>
          </Card>
        </Section>

        <Section gap={0.75}>
          <Content
            title={t("settings.general.appearanceTitle")}
            sizePreset="main-content"
            variant="section"
            widthVariant="full"
          />
          <Card>
            <InputLayouts.Horizontal
              title={t("settings.general.colorModeLabel")}
              description={t("settings.general.colorModeDescription")}
              center
            >
              <InputSelect
                value={mounted ? theme : undefined}
                onValueChange={(value) => {
                  setTheme(value);
                  updateUserThemePreference(value as ThemePreference);
                }}
              >
                <InputSelect.Trigger />
                <InputSelect.Content>
                  <InputSelect.Item
                    value={ThemePreference.SYSTEM}
                    icon={() => (
                      <ColorSwatch
                        light={systemTheme === "light"}
                        dark={systemTheme === "dark"}
                      />
                    )}
                    description={
                      systemTheme
                        ? systemTheme.charAt(0).toUpperCase() +
                          systemTheme.slice(1)
                        : undefined
                    }
                  >
                    {t("settings.general.colorModeAuto")}
                  </InputSelect.Item>
                  <InputSelect.Separator />
                  <InputSelect.Item
                    value={ThemePreference.LIGHT}
                    icon={() => <ColorSwatch light />}
                  >
                    {t("settings.general.colorModeLight")}
                  </InputSelect.Item>
                  <InputSelect.Item
                    value={ThemePreference.DARK}
                    icon={() => <ColorSwatch dark />}
                  >
                    {t("settings.general.colorModeDark")}
                  </InputSelect.Item>
                </InputSelect.Content>
              </InputSelect>
            </InputLayouts.Horizontal>
            <InputLayouts.Vertical
              title={t("settings.general.chatBackgroundLabel")}
            >
              <div className="flex flex-wrap gap-2">
                {CHAT_BACKGROUND_OPTIONS.map((bg) => {
                  const currentBackgroundId =
                    user?.preferences?.chat_background ?? "none";
                  const isSelected = currentBackgroundId === bg.id;
                  const isNone = bg.src === CHAT_BACKGROUND_NONE;

                  return (
                    <button
                      key={bg.id}
                      onClick={() => {
                        updateUserChatBackground(
                          bg.id === CHAT_BACKGROUND_NONE ? null : bg.id
                        );
                        if (bg.id !== CHAT_BACKGROUND_NONE) {
                          const matchingTheme = bg.isDarkBackground
                            ? ThemePreference.DARK
                            : ThemePreference.LIGHT;
                          setTheme(matchingTheme);
                          updateUserThemePreference(matchingTheme);
                        }
                      }}
                      className="relative overflow-hidden rounded-lg transition-all w-[90px] h-[68px] cursor-pointer border-none p-0 bg-transparent group"
                      title={bg.label}
                      aria-label={`${bg.label} background${
                        isSelected ? " (selected)" : ""
                      }`}
                    >
                      {isNone ? (
                        <div className="absolute inset-0 bg-background flex items-center justify-center">
                          <span className="text-xs text-text-02">
                            {t("settings.general.colorModeNone")}
                          </span>
                        </div>
                      ) : (
                        <div
                          className="absolute inset-0 bg-cover bg-center transition-transform duration-300 group-hover:scale-105"
                          style={{ backgroundImage: `url(${bg.thumbnail})` }}
                        />
                      )}
                      <div
                        className={cn(
                          "absolute inset-0 transition-all rounded-lg",
                          isSelected
                            ? "ring-2 ring-inset ring-theme-primary-05"
                            : "ring-1 ring-inset ring-border-02 group-hover:ring-border-03"
                        )}
                      />
                      {isSelected && (
                        <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-theme-primary-05 flex items-center justify-center">
                          <SvgCheck className="w-2.5 h-2.5 stroke-text-inverted-05" />
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </InputLayouts.Vertical>
          </Card>
        </Section>

        <Separator noPadding />

        <Section gap={0.75}>
          <Content
            title={t("settings.general.dangerZoneTitle")}
            sizePreset="main-content"
            variant="section"
            widthVariant="full"
          />
          <Card>
            <InputLayouts.Horizontal
              title={t("settings.general.deleteChatsModalTitle")}
              description={t("settings.general.deleteChatsModalDescription")}
              center
            >
              <Button
                danger
                secondary
                onClick={() => setShowDeleteConfirmation(true)}
                leftIcon={SvgTrash}
                transient={showDeleteConfirmation}
              >
                {t("settings.general.deleteAllChatsButton")}
              </Button>
            </InputLayouts.Horizontal>
          </Card>
        </Section>
      </Section>
    </>
  );
}

interface LocalShortcut extends InputPrompt {
  isNew: boolean;
}

function PromptShortcuts() {
  const { t } = useTranslation();
  const { promptShortcuts, isLoading, error, refresh } = usePromptShortcuts();
  const [shortcuts, setShortcuts] = useState<LocalShortcut[]>([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  // Initialize shortcuts when input prompts are loaded
  useEffect(() => {
    if (isLoading || error) return;

    // Convert InputPrompt[] to LocalShortcut[] with isNew: false for existing items
    // Sort by id to maintain stable ordering when editing
    const existingShortcuts: LocalShortcut[] = promptShortcuts
      .map((shortcut) => ({
        ...shortcut,
        isNew: false,
      }))
      .sort((a, b) => a.id - b.id);

    // Always ensure there's at least one empty row
    setShortcuts([
      ...existingShortcuts,
      {
        id: Date.now(),
        prompt: "",
        content: "",
        active: true,
        is_public: false,
        isNew: true,
      },
    ]);
    setIsInitialLoad(false);
  }, [promptShortcuts, isLoading, error]);

  // Show error popup if fetch fails
  useEffect(() => {
    if (!error) return;
    toast.error(t("settings.chatPreferences.toastShortcutLoadFailed"));
  }, [error]);

  const handleUpdateShortcut = useCallback(
    (index: number, field: "prompt" | "content", value: string) => {
      setShortcuts((prev) => {
        const next = prev.map((shortcut, i) =>
          i === index ? { ...shortcut, [field]: value } : shortcut
        );

        const isEmptyNew = (s: LocalShortcut) =>
          s.isNew && !s.prompt.trim() && !s.content.trim();

        const emptyCount = next.filter(isEmptyNew).length;

        if (emptyCount === 0) {
          return [
            ...next,
            {
              id: Date.now(),
              prompt: "",
              content: "",
              active: true,
              is_public: false,
              isNew: true,
            },
          ];
        }

        if (emptyCount > 1) {
          const userRow = next[index];
          const userRowEmpty = userRow !== undefined && isEmptyNew(userRow);
          let keepIndex = -1;
          if (userRowEmpty) {
            keepIndex = index;
          } else {
            for (let i = next.length - 1; i >= 0; i--) {
              const row = next[i];
              if (row !== undefined && isEmptyNew(row)) {
                keepIndex = i;
                break;
              }
            }
          }
          return next.filter((s, i) => !isEmptyNew(s) || i === keepIndex);
        }

        return next;
      });
    },
    []
  );

  const handleRemoveShortcut = useCallback(
    async (index: number) => {
      const shortcut = shortcuts[index];
      if (!shortcut) return;

      // If it's a new shortcut, just remove from state
      if (shortcut.isNew) {
        setShortcuts((prev) => prev.filter((_, i) => i !== index));
        return;
      }

      // Otherwise, delete from backend
      try {
        const response = await fetch(`/api/input_prompt/${shortcut.id}`, {
          method: "DELETE",
        });

        if (response.ok) {
          setShortcuts((prev) => prev.filter((_, i) => i !== index));
          await refresh();
          toast.success(t("settings.chatPreferences.toastShortcutDeleted"));
        } else {
          throw new Error("Failed to delete shortcut");
        }
      } catch (error) {
        toast.error(t("settings.chatPreferences.toastShortcutDeleteFailed"));
      }
    },
    [shortcuts, refresh]
  );

  const handleSaveShortcut = useCallback(
    async (index: number) => {
      const shortcut = shortcuts[index];
      if (!shortcut || !shortcut.prompt.trim() || !shortcut.content.trim()) {
        toast.error(t("settings.chatPreferences.toastShortcutRequired"));
        return;
      }

      // If existing shortcut and no fields changed, do not save
      if (!shortcut.isNew) {
        const original = promptShortcuts.find((p) => p.id === shortcut.id);
        if (
          original &&
          original.prompt === shortcut.prompt &&
          original.content === shortcut.content
        ) {
          return;
        }
      }

      try {
        if (shortcut.isNew) {
          // Create new shortcut
          const response = await fetch("/api/input_prompt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              prompt: shortcut.prompt,
              content: shortcut.content,
              active: true,
              is_public: false,
            }),
          });

          if (response.ok) {
            await refresh();
            toast.success(t("settings.chatPreferences.toastShortcutCreated"));
          } else {
            throw new Error("Failed to create shortcut");
          }
        } else {
          // Update existing shortcut
          const response = await fetch(`/api/input_prompt/${shortcut.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              prompt: shortcut.prompt,
              content: shortcut.content,
              active: true,
              is_public: false,
            }),
          });

          if (response.ok) {
            await refresh();
            toast.success(t("settings.chatPreferences.toastShortcutUpdated"));
          } else {
            throw new Error("Failed to update shortcut");
          }
        }
      } catch (error) {
        toast.error(t("settings.chatPreferences.toastShortcutSaveFailed"));
      }
    },
    [shortcuts, promptShortcuts, refresh, t]
  );

  const handleBlurShortcut = useCallback(
    async (index: number) => {
      const shortcut = shortcuts[index];
      if (!shortcut) return;

      const hasPrompt = shortcut.prompt.trim();
      const hasContent = shortcut.content.trim();

      // Both fields are filled - save/update the shortcut
      if (hasPrompt && hasContent) {
        await handleSaveShortcut(index);
      }
      // For existing shortcuts with incomplete fields, error state will be shown in UI
      // User must use the delete button to remove them
    },
    [shortcuts, handleSaveShortcut]
  );

  return (
    <>
      {shortcuts.length > 0 && (
        <Section gap={0.75}>
          {shortcuts.map((shortcut, index) => {
            const isEmpty = !shortcut.prompt.trim() && !shortcut.content.trim();
            const isExisting = !shortcut.isNew;
            const hasPrompt = shortcut.prompt.trim();
            const hasContent = shortcut.content.trim();

            // Show error for existing shortcuts with incomplete fields
            // (either one field empty or both fields empty)
            const showPromptError = isExisting && !hasPrompt;
            const showContentError = isExisting && !hasContent;

            return (
              <div
                key={shortcut.id}
                className="w-full grid grid-cols-[1fr_min-content] gap-x-1 gap-y-1"
              >
                <InputTypeIn
                  prefixText="/"
                  placeholder={t(
                    "settings.chatPreferences.shortcutPlaceholder"
                  )}
                  value={shortcut.prompt}
                  onChange={(e) =>
                    handleUpdateShortcut(index, "prompt", e.target.value)
                  }
                  onBlur={
                    shortcut.is_public
                      ? undefined
                      : () => void handleBlurShortcut(index)
                  }
                  variant={
                    shortcut.is_public
                      ? "readOnly"
                      : showPromptError
                        ? "error"
                        : undefined
                  }
                />
                <Section>
                  <OpalButton
                    icon={SvgMinusCircle}
                    onClick={() => void handleRemoveShortcut(index)}
                    prominence="tertiary"
                    disabled={(shortcut.isNew && isEmpty) || shortcut.is_public}
                    aria-label={t(
                      "settings.chatPreferences.removeShortcutAriaLabel"
                    )}
                    tooltip={
                      shortcut.is_public
                        ? t(
                            "settings.chatPreferences.cannotDeletePublicTooltip"
                          )
                        : undefined
                    }
                  />
                </Section>
                <InputTextArea
                  placeholder={t(
                    "settings.chatPreferences.expansionPlaceholder"
                  )}
                  value={shortcut.content}
                  onChange={(e) =>
                    handleUpdateShortcut(index, "content", e.target.value)
                  }
                  onBlur={
                    shortcut.is_public
                      ? undefined
                      : () => void handleBlurShortcut(index)
                  }
                  variant={
                    shortcut.is_public
                      ? "readOnly"
                      : showContentError
                        ? "error"
                        : undefined
                  }
                  rows={3}
                />
                <div />
              </div>
            );
          })}
        </Section>
      )}
    </>
  );
}

function ChatPreferencesSettings() {
  const { t } = useTranslation();
  const {
    user,
    updateUserPersonalization,
    updateUserAutoScroll,
    updateUserShortcuts,
    updateUserDefaultModel,
    updateUserDefaultAppMode,
  } = useUser();
  const isPaidEnterpriseFeaturesEnabled = usePaidEnterpriseFeaturesEnabled();
  const settings = useSettingsContext();
  const { isSearchModeAvailable: searchUiEnabled } = settings;
  const llmManager = useLlmManager();

  const {
    personalizationValues,
    toggleUseMemories,
    toggleEnableMemoryTool,
    updateUserPreferences,
    handleSavePersonalization,
  } = useUserPersonalization(user, updateUserPersonalization, {
    onSuccess: () =>
      toast.success(t("settings.chatPreferences.toastPreferencesSaved")),
    onError: () =>
      toast.error(t("settings.chatPreferences.toastPreferencesFailed")),
  });

  const {
    memories,
    isLoading: isLoadingMemories,
    createMemory,
    updateMemory,
    deleteMemory,
    deleteAllMemories,
  } = useUserMemories({
    onError: () =>
      toast.error(t("settings.chatPreferences.toastPreferencesFailed")),
  });

  // Wrapper to save memories and return success/failure
  const handleSaveMemories = useCallback(
    async (
      newMemories: import("@/lib/types").MemoryItem[]
    ): Promise<boolean> => {
      try {
        // Sync: create new (empty dbId) and update existing
        for (const mem of newMemories) {
          if (!mem.id) {
            await createMemory(mem.content);
          }
        }
        return true;
      } catch {
        return false;
      }
    },
    [createMemory]
  );

  return (
    <Section gap={2}>
      <Section gap={0.75}>
        <Content
          title={t("settings.chatPreferences.chatsTitle")}
          sizePreset="main-content"
          variant="section"
          widthVariant="full"
        />
        <Card>
          <InputLayouts.Horizontal
            title={t("settings.chatPreferences.defaultModelLabel")}
            description={t("settings.chatPreferences.defaultModelDescription")}
          >
            <LLMPopover
              llmManager={llmManager}
              onSelect={(selected) => {
                void updateUserDefaultModel(selected);
              }}
            />
          </InputLayouts.Horizontal>

          <InputLayouts.Horizontal
            title={t("settings.chatPreferences.autoScrollLabel")}
            description={t("settings.chatPreferences.autoScrollDescription")}
          >
            <Switch
              checked={user?.preferences.auto_scroll}
              onCheckedChange={(checked) => {
                updateUserAutoScroll(checked);
              }}
            />
          </InputLayouts.Horizontal>

          {isPaidEnterpriseFeaturesEnabled && (
            <SimpleTooltip
              tooltip={
                searchUiEnabled
                  ? undefined
                  : t("settings.chatPreferences.defaultAppModeDisabledTooltip")
              }
              side="top"
            >
              <InputLayouts.Horizontal
                title={t("settings.chatPreferences.defaultAppModeLabel")}
                description={t(
                  "settings.chatPreferences.defaultAppModeDescription"
                )}
                center
                disabled={!searchUiEnabled}
              >
                <InputSelect
                  value={user?.preferences.default_app_mode ?? "CHAT"}
                  onValueChange={(value) => {
                    void updateUserDefaultAppMode(value as "CHAT" | "SEARCH");
                  }}
                  disabled={!searchUiEnabled}
                >
                  <InputSelect.Trigger />
                  <InputSelect.Content>
                    <InputSelect.Item value="CHAT">
                      {t("settings.chatPreferences.chatModeOption")}
                    </InputSelect.Item>
                    <InputSelect.Item value="SEARCH">
                      {t("settings.chatPreferences.searchModeOption")}
                    </InputSelect.Item>
                  </InputSelect.Content>
                </InputSelect>
              </InputLayouts.Horizontal>
            </SimpleTooltip>
          )}
        </Card>
      </Section>

      <Section gap={0.75}>
        <InputLayouts.Vertical
          title={t("settings.chatPreferences.personalPreferencesTitle")}
          description={t(
            "settings.chatPreferences.personalPreferencesDescription"
          )}
        >
          <InputTextArea
            placeholder={t(
              "settings.chatPreferences.personalPreferencesPlaceholder"
            )}
            value={personalizationValues.user_preferences}
            onChange={(e) => updateUserPreferences(e.target.value)}
            onBlur={() => void handleSavePersonalization()}
            rows={4}
            maxRows={10}
            autoResize
            maxLength={500}
          />
          <CharacterCount
            value={personalizationValues.user_preferences || ""}
            limit={500}
          />
        </InputLayouts.Vertical>
        <Content
          title={t("settings.chatPreferences.memoryTitle")}
          sizePreset="main-content"
          variant="section"
          widthVariant="full"
        />
        <Card>
          <InputLayouts.Horizontal
            title={t("settings.chatPreferences.referenceMemoriesLabel")}
            description={t(
              "settings.chatPreferences.referenceMemoriesDescription"
            )}
          >
            <Switch
              checked={personalizationValues.long_term_memory_enabled}
              onCheckedChange={(checked) => {
                void handleSavePersonalization({
                  long_term_memory_enabled: checked,
                });
              }}
            />
          </InputLayouts.Horizontal>
          <InputLayouts.Horizontal
            title={t("settings.chatPreferences.updateMemoriesLabel")}
            description={t(
              "settings.chatPreferences.updateMemoriesDescription"
            )}
          >
            <Switch
              checked={personalizationValues.extract_memory}
              onCheckedChange={(checked) => {
                void handleSavePersonalization({
                  extract_memory: checked,
                });
              }}
            />
          </InputLayouts.Horizontal>
          {(personalizationValues.long_term_memory_enabled ||
            personalizationValues.extract_memory ||
            memories.length > 0) && (
            <Memories
              memories={memories}
              onSaveMemories={handleSaveMemories}
              onDeleteMemory={deleteMemory}
            />
          )}
        </Card>
      </Section>

      <Section gap={0.75}>
        <Content
          title={t("settings.chatPreferences.promptShortcutsTitle")}
          sizePreset="main-content"
          variant="section"
          widthVariant="full"
        />
        <Card>
          <InputLayouts.Horizontal
            title={t("settings.chatPreferences.useShortcutsLabel")}
            description={t("settings.chatPreferences.useShortcutsDescription")}
          >
            <Switch
              checked={user?.preferences?.shortcut_enabled}
              onCheckedChange={(checked) => {
                updateUserShortcuts(checked);
              }}
            />
          </InputLayouts.Horizontal>

          {user?.preferences?.shortcut_enabled && <PromptShortcuts />}
        </Card>
      </Section>
    </Section>
  );
}

export { GeneralSettings, ChatPreferencesSettings };

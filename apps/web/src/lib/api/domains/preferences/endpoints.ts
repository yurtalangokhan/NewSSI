export const preferencesEndpoints = {
  updatePersonalizationProfile: {
    method: "PATCH",
    browserPath: "/api/user/personalization",
    backend: { service: "user", path: "/api/v1/users/me" },
  },
  updatePersonalizationSettings: {
    method: "PATCH",
    browserPath: "/api/user/personalization",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  getPinnedAssistants: {
    method: "GET",
    browserPath: "/api/user/pinned-assistants",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  updatePinnedAssistants: {
    method: "PATCH",
    browserPath: "/api/user/pinned-assistants",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  updateShortcutEnabled: (enabled?: boolean) =>
    ({
      method: "PATCH",
      browserPath: `/api/shortcut-enabled${
        enabled === undefined ? "" : `?shortcut_enabled=${enabled}`
      }`,
      backend: { service: "user", path: "/api/v1/users/me/settings/" },
    }) as const,
  getInputPrompts: {
    method: "GET",
    browserPath: "/api/input_prompt",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  createInputPrompt: {
    method: "POST",
    browserPath: "/api/input_prompt",
    backend: {
      service: "user",
      path: "/api/v1/users/me/settings/prompt-shortcuts",
    },
  },
  deleteInputPrompt: (id: string | number) =>
    ({
      method: "DELETE",
      browserPath: `/api/input_prompt/${id}`,
      backend: {
        service: "user",
        path: `/api/v1/users/me/settings/prompt-shortcuts/${id}`,
      },
    }) as const,
  updateInputPrompt: (id: string | number) =>
    ({
      method: "PATCH",
      browserPath: `/api/input_prompt/${id}`,
      backend: {
        service: "user",
        path: `/api/v1/users/me/settings/prompt-shortcuts/${id}`,
      },
    }) as const,
  listMemories: {
    method: "GET",
    browserPath: "/api/user-service/users/me/memories",
    backend: { service: "user", path: "/api/v1/users/me/memories/" },
  },
  createMemory: {
    method: "POST",
    browserPath: "/api/user-service/users/me/memories",
    backend: { service: "user", path: "/api/v1/users/me/memories/" },
  },
  deleteAllMemories: {
    method: "DELETE",
    browserPath: "/api/user-service/users/me/memories",
    backend: { service: "user", path: "/api/v1/users/me/memories/" },
  },
  updateMemory: (id: string) =>
    ({
      method: "PATCH",
      browserPath: `/api/user-service/users/me/memories/${id}`,
      backend: { service: "user", path: `/api/v1/users/me/memories/${id}` },
    }) as const,
  deleteMemory: (id: string) =>
    ({
      method: "DELETE",
      browserPath: `/api/user-service/users/me/memories/${id}`,
      backend: { service: "user", path: `/api/v1/users/me/memories/${id}` },
    }) as const,
  assistantPreferences: { browserPath: "/api/user/assistant/preferences" },
  getAssistantPreferences: (): { browserPath: string } => {
    return {
      browserPath: preferencesEndpoints.assistantPreferences.browserPath,
    };
  },
  agentPreferences: (agentId: number): { browserPath: string } => {
    return {
      browserPath: `/api/user/assistant/${encodeURIComponent(
        String(agentId)
      )}/preferences`,
    };
  },
  themePreference: {
    method: "PATCH",
    browserPath: "/api/user/theme-preference",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  chatBackground: {
    method: "PATCH",
    browserPath: "/api/user/chat-background",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  defaultModel: {
    method: "PATCH",
    browserPath: "/api/user/default-model",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  defaultAppMode: {
    method: "PATCH",
    browserPath: "/api/user/default-app-mode",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  memoriesPage: (page: number, pageSize: number): { browserPath: string } => {
    return {
      browserPath: `${preferencesEndpoints.listMemories.browserPath}?page=${page}&page_size=${pageSize}`,
    };
  },
  temperatureOverride: (enabled: boolean): { browserPath: string } => {
    return {
      browserPath: `/api/temperature-override-enabled?temperature_override_enabled=${enabled}`,
    };
  },
  autoScroll: {
    method: "PATCH",
    browserPath: "/api/auto-scroll",
    backend: { service: "user", path: "/api/v1/users/me/settings/" },
  },
  updateDefaultAssistantTools: { browserPath: "/api/admin/default-assistant" },
  updateAdminChatSettings: { browserPath: "/api/admin/settings" },
  defaultAssistantConfiguration: {
    browserPath: "/api/admin/default-assistant/configuration",
  },
} as const;

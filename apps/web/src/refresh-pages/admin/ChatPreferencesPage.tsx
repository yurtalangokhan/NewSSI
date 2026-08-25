"use client";

import React, { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Formik, Form, useFormikContext } from "formik";
import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { getErrorMsg } from "@/lib/fetchUtils";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import * as InputLayouts from "@/layouts/input-layouts";
import { Section } from "@/layouts/general-layouts";
import Card from "@/refresh-components/cards/Card";
import Separator from "@/refresh-components/Separator";
import SimpleCollapsible from "@/refresh-components/SimpleCollapsible";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import SwitchField from "@/refresh-components/form/SwitchField";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import InputSelectField from "@/refresh-components/form/InputSelectField";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import {
  SvgAddLines,
  SvgActions,
  SvgExpand,
  SvgFold,
  SvgExternalLink,
} from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { Content } from "@opal/layouts";
import { useSettingsContext } from "@/providers/SettingsProvider";
import useCCPairs from "@/hooks/useCCPairs";
import { getSourceMetadata } from "@/lib/sources";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import { Settings } from "@/interfaces/settings";
import { toast } from "@/hooks/useToast";
import { useAvailableTools } from "@/hooks/useAvailableTools";
import {
  SEARCH_TOOL_ID,
  WEB_SEARCH_TOOL_ID,
} from "@/app/app/components/tools/constants";
import { Button } from "@opal/components";
import Modal from "@/refresh-components/Modal";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import Switch from "@/refresh-components/inputs/Switch";
import useMcpServersForAgentEditor from "@/hooks/useMcpServersForAgentEditor";
import useOpenApiTools from "@/hooks/useOpenApiTools";
import * as ExpandableCard from "@/layouts/expandable-card-layouts";
import * as ActionsLayouts from "@/layouts/actions-layouts";
import { getActionIcon } from "@/lib/tools/mcpUtils";
import Disabled from "@/refresh-components/Disabled";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import useFilter from "@/hooks/useFilter";
import { MCPServer } from "@/lib/tools/interfaces";
import type { IconProps } from "@opal/types";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.CHAT_PREFERENCES]!;

interface DefaultAgentConfiguration {
  tool_ids: number[];
  system_prompt: string | null;
  default_system_prompt: string;
}

interface ChatPreferencesFormValues {
  // Features
  search_ui_enabled: boolean;
  deep_research_enabled: boolean;
  auto_scroll: boolean;

  // Team context
  company_name: string;
  company_description: string;

  // Advanced
  maximum_chat_retention_days: string;
  anonymous_user_enabled: boolean;
  disable_default_assistant: boolean;
}

interface MCPServerCardTool {
  id: number;
  icon: React.FunctionComponent<IconProps>;
  name: string;
  description: string;
}

interface MCPServerCardProps {
  server: MCPServer;
  tools: MCPServerCardTool[];
  isToolEnabled: (toolDbId: number) => boolean;
  onToggleTool: (toolDbId: number, enabled: boolean) => void;
  onToggleTools: (toolDbIds: number[], enabled: boolean) => void;
}

function MCPServerCard({
  server,
  tools,
  isToolEnabled,
  onToggleTool,
  onToggleTools,
}: MCPServerCardProps) {
  const { t } = useTranslation();
  const [isFolded, setIsFolded] = useState(true);
  const {
    query,
    setQuery,
    filtered: filteredTools,
  } = useFilter(tools, (tool) => `${tool.name} ${tool.description}`);

  const allToolIds = tools.map((t) => t.id);
  const serverEnabled =
    tools.length > 0 && tools.some((t) => isToolEnabled(t.id));

  return (
    <ExpandableCard.Root isFolded={isFolded} onFoldedChange={setIsFolded}>
      <ActionsLayouts.Header
        title={server.name}
        description={server.description}
        icon={getActionIcon(server.server_url, server.name)}
        rightChildren={
          <Switch
            checked={serverEnabled}
            onCheckedChange={(checked) => onToggleTools(allToolIds, checked)}
          />
        }
      >
        {tools.length > 0 && (
          <Section flexDirection="row" gap={0.5}>
            <InputTypeIn
              placeholder={t("agentEditor.searchToolsPlaceholder")}
              variant="internal"
              leftSearchIcon
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button
              rightIcon={isFolded ? SvgExpand : SvgFold}
              onClick={() => setIsFolded((prev) => !prev)}
              prominence="internal"
              size="lg"
            >
              {isFolded
                ? t("agentEditor.expandButton")
                : t("agentEditor.foldButton")}
            </Button>
          </Section>
        )}
      </ActionsLayouts.Header>
      {tools.length > 0 && filteredTools.length > 0 && (
        <ActionsLayouts.Content>
          <div className="flex flex-col gap-2">
            {filteredTools.map((tool) => (
              <ActionsLayouts.Tool
                key={tool.id}
                title={tool.name}
                description={tool.description}
                icon={tool.icon}
                rightChildren={
                  <Switch
                    checked={isToolEnabled(tool.id)}
                    onCheckedChange={(checked) =>
                      onToggleTool(tool.id, checked)
                    }
                  />
                }
              />
            ))}
          </div>
        </ActionsLayouts.Content>
      )}
    </ExpandableCard.Root>
  );
}

/**
 * Inner form component that uses useFormikContext to access values
 * and create save handlers for settings fields.
 */
function ChatPreferencesForm() {
  const { t } = useTranslation();
  const router = useRouter();
  const settings = useSettingsContext();
  const { values } = useFormikContext<ChatPreferencesFormValues>();

  // Track initial text values to avoid unnecessary saves on blur
  const initialCompanyName = useRef(values.company_name);
  const initialCompanyDescription = useRef(values.company_description);

  // Tools availability
  const { tools: availableTools } = useAvailableTools();
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;
  const searchTool = availableTools.find(
    (t) => t.in_code_tool_id === SEARCH_TOOL_ID
  );
  const webSearchTool = availableTools.find(
    (t) => t.in_code_tool_id === WEB_SEARCH_TOOL_ID
  );

  // Connectors
  const { ccPairs } = useCCPairs();
  const uniqueSources = Array.from(new Set(ccPairs.map((p) => p.source)));

  // MCP servers and OpenAPI tools
  const { mcpData } = useMcpServersForAgentEditor();
  const { openApiTools: openApiToolsRaw } = useOpenApiTools();
  const mcpServers = mcpData?.mcp_servers ?? [];
  const openApiTools = openApiToolsRaw ?? [];

  const mcpServersWithTools = mcpServers.map((server) => ({
    server,
    tools: availableTools
      .filter((tool) => tool.mcp_server_id === server.id)
      .map((tool) => ({
        id: tool.id,
        icon: getActionIcon(server.server_url, server.name),
        name: tool.display_name || tool.name,
        description: tool.description,
      })),
  }));

  // Default agent configuration (system prompt)
  const { data: defaultAgentConfig, mutate: mutateDefaultAgent } =
    useSWR<DefaultAgentConfiguration>(
      "/api/admin/default-assistant/configuration",
      errorHandlingFetcher
    );

  const enabledToolIds = defaultAgentConfig?.tool_ids ?? [];

  const isToolEnabled = useCallback(
    (toolDbId: number) => enabledToolIds.includes(toolDbId),
    [enabledToolIds]
  );

  const saveToolIds = useCallback(
    async (newToolIds: number[]) => {
      // Optimistic update so subsequent toggles read fresh state
      const optimisticData = defaultAgentConfig
        ? { ...defaultAgentConfig, tool_ids: newToolIds }
        : undefined;
      try {
        await mutateDefaultAgent(
          async () => {
            const response = await fetch("/api/admin/default-assistant", {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ tool_ids: newToolIds }),
            });
            if (!response.ok) {
              const errorMsg = (await getErrorMsg(response)) ?? "Unknown error";
              throw new Error(errorMsg);
            }
            return optimisticData;
          },
          { optimisticData, revalidate: true }
        );
        toast.success(t("admin.chatPreferencesPage.toastToolsUpdated"));
      } catch {
        toast.error(t("admin.chatPreferencesPage.toastToolsFailed"));
      }
    },
    [defaultAgentConfig, mutateDefaultAgent, t]
  );

  const toggleTool = useCallback(
    (toolDbId: number, enabled: boolean) => {
      const newToolIds = enabled
        ? [...enabledToolIds, toolDbId]
        : enabledToolIds.filter((id) => id !== toolDbId);
      void saveToolIds(newToolIds);
    },
    [enabledToolIds, saveToolIds]
  );

  const toggleTools = useCallback(
    (toolDbIds: number[], enabled: boolean) => {
      const idsSet = new Set(toolDbIds);
      const withoutIds = enabledToolIds.filter((id) => !idsSet.has(id));
      const newToolIds = enabled ? [...withoutIds, ...toolDbIds] : withoutIds;
      void saveToolIds(newToolIds);
    },
    [enabledToolIds, saveToolIds]
  );

  // System prompt modal state
  const [systemPromptModalOpen, setSystemPromptModalOpen] = useState(false);
  const [systemPromptValue, setSystemPromptValue] = useState("");

  const saveSettings = useCallback(
    async (updates: Partial<Settings>) => {
      const currentSettings = settings?.settings;
      if (!currentSettings) return;

      const newSettings = { ...currentSettings, ...updates };

      try {
        const response = await fetch("/api/admin/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(newSettings),
        });

        if (!response.ok) {
          const errorMsg = (await getErrorMsg(response)) ?? "Unknown error";
          throw new Error(errorMsg);
        }

        router.refresh();
        toast.success(t("admin.chatPreferencesPage.toastSettingsUpdated"));
      } catch {
        toast.error(t("admin.chatPreferencesPage.toastSettingsFailed"));
      }
    },
    [settings, router, t]
  );

  return (
    <>
      <SettingsLayouts.Root>
        <SettingsLayouts.Header
          icon={route.icon}
          title={t(route.titleKey || "", { defaultValue: route.title })}
          description={t("admin.chatPreferencesPage.description")}
          separator
        />

        <SettingsLayouts.Body>
          {/* Team Context */}
          <Section gap={1}>
            <InputLayouts.Vertical
              title={t("admin.chatPreferencesPage.teamNameTitle")}
              subDescription={t(
                "admin.chatPreferencesPage.teamNameDescription"
              )}
            >
              <InputTypeInField
                name="company_name"
                placeholder={t("admin.chatPreferencesPage.teamNamePlaceholder")}
                onBlur={() => {
                  if (values.company_name !== initialCompanyName.current) {
                    void saveSettings({
                      company_name: values.company_name || null,
                    });
                    initialCompanyName.current = values.company_name;
                  }
                }}
              />
            </InputLayouts.Vertical>

            <InputLayouts.Vertical
              title={t("admin.chatPreferencesPage.teamContextTitle")}
              subDescription={t(
                "admin.chatPreferencesPage.teamContextDescription"
              )}
            >
              <InputTextAreaField
                name="company_description"
                placeholder={t(
                  "admin.chatPreferencesPage.teamContextPlaceholder"
                )}
                rows={4}
                maxRows={10}
                autoResize
                onBlur={() => {
                  if (
                    values.company_description !==
                    initialCompanyDescription.current
                  ) {
                    void saveSettings({
                      company_description: values.company_description || null,
                    });
                    initialCompanyDescription.current =
                      values.company_description;
                  }
                }}
              />
            </InputLayouts.Vertical>
          </Section>

          <InputLayouts.Horizontal
            title={t("admin.chatPreferencesPage.systemPromptTitle")}
            description={t("admin.chatPreferencesPage.systemPromptDescription")}
          >
            <Button
              prominence="tertiary"
              icon={SvgAddLines}
              onClick={() => {
                setSystemPromptValue(
                  defaultAgentConfig?.system_prompt ??
                    defaultAgentConfig?.default_system_prompt ??
                    ""
                );
                setSystemPromptModalOpen(true);
              }}
            >
              {t("admin.chatPreferencesPage.modifyPrompt")}
            </Button>
          </InputLayouts.Horizontal>

          <Separator noPadding />

          {/* Features */}
          <Section gap={0.75}>
            <Content
              title={t("admin.chatPreferencesPage.featuresTitle")}
              sizePreset="main-content"
              variant="section"
            />
            <Card>
              <SimpleTooltip
                tooltip={
                  uniqueSources.length === 0
                    ? t("admin.chatPreferencesPage.searchModeSetupTooltip")
                    : undefined
                }
                side="top"
              >
                <Disabled disabled={uniqueSources.length === 0} allowClick>
                  <div className="w-full">
                    <InputLayouts.Horizontal
                      title={t("admin.chatPreferencesPage.searchModeTitle")}
                      description={t(
                        "admin.chatPreferencesPage.searchModeDescription"
                      )}
                      disabled={uniqueSources.length === 0}
                    >
                      <SwitchField
                        name="search_ui_enabled"
                        onCheckedChange={(checked) => {
                          void saveSettings({ search_ui_enabled: checked });
                        }}
                        disabled={uniqueSources.length === 0}
                      />
                    </InputLayouts.Horizontal>
                  </div>
                </Disabled>
              </SimpleTooltip>
              <InputLayouts.Horizontal
                title={t("admin.chatPreferencesPage.deepResearchTitle")}
                description={t(
                  "admin.chatPreferencesPage.deepResearchDescription"
                )}
              >
                <SwitchField
                  name="deep_research_enabled"
                  onCheckedChange={(checked) => {
                    void saveSettings({ deep_research_enabled: checked });
                  }}
                />
              </InputLayouts.Horizontal>
              <InputLayouts.Horizontal
                title={t("admin.chatPreferencesPage.chatAutoScrollTitle")}
                description={t(
                  "admin.chatPreferencesPage.chatAutoScrollDescription"
                )}
              >
                <SwitchField
                  name="auto_scroll"
                  onCheckedChange={(checked) => {
                    void saveSettings({ auto_scroll: checked });
                  }}
                />
              </InputLayouts.Horizontal>
            </Card>
          </Section>

          <Separator noPadding />

          <Disabled disabled={values.disable_default_assistant}>
            <div>
              <Section gap={1.5}>
                {/* Connectors */}
                <Section gap={0.75}>
                  <Content
                    title={t("admin.chatPreferencesPage.connectorsTitle")}
                    sizePreset="main-content"
                    variant="section"
                  />

                  <Section
                    flexDirection="row"
                    justifyContent="between"
                    alignItems="center"
                    gap={0.25}
                  >
                    {uniqueSources.length === 0 ? (
                      <EmptyMessage
                        title={t("admin.chatPreferencesPage.noConnectors")}
                      />
                    ) : (
                      <>
                        <Section
                          flexDirection="row"
                          justifyContent="start"
                          alignItems="center"
                          gap={0.25}
                        >
                          {uniqueSources.slice(0, 3).map((source) => {
                            const meta = getSourceMetadata(source);
                            return (
                              <Card
                                key={source}
                                padding={0.75}
                                className="w-[10rem]"
                              >
                                <Content
                                  icon={meta.icon}
                                  title={meta.displayName}
                                  sizePreset="main-ui"
                                />
                              </Card>
                            );
                          })}
                        </Section>

                        <Button
                          href="/admin/indexing/status"
                          prominence="tertiary"
                          rightIcon={SvgExternalLink}
                        >
                          {t("admin.chatPreferencesPage.manageAll")}
                        </Button>
                      </>
                    )}
                  </Section>
                </Section>

                {/* Actions & Tools */}
                <SimpleCollapsible>
                  <SimpleCollapsible.Header
                    title={t("admin.chatPreferencesPage.actionsToolsTitle")}
                    description={t(
                      "admin.chatPreferencesPage.actionsToolsDescription"
                    )}
                  />
                  <SimpleCollapsible.Content>
                    <Section gap={0.5}>
                      {vectorDbEnabled && searchTool && (
                        <Card>
                          <InputLayouts.Horizontal
                            title={t(
                              "admin.chatPreferencesPage.internalSearchTitle"
                            )}
                            description={t(
                              "admin.chatPreferencesPage.internalSearchDescription"
                            )}
                          >
                            <Switch
                              checked={isToolEnabled(searchTool.id)}
                              onCheckedChange={(checked) =>
                                void toggleTool(searchTool.id, checked)
                              }
                            />
                          </InputLayouts.Horizontal>
                        </Card>
                      )}

                      <Card variant={webSearchTool ? undefined : "disabled"}>
                        <InputLayouts.Horizontal
                          title={t("admin.chatPreferencesPage.webSearchTitle")}
                          description={t(
                            "admin.chatPreferencesPage.webSearchDescription"
                          )}
                          disabled={!webSearchTool}
                        >
                          <Switch
                            checked={
                              webSearchTool
                                ? isToolEnabled(webSearchTool.id)
                                : false
                            }
                            onCheckedChange={(checked) =>
                              webSearchTool &&
                              void toggleTool(webSearchTool.id, checked)
                            }
                            disabled={!webSearchTool}
                          />
                        </InputLayouts.Horizontal>
                      </Card>
                    </Section>

                    {/* Separator between built-in tools and MCP/OpenAPI tools */}
                    {(mcpServersWithTools.length > 0 ||
                      openApiTools.length > 0) && (
                      <Separator noPadding className="py-3" />
                    )}

                    {/* MCP Servers & OpenAPI Tools */}
                    <Section gap={0.5}>
                      {mcpServersWithTools.map(({ server, tools }) => (
                        <MCPServerCard
                          key={`mcp-server-${server.id}`}
                          server={server}
                          tools={tools}
                          isToolEnabled={isToolEnabled}
                          onToggleTool={toggleTool}
                          onToggleTools={toggleTools}
                        />
                      ))}
                      {openApiTools.map((tool, index) => (
                        <ExpandableCard.Root
                          key={`openapi-tool-${tool.id ?? tool.name ?? index}`}
                          defaultFolded
                        >
                          <ActionsLayouts.Header
                            title={tool.display_name || tool.name}
                            description={tool.description}
                            icon={SvgActions}
                            rightChildren={
                              <Switch
                                checked={isToolEnabled(tool.id)}
                                onCheckedChange={(checked) =>
                                  toggleTool(tool.id, checked)
                                }
                              />
                            }
                          />
                        </ExpandableCard.Root>
                      ))}
                    </Section>
                  </SimpleCollapsible.Content>
                </SimpleCollapsible>
              </Section>
            </div>
          </Disabled>

          <Separator noPadding />

          {/* Advanced Options */}
          <SimpleCollapsible defaultOpen={false}>
            <SimpleCollapsible.Header
              title={t("admin.chatPreferencesPage.advancedOptionsTitle")}
            />
            <SimpleCollapsible.Content>
              <Section gap={1}>
                <Card>
                  <InputLayouts.Horizontal
                    title={t("admin.chatPreferencesPage.keepChatHistoryTitle")}
                    description={t(
                      "admin.chatPreferencesPage.keepChatHistoryDescription"
                    )}
                  >
                    <InputSelectField
                      name="maximum_chat_retention_days"
                      onValueChange={(value) => {
                        void saveSettings({
                          maximum_chat_retention_days:
                            value === "forever" ? null : parseInt(value, 10),
                        });
                      }}
                    >
                      <InputSelect.Trigger />
                      <InputSelect.Content>
                        <InputSelect.Item value="forever">
                          {t("admin.chatPreferencesPage.forever")}
                        </InputSelect.Item>
                        <InputSelect.Item value="7">
                          {t("admin.chatPreferencesPage.days", { count: 7 })}
                        </InputSelect.Item>
                        <InputSelect.Item value="30">
                          {t("admin.chatPreferencesPage.days", { count: 30 })}
                        </InputSelect.Item>
                        <InputSelect.Item value="90">
                          {t("admin.chatPreferencesPage.days", { count: 90 })}
                        </InputSelect.Item>
                        <InputSelect.Item value="365">
                          {t("admin.chatPreferencesPage.days", {
                            count: 365,
                          })}
                        </InputSelect.Item>
                      </InputSelect.Content>
                    </InputSelectField>
                  </InputLayouts.Horizontal>
                </Card>

                <Card>
                  <InputLayouts.Horizontal
                    title={t(
                      "admin.chatPreferencesPage.allowAnonymousUsersTitle"
                    )}
                    description={t(
                      "admin.chatPreferencesPage.allowAnonymousUsersDescription"
                    )}
                  >
                    <SwitchField
                      name="anonymous_user_enabled"
                      onCheckedChange={(checked) => {
                        void saveSettings({ anonymous_user_enabled: checked });
                      }}
                    />
                  </InputLayouts.Horizontal>

                  <InputLayouts.Horizontal
                    title={t(
                      "admin.chatPreferencesPage.alwaysStartWithAgentTitle"
                    )}
                    description={t(
                      "admin.chatPreferencesPage.alwaysStartWithAgentDescription"
                    )}
                  >
                    <SwitchField
                      name="disable_default_assistant"
                      onCheckedChange={(checked) => {
                        void saveSettings({
                          disable_default_assistant: checked,
                        });
                      }}
                    />
                  </InputLayouts.Horizontal>
                </Card>
              </Section>
            </SimpleCollapsible.Content>
          </SimpleCollapsible>
        </SettingsLayouts.Body>
      </SettingsLayouts.Root>

      <Modal
        open={systemPromptModalOpen}
        onOpenChange={setSystemPromptModalOpen}
      >
        <Modal.Content width="md" height="fit">
          <Modal.Header
            icon={SvgAddLines}
            title={t("admin.chatPreferencesPage.systemPromptTitle")}
            description={t(
              "admin.chatPreferencesPage.systemPromptModalDescription"
            )}
            onClose={() => setSystemPromptModalOpen(false)}
          />
          <Modal.Body>
            <InputTextArea
              value={systemPromptValue}
              onChange={(e) => setSystemPromptValue(e.target.value)}
              placeholder={t(
                "admin.chatPreferencesPage.systemPromptPlaceholder"
              )}
              rows={8}
              maxRows={20}
              autoResize
            />
          </Modal.Body>
          <Modal.Footer>
            <Button
              prominence="secondary"
              onClick={() => setSystemPromptModalOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              prominence="primary"
              onClick={async () => {
                try {
                  const response = await fetch("/api/admin/default-assistant", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      system_prompt: systemPromptValue,
                    }),
                  });
                  if (!response.ok) {
                    const errorMsg =
                      (await getErrorMsg(response)) ?? "Unknown error";
                    throw new Error(errorMsg);
                  }
                  await mutateDefaultAgent();
                  setSystemPromptModalOpen(false);
                  toast.success(
                    t("admin.chatPreferencesPage.toastSystemPromptUpdated")
                  );
                } catch {
                  toast.error(
                    t("admin.chatPreferencesPage.toastSystemPromptFailed")
                  );
                }
              }}
            >
              {t("common.save")}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </>
  );
}

export default function ChatPreferencesPage() {
  const settings = useSettingsContext();

  const initialValues: ChatPreferencesFormValues = {
    // Features
    search_ui_enabled: settings.settings.search_ui_enabled ?? false,
    deep_research_enabled: settings.settings.deep_research_enabled ?? true,
    auto_scroll: settings.settings.auto_scroll ?? false,

    // Team context
    company_name: settings.settings.company_name ?? "",
    company_description: settings.settings.company_description ?? "",

    // Advanced
    maximum_chat_retention_days:
      settings.settings.maximum_chat_retention_days?.toString() ?? "forever",
    anonymous_user_enabled: settings.settings.anonymous_user_enabled ?? false,
    disable_default_assistant:
      settings.settings.disable_default_assistant ?? false,
  };

  return (
    <Formik
      initialValues={initialValues}
      onSubmit={() => {}}
      enableReinitialize
    >
      <Form className="h-full w-full">
        <ChatPreferencesForm />
      </Form>
    </Formik>
  );
}

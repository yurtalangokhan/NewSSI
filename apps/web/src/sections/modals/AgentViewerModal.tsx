"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { FullPersona } from "@/app/admin/agents/interfaces";
import { useModal } from "@/refresh-components/contexts/ModalContext";
import Modal from "@/refresh-components/Modal";
import { Section } from "@/layouts/general-layouts";
import { Content, ContentAction } from "@opal/layouts";
import Text from "@/refresh-components/texts/Text";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import AgentAvailabilityBadge from "@/refresh-components/agents/AgentAvailabilityBadge";
import Separator from "@/refresh-components/Separator";
import SimpleCollapsible from "@/refresh-components/SimpleCollapsible";
import {
  SvgActions,
  SvgAlertCircle,
  SvgBubbleText,
  SvgClock,
  SvgExpand,
  SvgFold,
  SvgOrganization,
  SvgStar,
  SvgUser,
} from "@opal/icons";
import Tag from "@/refresh-components/buttons/Tag";
import * as ExpandableCard from "@/layouts/expandable-card-layouts";
import * as ActionsLayouts from "@/layouts/actions-layouts";
import useMcpServersForAgentEditor from "@/hooks/useMcpServersForAgentEditor";
import { getActionIcon } from "@/lib/tools/mcpUtils";
import { MCPServer, ToolSnapshot } from "@/lib/tools/interfaces";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import { Horizontal } from "@/layouts/input-layouts";
import Switch from "@/refresh-components/inputs/Switch";
import Button from "@/refresh-components/buttons/Button";
import AppInputBar from "@/sections/input/AppInputBar";
import { useFilters, useLlmManager } from "@/lib/hooks";
import { resolveAgentOwnerEmail } from "@/lib/agents";
import { formatMmDdYyyy } from "@/lib/dateUtils";
import { useProjectsContext } from "@/providers/ProjectsContext";
import { FileCard } from "@/sections/cards/FileCard";
import DocumentSetCard from "@/sections/cards/DocumentSetCard";
import { getDisplayName } from "@/lib/llmConfig/utils";
import { getAgentAvailabilityIssues } from "@/lib/agentAvailability";
import { useLLMProviders } from "@/hooks/useLLMProviders";
import { Interactive } from "@opal/core";
import { useTranslation } from "react-i18next";
import { buildAppPath } from "@/hooks/appNavigation";
import { saveAppDraftCommand } from "@/app/app/services/draftCommand";

/**
 * Memory section rendered inside the Actions & Tools collapsible.
 * Shows the "Bellek" heading with a badge indicating memory type.
 */
function MemorySection({
  longTermMemoryEnabled,
}: {
  longTermMemoryEnabled: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-row items-center gap-2 px-0.5 py-1">
      <Text mainUiBody text02 className="shrink-0">
        {t("agentViewer.memoryTitle")}
      </Text>
      <Tag
        icon={SvgClock}
        label={
          longTermMemoryEnabled
            ? t("agentViewer.memoryTypeLongTerm")
            : t("agentViewer.memoryTypeStandard")
        }
      />
    </div>
  );
}

/**
 * Read-only MCP Server card for the viewer modal.
 * Displays the server header with its tools listed in the expandable content area.
 */
interface ViewerMCPServerCardProps {
  server: MCPServer;
  tools: ToolSnapshot[];
}

function ViewerMCPServerCard({ server, tools }: ViewerMCPServerCardProps) {
  const [folded, setFolded] = useState(false);
  const { t } = useTranslation();
  const serverIcon = getActionIcon(server.server_url, server.name);

  return (
    <ExpandableCard.Root isFolded={folded} onFoldedChange={setFolded}>
      <ExpandableCard.Header>
        <div className="p-2">
          <ContentAction
            icon={serverIcon}
            title={server.name}
            description={server.description}
            sizePreset="main-ui"
            variant="section"
            rightChildren={
              <Button
                internal
                rightIcon={folded ? SvgExpand : SvgFold}
                onClick={() => setFolded((prev) => !prev)}
              >
                {folded
                  ? t("agentViewer.expandButton")
                  : t("agentViewer.foldButton")}
              </Button>
            }
          />
        </div>
      </ExpandableCard.Header>
      {tools.length > 0 && (
        <ActionsLayouts.Content>
          {tools.map((tool) => (
            <Section key={tool.id} padding={0.25}>
              <Content
                title={tool.display_name}
                description={tool.description}
                sizePreset="main-ui"
                variant="section"
              />
            </Section>
          ))}
        </ActionsLayouts.Content>
      )}
    </ExpandableCard.Root>
  );
}

/**
 * Read-only OpenAPI tool card for the viewer modal.
 * Displays just the tool header (no expandable content).
 */
function ViewerOpenApiToolCard({ tool }: { tool: ToolSnapshot }) {
  return (
    <ExpandableCard.Root>
      <ExpandableCard.Header>
        <div className="p-2">
          <Content
            icon={SvgActions}
            title={tool.display_name}
            description={tool.description}
            sizePreset="main-ui"
            variant="section"
          />
        </div>
      </ExpandableCard.Header>
    </ExpandableCard.Root>
  );
}

const EMPTY_DOCS: [] = [];

/**
 * Floating ChatInputBar below the AgentViewerModal.
 * On submit, navigates to the agent's chat with the message pre-filled.
 */
interface AgentChatInputProps {
  agent: FullPersona;
  onSubmit: (message: string) => void;
}
function AgentChatInput({ agent, onSubmit }: AgentChatInputProps) {
  const llmManager = useLlmManager(undefined, agent);
  const filterManager = useFilters();

  return (
    <AppInputBar
      onSubmit={onSubmit}
      llmManager={llmManager}
      chatState="input"
      filterManager={filterManager}
      selectedAgent={agent}
      selectedDocuments={EMPTY_DOCS}
      removeDocs={() => {}}
      stopGenerating={() => {}}
      handleFileUpload={() => {}}
      toggleDocumentSidebar={() => {}}
      currentSessionFileTokenCount={0}
      availableContextTokens={Infinity}
      retrievalEnabled={false}
      deepResearchEnabled={false}
      toggleDeepResearch={() => {}}
      disabled={false}
    />
  );
}

/**
 * AgentViewerModal - A read-only view of an agent's configuration
 *
 * This modal is the view-only counterpart to `AgentEditorPage.tsx`. While
 * AgentEditorPage allows creating and editing agents with forms and inputs,
 * AgentViewerModal displays the same information in a read-only format.
 *
 * Key differences from AgentEditorPage:
 * - Modal presentation instead of full page
 * - Read-only display (no form inputs, switches, or editable fields)
 * - Static text/badges instead of form controls
 * - Designed to be opened from AgentCard when clicking on the card body
 *
 * Sections displayed (mirroring AgentEditorPage):
 * - Agent info: name, description, avatar
 * - Instructions (system prompt)
 * - Conversation starters
 * - Knowledge configuration
 * - Actions/tools
 * - Advanced options (model, sharing status)
 */
export interface AgentViewerModalProps {
  agent: FullPersona;
}
export default function AgentViewerModal({ agent }: AgentViewerModalProps) {
  const agentViewerModal = useModal();
  const router = useRouter();
  const { t } = useTranslation();
  const { allRecentFiles } = useProjectsContext();
  const { llmProviders } = useLLMProviders(agent.id);
  const routeAgentId = agent.external_id ?? agent.id;

  const handleStartChat = useCallback(
    (message: string) => {
      saveAppDraftCommand({
        agentId: String(routeAgentId),
        message,
        submitOnLoad: true,
      });
      router.push(buildAppPath({ type: "agent", id: routeAgentId }) as Route);
      agentViewerModal.toggle(false);
    },
    [agentViewerModal, routeAgentId, router]
  );

  const ragDocumentCollections =
    agent.rag_config?.document_processing?.length ?? 0;
  const ragGraphCollections = agent.rag_config?.knowledge_graph?.length ?? 0;
  const hasRagKnowledge = ragDocumentCollections > 0 || ragGraphCollections > 0;

  const hasKnowledge =
    (agent.document_sets && agent.document_sets.length > 0) ||
    (agent.hierarchy_nodes && agent.hierarchy_nodes.length > 0) ||
    (agent.user_file_ids && agent.user_file_ids.length > 0) ||
    hasRagKnowledge;

  // Categorize tools into MCP, OpenAPI, and built-in
  const mcpToolsByServerId = useMemo(() => {
    const map = new Map<number, ToolSnapshot[]>();
    agent.tools.forEach((tool) => {
      if (tool.mcp_server_id != null) {
        const existing = map.get(tool.mcp_server_id) || [];
        existing.push(tool);
        map.set(tool.mcp_server_id, existing);
      }
    });
    return map;
  }, [agent.tools]);

  const openApiTools = useMemo(
    () =>
      agent.tools.filter((t) => !t.in_code_tool_id && t.mcp_server_id == null),
    [agent.tools]
  );

  const builtInTools = useMemo(
    () =>
      agent.tools.filter((t) => !!t.in_code_tool_id && t.mcp_server_id == null),
    [agent.tools]
  );

  // Fetch MCP server metadata for display
  const { mcpData } = useMcpServersForAgentEditor();
  const mcpServers = mcpData?.mcp_servers ?? [];

  const mcpServersWithTools = useMemo(
    () =>
      mcpServers
        .filter((server) => mcpToolsByServerId.has(server.id))
        .map((server) => ({
          server,
          tools: mcpToolsByServerId.get(server.id)!,
        })),
    [mcpServers, mcpToolsByServerId]
  );

  const unknownMcpToolNames = useMemo(() => {
    const knownToolNames = new Set(
      agent.tools
        .flatMap((tool) => [tool.name, tool.in_code_tool_id || ""])
        .filter(Boolean)
    );
    return (agent.mcp_tools || []).filter((name) => !knownToolNames.has(name));
  }, [agent.mcp_tools, agent.tools]);

  const hasActions =
    mcpServersWithTools.length > 0 ||
    openApiTools.length > 0 ||
    builtInTools.length > 0 ||
    unknownMcpToolNames.length > 0;
  const longTermMemoryEnabled =
    Boolean(agent.long_term_memory) || agent.memory_type === "long_term";
  const defaultModel = getDisplayName(agent, llmProviders ?? []);
  const availabilityIssues = getAgentAvailabilityIssues(agent.availability);

  return (
    <Modal
      open={agentViewerModal.isOpen}
      onOpenChange={agentViewerModal.toggle}
    >
      <Modal.Content
        width="md-sm"
        height="lg"
        bottomSlot={<AgentChatInput agent={agent} onSubmit={handleStartChat} />}
      >
        <Modal.Header
          icon={(props) => <AgentAvatar agent={agent} {...props} size={24} />}
          title={agent.name}
          tag={<AgentAvailabilityBadge agent={agent} showLabel />}
          onClose={() => agentViewerModal.toggle(false)}
        >
          <AgentAvailabilityBadge
            agent={agent}
            showLabel
            className="ml-8 w-fit"
          />
        </Modal.Header>

        <Modal.Body>
          {/* Metadata */}
          <Section flexDirection="row" justifyContent="start">
            {agent.featured && (
              <Content
                icon={SvgStar}
                title={t("agentViewer.featuredLabel")}
                sizePreset="main-ui"
                variant="body"
              />
            )}
            <Content
              icon={SvgUser}
              title={resolveAgentOwnerEmail(agent.owner?.email, t)}
              sizePreset="main-ui"
              variant="body"
              prominence="muted"
            />
            {agent.is_public && (
              <Content
                icon={SvgOrganization}
                title={t("agentViewer.publicToOrgLabel")}
                sizePreset="main-ui"
                variant="body"
                prominence="muted"
              />
            )}
          </Section>

          {/* Description */}
          {agent.description && <Text text03>{agent.description}</Text>}

          {availabilityIssues.length > 0 && (
            <div className="rounded-08 border border-status-error-02 bg-status-error-00 p-2">
              <Section gap={0.5} alignItems="start">
                <Content
                  icon={SvgAlertCircle}
                  title={t(
                    "agentViewer.availabilityIssuesTitle",
                    "Availability issues"
                  )}
                  sizePreset="main-ui"
                  variant="section"
                />
                <div className="flex flex-col gap-1">
                  {availabilityIssues.map((issue, index) => (
                    <Text
                      key={`${issue.component}-${index}`}
                      secondaryBody
                      text02
                    >
                      {issue.message}
                    </Text>
                  ))}
                </div>
              </Section>
            </div>
          )}

          {/* Knowledge */}
          <Separator noPadding />
          <Section gap={0.5} alignItems="start">
            <Content
              title={t("agentViewer.knowledgeSectionTitle")}
              sizePreset="main-content"
              variant="section"
            />
            {hasKnowledge ? (
              <Section
                gap={0.5}
                flexDirection="row"
                justifyContent="start"
                wrap
                alignItems="start"
              >
                {agent.document_sets?.map((docSet) => (
                  <DocumentSetCard key={docSet.id} documentSet={docSet} />
                ))}
                {agent.user_file_ids?.map((fileId) => {
                  const file = allRecentFiles.find((f) => f.id === fileId);
                  if (!file) return null;
                  return <FileCard key={fileId} file={file} />;
                })}
                {ragDocumentCollections > 0 && (
                  <Content
                    icon={SvgActions}
                    title={t("agentViewer.documentProcessingLabel")}
                    description={t(
                      "agentViewer.documentProcessingDescription",
                      { count: ragDocumentCollections }
                    )}
                    sizePreset="main-ui"
                    variant="section"
                  />
                )}
                {ragGraphCollections > 0 && (
                  <Content
                    icon={SvgActions}
                    title={t("agentViewer.knowledgeGraphLabel")}
                    description={t("agentViewer.knowledgeGraphDescription", {
                      count: ragGraphCollections,
                    })}
                    sizePreset="main-ui"
                    variant="section"
                  />
                )}
              </Section>
            ) : (
              <EmptyMessage title={t("agentViewer.noKnowledgeMessage")} />
            )}
          </Section>

          {/* Actions & Tools */}
          <SimpleCollapsible>
            <SimpleCollapsible.Header
              title={t("agentViewer.actionsAndToolsTitle")}
            />
            <SimpleCollapsible.Content>
              {hasActions ? (
                <Section gap={0.5} alignItems="start">
                  {mcpServersWithTools.map(({ server, tools }) => (
                    <ViewerMCPServerCard
                      key={server.id}
                      server={server}
                      tools={tools}
                    />
                  ))}
                  {openApiTools.map((tool) => (
                    <ViewerOpenApiToolCard key={tool.id} tool={tool} />
                  ))}
                  {builtInTools.map((tool) => (
                    <ViewerOpenApiToolCard
                      key={`builtin-${tool.id}`}
                      tool={tool}
                    />
                  ))}
                  {unknownMcpToolNames.map((toolName) => (
                    <ExpandableCard.Root key={`mcp-name-${toolName}`}>
                      <ExpandableCard.Header>
                        <div className="p-2">
                          <Content
                            icon={SvgActions}
                            title={toolName}
                            description={t("agentViewer.mcpToolDescription")}
                            sizePreset="main-ui"
                            variant="section"
                          />
                        </div>
                      </ExpandableCard.Header>
                    </ExpandableCard.Root>
                  ))}

                  <Separator noPadding />
                  <MemorySection
                    longTermMemoryEnabled={longTermMemoryEnabled}
                  />
                </Section>
              ) : (
                <Section gap={0.5} alignItems="start">
                  <EmptyMessage title={t("agentViewer.noActionsMessage")} />
                  <MemorySection
                    longTermMemoryEnabled={longTermMemoryEnabled}
                  />
                </Section>
              )}
            </SimpleCollapsible.Content>
          </SimpleCollapsible>

          {/* More Info (Collapsible) */}
          <Separator noPadding />
          <SimpleCollapsible>
            <SimpleCollapsible.Header title={t("agentViewer.moreInfoTitle")} />
            <SimpleCollapsible.Content>
              <Section gap={0.5} alignItems="start">
                {agent.system_prompt && (
                  <Content
                    title={t("agentViewer.instructionsLabel")}
                    description={agent.system_prompt}
                    sizePreset="main-ui"
                    variant="section"
                  />
                )}
                {defaultModel && (
                  <Horizontal
                    title={t("agentViewer.defaultModelLabel")}
                    description={t("agentViewer.defaultModelDescription")}
                    nonInteractive
                    sizePreset="main-ui"
                  >
                    <Text>{defaultModel}</Text>
                  </Horizontal>
                )}
                {agent.search_start_date && (
                  <Horizontal
                    title={t("agentViewer.knowledgeCutoffLabel")}
                    description={t("agentViewer.knowledgeCutoffDescription")}
                    nonInteractive
                    sizePreset="main-ui"
                  >
                    <Text mainUiMono>
                      {formatMmDdYyyy(agent.search_start_date)}
                    </Text>
                  </Horizontal>
                )}
                <Horizontal
                  title={t("agentViewer.overwriteSystemPromptsLabel")}
                  description={t(
                    "agentViewer.overwriteSystemPromptsDescription"
                  )}
                  nonInteractive
                  sizePreset="main-ui"
                >
                  <Switch disabled checked={agent.replace_base_system_prompt} />
                </Horizontal>
              </Section>
            </SimpleCollapsible.Content>
          </SimpleCollapsible>

          {/* Prompt Reminders */}
          {agent.task_prompt && (
            <>
              <Separator noPadding />
              <Content
                title={t("agentViewer.promptRemindersLabel")}
                description={agent.task_prompt}
                sizePreset="main-content"
                variant="section"
              />
            </>
          )}

          {/* Conversation Starters */}
          {agent.starter_messages && agent.starter_messages.length > 0 && (
            <>
              <Separator noPadding />
              <Content
                title={t("agentViewer.conversationStartersLabel")}
                sizePreset="main-content"
                variant="section"
              />
              <div className="grid grid-cols-2 gap-1 w-full">
                {agent.starter_messages.map((starter, index) => (
                  <Interactive.Base
                    key={index}
                    onClick={() => handleStartChat(starter.message)}
                    prominence="tertiary"
                  >
                    <Interactive.Container>
                      <Content
                        icon={SvgBubbleText}
                        title={starter.message}
                        sizePreset="main-ui"
                        variant="body"
                        prominence="muted"
                        widthVariant="full"
                      />
                    </Interactive.Container>
                  </Interactive.Base>
                ))}
              </div>
            </>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}

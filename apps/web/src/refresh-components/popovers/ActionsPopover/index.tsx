"use client";

import {
  FILE_READER_TOOL_ID,
  IMAGE_GENERATION_TOOL_ID,
  PYTHON_TOOL_ID,
  SEARCH_TOOL_ID,
  WEB_SEARCH_TOOL_ID,
} from "@/app/app/components/tools/constants";
import { useEffect, useMemo, useCallback, useState, useRef } from "react";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import SwitchList, {
  SwitchListItem,
} from "@/refresh-components/popovers/ActionsPopover/SwitchList";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { ToolSnapshot } from "@/lib/tools/interfaces";
import { useForcedTools } from "@/lib/hooks/useForcedTools";
import useAgentPreferences from "@/hooks/useAgentPreferences";
import { useUser } from "@/providers/UserProvider";
import { FilterManager, useSourcePreferences } from "@/lib/hooks";
import { listSourceMetadata } from "@/lib/sources";
import { ValidSources } from "@/lib/types";
import { SourceMetadata } from "@/lib/search/interfaces";
import { SourceIcon } from "@/components/SourceIcon";
import { useAvailableTools } from "@/hooks/useAvailableTools";
import useCCPairs from "@/hooks/useCCPairs";
import { useSettingsContext } from "@/providers/SettingsProvider";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { useToolOAuthStatus } from "@/lib/hooks/useToolOAuthStatus";
import LineItem from "@/refresh-components/buttons/LineItem";
import ActionLineItem from "@/refresh-components/popovers/ActionsPopover/ActionLineItem";
import StaticToolListItem from "@/refresh-components/popovers/ActionsPopover/StaticToolListItem";
import { useProjectsContext } from "@/providers/ProjectsContext";
import { SvgActions, SvgSliders } from "@opal/icons";
import { Button } from "@opal/components";
import { useTranslation } from "react-i18next";

// The only tools with real per-tool configuration state (a selected model,
// a configured provider, a base URL) admins set up individually. Everything
// else attached to an agent (built-in tools-service tools, RAG tools) is
// all-or-nothing, so it's just listed rather than made independently
// toggleable/forceable.
const CONFIGURABLE_SYSTEM_TOOL_IDS = new Set([
  SEARCH_TOOL_ID,
  WEB_SEARCH_TOOL_ID,
  IMAGE_GENERATION_TOOL_ID,
  PYTHON_TOOL_ID,
]);

const UNAVAILABLE_TOOL_TOOLTIP_FALLBACK =
  "This action is not configured yet. Ask an admin to enable it.";
const UNAVAILABLE_TOOL_TOOLTIP_ADMIN_FALLBACK =
  "This action is not configured yet. If you have access, enable it in the admin panel.";
const UNAVAILABLE_TOOL_TOOLTIPS: Record<string, string> = {
  [IMAGE_GENERATION_TOOL_ID]:
    "Image generation requires a configured model. If you have access, set one up under Settings > Image Generation, or ask an admin.",
  [WEB_SEARCH_TOOL_ID]:
    "Web search requires a configured provider. If you have access, set one up under Settings > Web Search, or ask an admin.",
  [PYTHON_TOOL_ID]:
    "Code Interpreter requires the service to be configured with a valid base URL. If you have access, configure it in the admin panel, or ask an admin.",
};
const getUnavailableToolTooltip = (
  inCodeToolId?: string | null,
  canAdminConfigure?: boolean
) =>
  (inCodeToolId && UNAVAILABLE_TOOL_TOOLTIPS[inCodeToolId]) ??
  (canAdminConfigure
    ? UNAVAILABLE_TOOL_TOOLTIP_ADMIN_FALLBACK
    : UNAVAILABLE_TOOL_TOOLTIP_FALLBACK);

const ADMIN_CONFIG_LINKS: Record<string, { href: string; tooltip: string }> = {
  [IMAGE_GENERATION_TOOL_ID]: {
    href: "/admin/configuration/image-generation",
    tooltip: "Configure Image Generation",
  },
  [WEB_SEARCH_TOOL_ID]: {
    href: "/admin/configuration/web-search",
    tooltip: "Configure Web Search",
  },
  KnowledgeGraphTool: {
    href: "/admin/kg",
    tooltip: "Configure Knowledge Graph",
  },
};

const OPENAPI_ADMIN_CONFIG = {
  href: "/admin/actions/open-api",
  tooltip: "Manage OpenAPI Actions",
};

const getAdminConfigureInfo = (
  tool: ToolSnapshot
): { href: string; tooltip: string } | null => {
  if (tool.in_code_tool_id && ADMIN_CONFIG_LINKS[tool.in_code_tool_id]) {
    return ADMIN_CONFIG_LINKS[tool.in_code_tool_id] ?? null;
  }

  if (!tool.in_code_tool_id && !tool.mcp_server_id) {
    return OPENAPI_ADMIN_CONFIG;
  }

  return null;
};

// Get source metadata for configured sources - deduplicated by source type
function getConfiguredSources(
  availableSources: ValidSources[]
): Array<SourceMetadata & { originalName: string; uniqueKey: string }> {
  const { t } = useTranslation();
  const allSources = listSourceMetadata();

  const seenSources = new Set<string>();
  const configuredSources: Array<
    SourceMetadata & { originalName: string; uniqueKey: string }
  > = [];

  availableSources.forEach((sourceName) => {
    // Handle federated connectors by removing the federated_ prefix
    const cleanName = sourceName.replace("federated_", "");
    // Skip if we've already seen this source type
    if (seenSources.has(cleanName)) return;
    seenSources.add(cleanName);
    const source = allSources.find(
      (source) => source.internalName === cleanName
    );
    if (source) {
      configuredSources.push({
        ...source,
        originalName: sourceName,
        uniqueKey: cleanName,
      });
    }
  });
  return configuredSources;
}

type SecondaryViewState = { type: "sources" };

export interface ActionsPopoverProps {
  selectedAgent: MinimalPersonaSnapshot;
  filterManager: FilterManager;
  availableSources?: ValidSources[];
  disabled?: boolean;
}

export default function ActionsPopover({
  selectedAgent,
  filterManager,
  availableSources = [],
  disabled = false,
}: ActionsPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [secondaryView, setSecondaryView] = useState<SecondaryViewState | null>(
    null
  );
  const [searchTerm, setSearchTerm] = useState("");
  // const [showFadeMask, setShowFadeMask] = useState(false);
  // const [showTopShadow, setShowTopShadow] = useState(false);
  const { selectedSources, setSelectedSources } = filterManager;

  // Use the OAuth hook
  const { getToolAuthStatus, authenticateTool } = useToolOAuthStatus(
    selectedAgent.id
  );

  const {
    sourcesInitialized,
    enableSources,
    enableAllSources: baseEnableAllSources,
    disableAllSources: baseDisableAllSources,
    toggleSource: baseToggleSource,
    isSourceEnabled,
  } = useSourcePreferences({
    availableSources,
    selectedSources,
    setSelectedSources,
  });

  // Store previously enabled sources when search tool is disabled
  const previouslyEnabledSourcesRef = useRef<SourceMetadata[]>([]);

  const isDefaultAgent = selectedAgent.id === 0;

  // Check if the search tool is explicitly enabled on this persona (admin enabled "Use Knowledge")
  const hasSearchTool = selectedAgent.tools.some(
    (tool) => tool.in_code_tool_id === SEARCH_TOOL_ID
  );

  // Get sources the agent has access to via document sets, hierarchy nodes, and attached documents
  // Default agent has access to all sources
  const agentAccessibleSources = useMemo(() => {
    if (isDefaultAgent) {
      return null; // null means "all accessible"
    }

    const sourceSet = new Set<string>();

    // Add sources from document sets
    selectedAgent.document_sets.forEach((docSet) => {
      // Check cc_pair_summaries (regular connectors)
      docSet.cc_pair_summaries?.forEach((ccPair) => {
        // Normalize by removing federated_ prefix
        const normalized = ccPair.source.replace("federated_", "");
        sourceSet.add(normalized);
      });

      // Check federated_connector_summaries (federated connectors)
      docSet.federated_connector_summaries?.forEach((fedConnector) => {
        // Normalize by removing federated_ prefix
        const normalized = fedConnector.source.replace("federated_", "");
        sourceSet.add(normalized);
      });
    });

    // Add sources from hierarchy nodes and attached documents (via knowledge_sources)
    selectedAgent.knowledge_sources?.forEach((source) => {
      // Normalize by removing federated_ prefix
      const normalized = source.replace("federated_", "");
      sourceSet.add(normalized);
    });

    // If agent has search tool but no specific sources, it can search everything
    if (sourceSet.size === 0 && hasSearchTool) {
      return null;
    }

    return sourceSet;
  }, [
    isDefaultAgent,
    selectedAgent.document_sets,
    selectedAgent.knowledge_sources,
    hasSearchTool,
  ]);

  // Check if non-default agent has no knowledge sources (Internal Search should be disabled)
  // Knowledge sources include document sets, hierarchy nodes, and attached documents
  // If the search tool is present, the admin intentionally enabled knowledge search
  const hasNoKnowledgeSources =
    !isDefaultAgent &&
    !hasSearchTool &&
    selectedAgent.document_sets.length === 0 &&
    (selectedAgent.hierarchy_node_count ?? 0) === 0 &&
    (selectedAgent.attached_document_count ?? 0) === 0;

  // Get the agent preference for this assistant
  const { agentPreferences, setSpecificAgentPreferences } =
    useAgentPreferences();
  const { forcedToolIds, setForcedToolIds } = useForcedTools();

  // Reset state when assistant changes
  useEffect(() => {
    setForcedToolIds([]);
  }, [selectedAgent.id, setForcedToolIds]);

  const { isAdmin, isCurator } = useUser();
  const settings = useSettingsContext();
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;

  const { tools: availableTools } = useAvailableTools();
  const { ccPairs } = useCCPairs(vectorDbEnabled);
  const { currentProjectId, allCurrentProjectFiles } = useProjectsContext();
  // Matched by name, not id: the backend gives every tool from the
  // available-tools catalog the same placeholder id (0), and an agent's own
  // tool snapshots carry synthetic per-agent ids — neither lines up with the
  // other, so name is the only identity both sides share.
  const availableToolNameSet = new Set(availableTools.map((tool) => tool.name));

  // Check if there are any connectors available
  const hasNoConnectors = ccPairs.length === 0;

  const agentPreference = agentPreferences?.[selectedAgent.id];
  const disabledToolIds = agentPreference?.disabled_tool_ids || [];
  const toggleToolForCurrentAgent = (toolId: number) => {
    const disabled = disabledToolIds.includes(toolId);
    setSpecificAgentPreferences(selectedAgent.id, {
      disabled_tool_ids: disabled
        ? disabledToolIds.filter((id) => id !== toolId)
        : [...disabledToolIds, toolId],
    });

    // If we're disabling a tool that is currently forced, remove it from forced tools
    if (!disabled && forcedToolIds.includes(toolId)) {
      setForcedToolIds(forcedToolIds.filter((id) => id !== toolId));
    }
  };

  const toggleForcedTool = (toolId: number) => {
    if (forcedToolIds.includes(toolId)) {
      // If clicking on already forced tool, unforce it
      setForcedToolIds([]);
    } else {
      // If clicking on a new tool, replace any existing forced tools with just this one
      setForcedToolIds([toolId]);
    }
  };

  // Get internal search tool reference for auto-pin logic
  const internalSearchTool = useMemo(
    () =>
      selectedAgent.tools.find(
        (tool) => tool.in_code_tool_id === SEARCH_TOOL_ID && !tool.mcp_server_id
      ),
    [selectedAgent.tools]
  );

  // Handle explicit force toggle from ActionLineItem
  const handleForceToggleWithTracking = useCallback(
    (toolId: number, wasForced: boolean) => {
      // If pinning internal search, enable all accessible sources
      if (
        !wasForced &&
        internalSearchTool &&
        toolId === internalSearchTool.id
      ) {
        const sources = getConfiguredSources(availableSources);
        const accessibleSources = sources.filter(
          (s) =>
            agentAccessibleSources === null ||
            agentAccessibleSources.has(s.uniqueKey)
        );
        setSelectedSources(accessibleSources);
      }
      toggleForcedTool(toolId);
    },
    [
      toggleForcedTool,
      internalSearchTool,
      availableSources,
      agentAccessibleSources,
      setSelectedSources,
    ]
  );

  // Wrapped source functions that auto-pin internal search when sources change
  const enableAllSources = useCallback(() => {
    // Only enable sources the agent has access to
    const allConfiguredSources = getConfiguredSources(availableSources);
    const accessibleSources = allConfiguredSources.filter(
      (s) =>
        agentAccessibleSources === null ||
        agentAccessibleSources.has(s.uniqueKey)
    );
    setSelectedSources(accessibleSources);

    if (internalSearchTool) {
      setForcedToolIds([internalSearchTool.id]);
    }
  }, [
    agentAccessibleSources,
    availableSources,
    setSelectedSources,
    internalSearchTool,
    setForcedToolIds,
  ]);

  const disableAllSources = useCallback(() => {
    baseDisableAllSources();
    const willUnpin =
      internalSearchTool && forcedToolIds.includes(internalSearchTool.id);
    if (willUnpin) {
      setForcedToolIds([]);
    }
  }, [
    baseDisableAllSources,
    internalSearchTool,
    forcedToolIds,
    setForcedToolIds,
  ]);

  const toggleSource = useCallback(
    (sourceUniqueKey: string) => {
      const wasEnabled = isSourceEnabled(sourceUniqueKey);
      baseToggleSource(sourceUniqueKey);

      const configuredSources = getConfiguredSources(availableSources);

      if (internalSearchTool) {
        if (!wasEnabled) {
          // Enabling a source - auto-pin internal search
          setForcedToolIds([internalSearchTool.id]);
        } else {
          // Disabling a source - check if all sources will be disabled
          const remainingEnabled = configuredSources.filter(
            (s) =>
              s.uniqueKey !== sourceUniqueKey && isSourceEnabled(s.uniqueKey)
          );
          if (
            remainingEnabled.length === 0 &&
            forcedToolIds.includes(internalSearchTool.id)
          ) {
            // All sources disabled - unpin
            setForcedToolIds([]);
          }
        }
      }
    },
    [
      baseToggleSource,
      internalSearchTool,
      isSourceEnabled,
      availableSources,
      forcedToolIds,
      setForcedToolIds,
    ]
  );

  // MCP tools render inline alongside the agent's other tools below — the
  // backend doesn't expose real per-server identity for them (mcp_server_id
  // is a synthetic placeholder), so there's nothing meaningful to group or
  // gate behind a separate "server" entry.
  // Also filter out internal search tool for basic users when there are no connectors
  // Also filter out tools that are not chat-selectable (e.g., OpenURL)
  const displayTools = selectedAgent.tools.filter((tool) => {
    // Filter out tools that are not chat-selectable (visibility set by backend)
    if (!tool.chat_selectable) return false;

    // Always hide File Reader from the actions popover
    if (tool.in_code_tool_id === FILE_READER_TOOL_ID) return false;

    // Special handling for Project Search
    // Ensure Project Search is hidden if no files exist
    if (tool.in_code_tool_id === SEARCH_TOOL_ID && !!currentProjectId) {
      if (!allCurrentProjectFiles || allCurrentProjectFiles.length === 0) {
        return false;
      }
      // If files exist, show it (even if backend thinks it's strictly unavailable due to no connectors)
      return true;
    }

    // Advertise to admin/curator users that they can connect an internal search tool
    // even if it's not available or has no connectors
    if (tool.in_code_tool_id === SEARCH_TOOL_ID && (isAdmin || isCurator)) {
      return true;
    }

    // Filter out internal search tool for non-admin/curator users when there are no connectors
    if (
      tool.in_code_tool_id === SEARCH_TOOL_ID &&
      hasNoConnectors &&
      !isAdmin &&
      !isCurator
    ) {
      return false;
    }

    return true;
  });

  const searchToolId =
    displayTools.find((tool) => tool.in_code_tool_id === SEARCH_TOOL_ID)?.id ??
    null;

  // Filter tools based on search term
  const filteredTools = displayTools.filter((tool) => {
    if (!searchTerm) return true;
    const searchLower = searchTerm.toLowerCase();
    return (
      tool.display_name?.toLowerCase().includes(searchLower) ||
      tool.name.toLowerCase().includes(searchLower) ||
      tool.description?.toLowerCase().includes(searchLower)
    );
  });

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (newOpen) {
      setSecondaryView(null);
      setSearchTerm("");
    }
  };

  const configuredSources = getConfiguredSources(availableSources);

  const numSourcesEnabled = configuredSources.filter((source) =>
    isSourceEnabled(source.uniqueKey)
  ).length;
  const searchToolDisabled =
    searchToolId !== null && disabledToolIds.includes(searchToolId);

  // Sync search tool state with sources on mount/when states change
  useEffect(() => {
    if (searchToolId === null || !sourcesInitialized) return;

    const hasEnabledSources = numSourcesEnabled > 0;
    if (hasEnabledSources && searchToolDisabled) {
      // Sources are enabled but search tool is disabled - enable it
      toggleToolForCurrentAgent(searchToolId);
    } else if (!hasEnabledSources && !searchToolDisabled) {
      // No sources enabled but search tool is enabled - disable it
      toggleToolForCurrentAgent(searchToolId);
    }
  }, [
    searchToolId,
    numSourcesEnabled,
    searchToolDisabled,
    sourcesInitialized,
    toggleToolForCurrentAgent,
  ]);

  // Set search tool to a specific enabled/disabled state (only toggles if needed)
  const setSearchToolEnabled = (enabled: boolean) => {
    if (searchToolId === null) return;

    if (enabled && searchToolDisabled) {
      toggleToolForCurrentAgent(searchToolId);
    } else if (!enabled && !searchToolDisabled) {
      toggleToolForCurrentAgent(searchToolId);
    }
  };

  const handleSourceToggle = (sourceUniqueKey: string) => {
    const willEnable = !isSourceEnabled(sourceUniqueKey);
    const newEnabledCount = numSourcesEnabled + (willEnable ? 1 : -1);

    toggleSource(sourceUniqueKey);
    setSearchToolEnabled(newEnabledCount > 0);
  };

  const handleDisableAllSources = () => {
    disableAllSources();
    setSearchToolEnabled(false);
  };

  const handleEnableAllSources = () => {
    enableAllSources();
    setSearchToolEnabled(true);
  };

  const handleToggleTool = (toolId: number) => {
    const wasDisabled = disabledToolIds.includes(toolId);
    toggleToolForCurrentAgent(toolId);

    if (toolId === searchToolId) {
      if (wasDisabled) {
        // Enabling - restore previous sources or enable all (no persistence)
        const previous = previouslyEnabledSourcesRef.current;
        if (previous.length > 0) {
          setSelectedSources(previous);
        } else {
          setSelectedSources(configuredSources);
        }
        previouslyEnabledSourcesRef.current = [];
      } else {
        // Disabling - store current sources then disable all (no persistence)
        previouslyEnabledSourcesRef.current = [...selectedSources];
        setSelectedSources([]);
      }
    }
  };

  // Only show sources the agent has access to
  const accessibleConfiguredSources = configuredSources.filter(
    (source) =>
      agentAccessibleSources === null ||
      agentAccessibleSources.has(source.uniqueKey)
  );

  const sourceToggleItems: SwitchListItem[] = accessibleConfiguredSources.map(
    (source) => ({
      id: source.uniqueKey,
      label: source.displayName,
      leading: <SourceIcon sourceType={source.internalName} iconSize={16} />,
      isEnabled: isSourceEnabled(source.uniqueKey),
      onToggle: () => handleSourceToggle(source.uniqueKey),
    })
  );

  const allSourcesDisabled = configuredSources.every(
    (source) => !isSourceEnabled(source.uniqueKey)
  );

  // Count enabled sources for display (only accessible sources)
  const enabledSourceCount = accessibleConfiguredSources.filter((source) =>
    isSourceEnabled(source.uniqueKey)
  ).length;
  const totalSourceCount = accessibleConfiguredSources.length;

  const primaryView = (
    <PopoverMenu>
      {[
        <InputTypeIn
          key="search"
          placeholder={t("inputBar.searchActionsPlaceholder")}
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          autoFocus
          variant="internal"
        />,

        // Actions
        ...filteredTools.map((tool) =>
          (() => {
            if (
              !tool.in_code_tool_id ||
              !CONFIGURABLE_SYSTEM_TOOL_IDS.has(tool.in_code_tool_id)
            ) {
              return <StaticToolListItem key={tool.id} tool={tool} />;
            }

            const isToolAvailable = availableToolNameSet.has(tool.name);
            const isUnavailable =
              !isToolAvailable && tool.in_code_tool_id !== SEARCH_TOOL_ID;
            const canAdminConfigure = isAdmin || isCurator;
            const adminConfigureInfo =
              isUnavailable && canAdminConfigure
                ? getAdminConfigureInfo(tool)
                : null;
            return (
              <ActionLineItem
                key={tool.id}
                tool={tool}
                disabled={disabledToolIds.includes(tool.id)}
                isForced={forcedToolIds.includes(tool.id)}
                isUnavailable={isUnavailable}
                unavailableReason={
                  isUnavailable
                    ? getUnavailableToolTooltip(
                        tool.in_code_tool_id,
                        canAdminConfigure
                      )
                    : undefined
                }
                showAdminConfigure={!!adminConfigureInfo}
                adminConfigureHref={adminConfigureInfo?.href}
                adminConfigureTooltip={adminConfigureInfo?.tooltip}
                onToggle={() => handleToggleTool(tool.id)}
                onForceToggle={() =>
                  handleForceToggleWithTracking(
                    tool.id,
                    forcedToolIds.includes(tool.id)
                  )
                }
                onSourceManagementOpen={() =>
                  setSecondaryView({ type: "sources" })
                }
                hasNoConnectors={hasNoConnectors}
                toolAuthStatus={getToolAuthStatus(tool)}
                onOAuthAuthenticate={() => authenticateTool(tool)}
                onClose={() => setOpen(false)}
                sourceCounts={{
                  enabled: enabledSourceCount,
                  total: totalSourceCount,
                }}
              />
            );
          })()
        ),

        null,

        (isAdmin || isCurator) && (
          <LineItem href="/admin/actions" icon={SvgActions} key="more-actions">
            {t("inputBar.moreActionsButton")}
          </LineItem>
        ),
      ]}
    </PopoverMenu>
  );

  const toolsView = (
    <SwitchList
      items={sourceToggleItems}
      searchPlaceholder="Search Filters"
      allDisabled={allSourcesDisabled}
      onDisableAll={handleDisableAllSources}
      onEnableAll={handleEnableAllSources}
      disableAllLabel="Disable All Sources"
      enableAllLabel="Enable All Sources"
      onBack={() => setSecondaryView(null)}
    />
  );

  // If no tools are available, don't render the component
  if (displayTools.length === 0) return null;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <Popover.Trigger asChild>
        <div data-testid="action-management-toggle">
          <Button
            icon={SvgSliders}
            transient={open}
            prominence="tertiary"
            tooltip={t("inputBar.manageActionsTooltip")}
            disabled={disabled}
          />
        </div>
      </Popover.Trigger>
      <Popover.Content side="bottom" align="start" width="lg">
        <div data-testid="tool-options">
          {secondaryView ? toolsView : primaryView}
        </div>
      </Popover.Content>
    </Popover>
  );
}

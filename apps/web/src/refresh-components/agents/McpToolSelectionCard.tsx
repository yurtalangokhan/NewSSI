"use client";

import { useMemo, useState } from "react";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import Truncated from "@/refresh-components/texts/Truncated";
import { Card } from "@/refresh-components/cards";
import { Section } from "@/layouts/general-layouts";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import { MCPServer, ToolSnapshot } from "@/lib/tools/interfaces";
import {
  SvgActions,
  SvgCheck,
  SvgChevronDown,
  SvgSliders,
  SvgX,
} from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface SelectableMcpTool {
  id?: number | string;
  name: string;
  display_name?: string;
  description?: string;
  mcp_server_id?: number | null;
  enabled?: boolean;
  agent_creation_selectable?: boolean;
  isAvailable?: boolean;
}

export interface ToolSelectionGroup {
  id: string;
  title: string;
  description?: string;
  tools?: SelectableMcpTool[];
  children?: ToolSelectionGroup[];
  kind?: "server" | "builtin-root" | "builtin-category";
}

interface BuildToolSelectionGroupsArgs {
  mcpTools?: SelectableMcpTool[];
  mcpServers?: MCPServer[];
  serviceToolsByCategory?: Record<string, SelectableMcpTool[]>;
  categoryLabelMap?: Record<string, string>;
}

interface BuildMcpOnlyToolSelectionGroupsArgs {
  tools?: SelectableMcpTool[];
  mcpServers?: MCPServer[];
}

export function isToolSelectable(tool: SelectableMcpTool) {
  if (tool.isAvailable === false) {
    return false;
  }
  if (tool.enabled === false) {
    return false;
  }
  if (tool.agent_creation_selectable === false) {
    return false;
  }
  return true;
}

export function buildToolSelectionGroups({
  mcpTools = [],
  mcpServers = [],
  serviceToolsByCategory = {},
  categoryLabelMap = {},
}: BuildToolSelectionGroupsArgs): ToolSelectionGroup[] {
  const serverMap = new Map(mcpServers.map((server) => [server.id, server]));
  const mcpGroups = new Map<number | string, ToolSelectionGroup>();

  for (const tool of mcpTools) {
    const serverId = tool.mcp_server_id ?? "unassigned";
    if (!mcpGroups.has(serverId)) {
      const server =
        typeof serverId === "number" ? serverMap.get(serverId) : null;
      mcpGroups.set(serverId, {
        id: `mcp-${serverId}`,
        title: server?.name ?? "MCP tools",
        description: server?.description,
        kind: "server",
        tools: [],
      });
    }
    mcpGroups.get(serverId)!.tools!.push(tool);
  }

  const serviceGroups: ToolSelectionGroup[] = Object.keys(
    serviceToolsByCategory
  )
    .sort((a, b) =>
      (categoryLabelMap[a] ?? a).localeCompare(categoryLabelMap[b] ?? b)
    )
    .map((category) => ({
      id: `service-${category}`,
      title: categoryLabelMap[category] ?? category,
      kind: "builtin-category" as const,
      tools: serviceToolsByCategory[category] ?? [],
    }))
    .filter((group) => (group.tools ?? []).length > 0);

  return [...Array.from(mcpGroups.values()), ...serviceGroups];
}

export function buildMcpOnlyToolSelectionGroups({
  tools = [],
  mcpServers = [],
}: BuildMcpOnlyToolSelectionGroupsArgs): ToolSelectionGroup[] {
  return buildToolSelectionGroups({
    mcpTools: tools.filter(
      (tool) => tool.mcp_server_id !== null && tool.mcp_server_id !== undefined
    ),
    mcpServers,
  });
}

function collectToolNames(groups: ToolSelectionGroup[]): string[] {
  return groups.flatMap((group) => [
    ...(group.tools ?? []).map((tool) => tool.name),
    ...collectToolNames(group.children ?? []),
  ]);
}

function filterGroup(
  group: ToolSelectionGroup,
  normalizedQuery: string
): ToolSelectionGroup | null {
  if (group.children) {
    const kids = group.children
      .map((child) => filterGroup(child, normalizedQuery))
      .filter((child): child is ToolSelectionGroup => child !== null);
    return kids.length ? { ...group, children: kids } : null;
  }
  const tools = (group.tools ?? []).filter((tool) => {
    const haystack = `${tool.display_name ?? ""} ${tool.name} ${
      tool.description ?? ""
    }`.toLowerCase();
    return haystack.includes(normalizedQuery);
  });
  return tools.length ? { ...group, tools } : null;
}

export function countSelectedTools(
  groups: ToolSelectionGroup[],
  selectedToolNames: string[]
) {
  const availableNames = new Set(collectToolNames(groups));
  return selectedToolNames.filter((name) => availableNames.has(name)).length;
}

/** Flatten every tool across a (possibly nested) group tree. */
export function flattenGroupTools(
  groups: ToolSelectionGroup[]
): SelectableMcpTool[] {
  return groups.flatMap((group) => [
    ...(group.tools ?? []),
    ...flattenGroupTools(group.children ?? []),
  ]);
}

function ToolSelectionGroupTree({
  groups,
  depth,
  forceOpen,
  selectedSet,
  setToolSelected,
}: {
  groups: ToolSelectionGroup[];
  depth: number;
  forceOpen: boolean;
  selectedSet: Set<string>;
  setToolSelected: (name: string, selected: boolean) => void;
}) {
  return (
    <div className={cn("flex flex-col gap-1", depth > 0 && "pl-4")}>
      {groups.map((group) => {
        const total = collectToolNames([group]).length;
        return (
          <Collapsible
            key={group.id}
            defaultOpen
            open={forceOpen ? true : undefined}
          >
            <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left hover:bg-background-neutral-00">
              <SvgChevronDown className="size-4 shrink-0 stroke-text-03 transition-transform group-data-[state=closed]:-rotate-90" />
              <Text mainUiBody>{group.title}</Text>
              <Text secondaryBody text03>
                ({total})
              </Text>
            </CollapsibleTrigger>
            <CollapsibleContent>
              {group.children ? (
                <ToolSelectionGroupTree
                  groups={group.children}
                  depth={depth + 1}
                  forceOpen={forceOpen}
                  selectedSet={selectedSet}
                  setToolSelected={setToolSelected}
                />
              ) : (
                <div className="flex flex-col gap-1 pl-6 pt-1">
                  {(group.tools ?? []).map((tool) => {
                    const selectable = isToolSelectable(tool);
                    const checked = selectedSet.has(tool.name);
                    return (
                      <label
                        key={`${group.id}-${tool.name}`}
                        className={cn(
                          "flex cursor-pointer items-start gap-2 rounded-08 border border-border-02 bg-background-neutral-00 px-3 py-2",
                          !selectable && "cursor-not-allowed opacity-60"
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          disabled={!selectable}
                          onCheckedChange={(nextChecked) =>
                            setToolSelected(tool.name, nextChecked)
                          }
                        />
                        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <Truncated secondaryBody>
                            {tool.display_name || tool.name}
                          </Truncated>
                          <Truncated secondaryBody text03>
                            {tool.description || tool.name}
                          </Truncated>
                        </div>
                        {checked && (
                          <SvgCheck className="mt-0.5 h-4 w-4 shrink-0 stroke-action-link-05" />
                        )}
                      </label>
                    );
                  })}
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>
        );
      })}
    </div>
  );
}

interface McpToolSelectionCardProps {
  title: string;
  description?: string;
  groups: ToolSelectionGroup[];
  selectedToolNames: string[];
  onSelectedToolNamesChange: (toolNames: string[]) => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export default function McpToolSelectionCard({
  title,
  description,
  groups,
  selectedToolNames,
  onSelectedToolNamesChange,
  disabled = false,
  isLoading = false,
}: McpToolSelectionCardProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selectedSet = useMemo(
    () => new Set(selectedToolNames),
    [selectedToolNames]
  );
  const selectedCount = countSelectedTools(groups, selectedToolNames);

  const filteredGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return groups;
    }
    return groups
      .map((group) => filterGroup(group, normalizedQuery))
      .filter((group): group is ToolSelectionGroup => group !== null);
  }, [groups, query]);

  function setToolSelected(toolName: string, selected: boolean) {
    const next = new Set(selectedSet);
    if (selected) {
      next.add(toolName);
    } else {
      next.delete(toolName);
    }
    onSelectedToolNamesChange(Array.from(next).sort());
  }

  function clearSelection() {
    onSelectedToolNamesChange([]);
  }

  return (
    <>
      <Card variant="secondary" padding={1}>
        <Section
          flexDirection="row"
          justifyContent="between"
          alignItems="center"
          gap={1}
        >
          <Section gap={0.25} alignItems="start">
            <Text mainUiBody>{title}</Text>
            {description && (
              <Text secondaryBody text03>
                {description}
              </Text>
            )}
            <Text secondaryBody text03>
              {isLoading
                ? t("agentEditor.mcpToolsChecking", "Checking tools")
                : t("agentEditor.mcpToolsSelectedCount", {
                    count: selectedCount,
                    defaultValue: `${selectedCount} selected`,
                  })}
            </Text>
          </Section>
          <Button
            rightIcon={SvgSliders}
            onClick={() => setOpen(true)}
            disabled={disabled || isLoading}
          >
            {t("agentEditor.selectToolsButton", "Select tools")}
          </Button>
        </Section>
      </Card>

      <Modal open={open} onOpenChange={setOpen}>
        <Modal.Content width="sm" height="lg">
          <Modal.Header
            icon={SvgActions}
            title={title}
            description={description}
            onClose={() => setOpen(false)}
          />
          <Modal.Body>
            <Section gap={1} alignItems="stretch">
              <InputTypeIn
                leftSearchIcon
                variant="internal"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t("agentEditor.searchToolsPlaceholder")}
              />

              {groups.length === 0 ? (
                <EmptyMessage
                  title={t("agentEditor.noMcpToolsTitle", "No MCP tools")}
                  description={t(
                    "agentEditor.noMcpToolsDescription",
                    "Connect an MCP server or enable tools-service tools first."
                  )}
                />
              ) : filteredGroups.length === 0 ? (
                <EmptyMessage
                  title={t("agentEditor.noToolsFoundTitle", "No tools found")}
                  description={t(
                    "agentEditor.noToolsFoundDescription",
                    "Try a different search term."
                  )}
                />
              ) : (
                <div className="flex max-h-[28rem] flex-col gap-1 overflow-y-auto pr-1">
                  <ToolSelectionGroupTree
                    groups={filteredGroups}
                    depth={0}
                    forceOpen={query.trim().length > 0}
                    selectedSet={selectedSet}
                    setToolSelected={setToolSelected}
                  />
                </div>
              )}

              <Section flexDirection="row" justifyContent="end" gap={0.5}>
                <Button
                  rightIcon={SvgX}
                  onClick={clearSelection}
                  disabled={selectedCount === 0}
                >
                  {t("agentEditor.clearToolsButton", "Clear")}
                </Button>
                <Button main onClick={() => setOpen(false)}>
                  {t("agentEditor.applyToolsButton", "Apply")}
                </Button>
              </Section>
            </Section>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    </>
  );
}

export function toSelectableTool(tool: ToolSnapshot): SelectableMcpTool {
  return {
    id: tool.id,
    // For external MCP tools the selection identity is the server-scoped
    // qualified name; the raw name is kept only for display.
    name: tool.qualified_name || tool.name,
    display_name: tool.display_name || tool.name,
    description: tool.description,
    mcp_server_id: tool.mcp_server_id,
    enabled: tool.enabled,
    agent_creation_selectable: tool.agent_creation_selectable,
  };
}

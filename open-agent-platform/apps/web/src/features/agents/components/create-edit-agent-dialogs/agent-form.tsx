import React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Search } from "@/components/ui/tool-search";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ConfigField,
  ConfigFieldAgents,
  ConfigFieldRAG,
  ConfigFieldTool,
  ConfigFieldSubAgents,
  ConfigFieldSubAgentsConfig,
  ConfigFieldPipelineStages,
} from "@/features/chat/components/configuration-sidebar/config-field";
import { useSearchTools } from "@/hooks/use-search-tools";
import { useMCPContext } from "@/providers/MCP";
import {
  ConfigurableFieldAgentsMetadata,
  ConfigurableFieldMCPMetadata,
  ConfigurableFieldRAGMetadata,
  ConfigurableFieldUIMetadata,
  ConfigurableFieldSubAgentsMetadata,
  ConfigurableFieldSubAgentsConfigMetadata,
  ConfigurableFieldPipelineStagesMetadata,
} from "@/types/configurable";
import { groupToolsByCategory, buildCategoryLabelMap } from "@/types/tool";
import _ from "lodash";
import { ChevronDown } from "lucide-react";
import { useFetchPreselectedTools } from "@/hooks/use-fetch-preselected-tools";
import { Controller, useFormContext } from "react-hook-form";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

export function AgentFieldsFormLoading() {
  return (
    <div className="flex w-full flex-col items-start justify-start gap-2 space-y-2">
      {Array.from({ length: 2 }).map((_, index) => (
        <div
          key={`loading-${index}`}
          className="flex w-full flex-col items-start justify-start gap-2"
        >
          <Skeleton className="h-10 w-[85%]" />
          <Skeleton className="h-16 w-full" />
        </div>
      ))}
    </div>
  );
}

interface AgentFieldsFormProps {
  configurations: ConfigurableFieldUIMetadata[];
  toolConfigurations: ConfigurableFieldMCPMetadata[];
  agentId: string;
  ragConfigurations: ConfigurableFieldRAGMetadata[];
  agentsConfigurations: ConfigurableFieldAgentsMetadata[];
  subAgentsConfigurations: ConfigurableFieldSubAgentsMetadata[];
  subAgentsConfigConfigurations: ConfigurableFieldSubAgentsConfigMetadata[];
  pipelineStagesConfigurations: ConfigurableFieldPipelineStagesMetadata[];
}

export function AgentFieldsForm({
  configurations,
  toolConfigurations,
  agentId,
  ragConfigurations,
  agentsConfigurations,
  subAgentsConfigurations,
  subAgentsConfigConfigurations,
  pipelineStagesConfigurations,
}: AgentFieldsFormProps) {
  const form = useFormContext<{
    name: string;
    description: string;
    config: Record<string, any>;
  }>();

  const { tools, setTools, getTools, cursor, loading } = useMCPContext();
  const { toolSearchTerm, debouncedSetSearchTerm, displayTools } =
    useSearchTools(tools, {
      preSelectedTools: toolConfigurations[0]?.default?.tools,
    });

  const { loadingMore, setLoadingMore } = useFetchPreselectedTools({
    tools,
    setTools,
    getTools,
    cursor,
    toolConfigurations,
    searchTerm: toolSearchTerm,
  });

  const groupedDisplayTools = React.useMemo(
    () => groupToolsByCategory(displayTools),
    [displayTools],
  );
  const categoryLabelMap = React.useMemo(
    () => buildCategoryLabelMap(displayTools),
    [displayTools],
  );
  const sortedCategories = React.useMemo(
    () =>
      Object.keys(groupedDisplayTools).sort((a, b) => {
        if (a === "other") return 1;
        if (b === "other") return -1;
        const labelA = categoryLabelMap[a] || _.startCase(a);
        const labelB = categoryLabelMap[b] || _.startCase(b);
        return labelA.localeCompare(labelB);
      }),
    [groupedDisplayTools, categoryLabelMap],
  );

  return (
    <div className="flex flex-col gap-8 py-4">
      <div className="flex w-full flex-col items-start justify-start gap-2 space-y-2">
        <p className="text-lg font-semibold tracking-tight">Agent Details</p>
        <div className="flex w-full flex-col items-start justify-start gap-2">
          <Label htmlFor="oap_name">
            Name <span className="text-red-500">*</span>
          </Label>
          <Input
            id="oap_name"
            {...form.register("name")}
            placeholder="Emails Agent"
          />
        </div>
        <div className="flex w-full flex-col items-start justify-start gap-2">
          <Label htmlFor="oap_description">
            Description <span className="text-red-500">*</span>
          </Label>
          <Textarea
            id="oap_description"
            {...form.register("description")}
            placeholder="Agent that handles emails"
          />
        </div>
      </div>

      <>
        {configurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-2 space-y-2">
              <p className="text-lg font-semibold tracking-tight">
                Agent Configuration
              </p>
              {configurations.map((c, index) => (
                <Controller
                  key={`${c.label}-${index}`}
                  control={form.control}
                  name={`config.${c.label}`}
                  render={({ field: { value, onChange } }) => (
                    <ConfigField
                      className="w-full"
                      id={c.label}
                      label={c.label}
                      type={
                        c.type === "boolean" ? "switch" : (c.type ?? "text")
                      }
                      description={c.description}
                      placeholder={c.placeholder}
                      options={c.options}
                      min={c.min}
                      max={c.max}
                      step={c.step}
                      value={value}
                      setValue={onChange}
                      agentId={agentId}
                    />
                  )}
                />
              ))}
            </div>
          </>
        )}
        {toolConfigurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-4">
              <p className="text-lg font-semibold tracking-tight">
                Agent Tools
              </p>
              <Search
                onSearchChange={debouncedSetSearchTerm}
                placeholder="Search tools..."
                className="w-full"
              />
              <div className="relative w-full flex-1 basis-[500px] rounded-md border-[1px] border-slate-200 px-4">
                <div className="absolute inset-0 overflow-y-auto px-4">
                  {toolConfigurations[0]?.label
                    ? sortedCategories.map((category) => (
                        <Collapsible
                          key={`cat-${category}`}
                          defaultOpen={true}
                        >
                          <CollapsibleTrigger className="group flex w-full items-center gap-2 border-b py-3 hover:bg-slate-50">
                            <ChevronDown className="size-3.5 transition-transform group-data-[state=closed]:-rotate-90" />
                            <span className="text-sm font-semibold">
                              {categoryLabelMap[category] || _.startCase(category)}
                            </span>
                            <Badge
                              variant="secondary"
                              className="ml-1 text-xs"
                            >
                              {groupedDisplayTools[category].length}
                            </Badge>
                          </CollapsibleTrigger>
                          <CollapsibleContent>
                            {groupedDisplayTools[category].map((c) => (
                              <Controller
                                key={`tool-${c.name}`}
                                control={form.control}
                                name={`config.${toolConfigurations[0].label}`}
                                render={({ field: { value, onChange } }) => (
                                  <ConfigFieldTool
                                    key={`tool-${c.name}`}
                                    id={c.name}
                                    label={c.name}
                                    description={c.description}
                                    agentId={agentId}
                                    toolId={toolConfigurations[0].label}
                                    className="border-b-[1px] py-4 pl-4"
                                    value={value}
                                    setValue={onChange}
                                  />
                                )}
                              />
                            ))}
                          </CollapsibleContent>
                        </Collapsible>
                      ))
                    : null}
                  {displayTools.length === 0 && toolSearchTerm && (
                    <p className="my-4 w-full text-center text-sm text-slate-500">
                      No tools found matching "{toolSearchTerm}".
                    </p>
                  )}
                  {tools.length === 0 && !toolSearchTerm && (
                    <p className="my-4 w-full text-center text-sm text-slate-500">
                      No tools available for this agent.
                    </p>
                  )}
                  {cursor && !toolSearchTerm && (
                    <div className="flex justify-center py-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={async () => {
                          try {
                            setLoadingMore(true);
                            const moreTool = await getTools(cursor);
                            setTools((prevTools) => [
                              ...prevTools,
                              ...moreTool,
                            ]);
                          } catch (error) {
                            console.error("Failed to load more tools:", error);
                          } finally {
                            setLoadingMore(false);
                          }
                        }}
                        disabled={loadingMore || loading}
                      >
                        {loadingMore ? "Loading..." : "Load More Tools"}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
        {ragConfigurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <p className="text-lg font-semibold tracking-tight">Agent RAG</p>
              <Controller
                control={form.control}
                name={`config.${ragConfigurations[0].label}`}
                render={({ field: { value, onChange } }) => (
                  <ConfigFieldRAG
                    id={ragConfigurations[0].label}
                    label={ragConfigurations[0].label}
                    agentId={agentId}
                    value={value}
                    setValue={onChange}
                  />
                )}
              />
            </div>
          </>
        )}
        {agentsConfigurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <p className="text-lg font-semibold tracking-tight">
                Supervisor Agents
              </p>
              <Controller
                control={form.control}
                name={`config.${agentsConfigurations[0].label}`}
                render={({ field: { value, onChange } }) => (
                  <ConfigFieldAgents
                    id={agentsConfigurations[0].label}
                    label={agentsConfigurations[0].label}
                    agentId={agentId}
                    value={value}
                    setValue={onChange}
                  />
                )}
              />
            </div>
          </>
        )}
        {subAgentsConfigurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <p className="text-lg font-semibold tracking-tight">
                Sub-Agents (Old - Select Agents)
              </p>
              <Controller
                control={form.control}
                name={`config.${subAgentsConfigurations[0].label}`}
                render={({ field: { value, onChange } }) => (
                  <ConfigFieldSubAgents
                    id={subAgentsConfigurations[0].label}
                    label={subAgentsConfigurations[0].label}
                    agentId={agentId}
                    value={value}
                    setValue={onChange}
                  />
                )}
              />
            </div>
          </>
        )}
        {subAgentsConfigConfigurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <p className="text-lg font-semibold tracking-tight">
                Sub-Agents (Parallel Execution)
              </p>
              <p className="text-sm text-muted-foreground">
                Configure agents that work in parallel. The supervisor will delegate tasks to one or more agents.
              </p>
              <Controller
                control={form.control}
                name={`config.${subAgentsConfigConfigurations[0].label}`}
                render={({ field: { value, onChange } }) => (
                  <ConfigFieldSubAgentsConfig
                    id={subAgentsConfigConfigurations[0].label}
                    label={subAgentsConfigConfigurations[0].label}
                    agentId={agentId}
                    mcpUrl={subAgentsConfigConfigurations[0].mcp_url}
                    modelOptions={subAgentsConfigConfigurations[0].model_options}
                    value={value}
                    setValue={onChange}
                  />
                )}
              />
            </div>
          </>
        )}
        {pipelineStagesConfigurations.length > 0 && (
          <>
            <Separator />
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <p className="text-lg font-semibold tracking-tight">
                Pipeline Stages (Hierarchy Supervisor)
              </p>
              <Controller
                control={form.control}
                name={`config.${pipelineStagesConfigurations[0].label}`}
                render={({ field: { value, onChange } }) => (
                  <ConfigFieldPipelineStages
                    id={pipelineStagesConfigurations[0].label}
                    label={pipelineStagesConfigurations[0].label}
                    agentId={agentId}
                    mcpUrl={pipelineStagesConfigurations[0].mcp_url}
                    modelOptions={pipelineStagesConfigurations[0].model_options}
                    value={value}
                    setValue={onChange}
                  />
                )}
              />
            </div>
          </>
        )}
      </>
    </div>
  );
}

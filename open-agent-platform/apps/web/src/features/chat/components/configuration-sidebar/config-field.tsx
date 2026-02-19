"use client";

import { useState, useEffect } from "react";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useRagContext } from "@/features/rag/providers/RAG";
import { useAuthContext } from "@/providers/Auth";
import { Check, ChevronsUpDown, AlertCircle, Plus, Trash2, GripVertical } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import _ from "lodash";
import { cn } from "@/lib/utils";
import {
  ConfigurableFieldAgentsMetadata,
  ConfigurableFieldMCPMetadata,
  ConfigurableFieldRAGMetadata,
  ConfigurableFieldSubAgentsMetadata,
  PipelineStage,
  SubAgentConfig,
} from "@/types/configurable";
import { AgentsCombobox } from "@/components/ui/agents-combobox";
import { useAgentsContext } from "@/providers/Agents";
import { getDeployments } from "@/lib/environment/deployments";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

interface Option {
  label: string;
  value: string;
}

interface ConfigFieldProps {
  id: string;
  label: string;
  type:
  | "text"
  | "textarea"
  | "number"
  | "switch"
  | "slider"
  | "select"
  | "json";
  description?: string;
  placeholder?: string;
  options?: Option[];
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  // Optional props for external state management
  value?: any;
  setValue?: (value: any) => void;
  agentId: string;
}

export function ConfigField({
  id,
  label,
  type,
  description,
  placeholder,
  options = [],
  min,
  max,
  step = 1,
  className,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
  agentId,
}: ConfigFieldProps) {
  const store = useConfigStore();
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Determine whether to use external state or Zustand store
  const isExternallyManaged = externalSetValue !== undefined;

  const currentValue = isExternallyManaged
    ? externalValue
    : store.configsByAgentId[agentId][id];

  const handleChange = (newValue: any) => {
    setJsonError(null); // Clear JSON error on any change
    if (isExternallyManaged && externalSetValue) {
      externalSetValue(newValue); // Use non-null assertion as we checked existence
    } else {
      store.updateConfig(agentId, id, newValue);
    }
  };

  const handleJsonChange = (jsonString: string) => {
    try {
      if (!jsonString.trim()) {
        handleChange(undefined); // Use the unified handleChange
        setJsonError(null);
        return;
      }

      // Attempt to parse for validation first
      const parsedJson = JSON.parse(jsonString);
      // If parsing succeeds, call handleChange with the raw string and clear error
      handleChange(parsedJson); // Use the unified handleChange
      setJsonError(null);
    } catch (_) {
      // If parsing fails, update state with invalid string but set error
      // This allows the user to see their invalid input and the error message
      if (isExternallyManaged && externalSetValue) {
        externalSetValue(jsonString);
      } else {
        store.updateConfig(agentId, id, jsonString);
      }
      setJsonError("Invalid JSON format");
    }
  };

  const handleFormatJson = (jsonString: string) => {
    try {
      const parsed = JSON.parse(jsonString);
      // Directly use handleChange to update with the formatted string
      handleChange(parsed);
      setJsonError(null); // Clear error on successful format
    } catch (_) {
      // If formatting fails (because input is not valid JSON), set the error state
      // Do not change the underlying value that failed to parse/format
      setJsonError("Invalid JSON format");
    }
  };

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between">
        <Label
          htmlFor={id}
          className="text-sm font-medium"
        >
          {_.startCase(label)}
        </Label>
        {type === "switch" && (
          <Switch
            id={id}
            checked={!!currentValue} // Use currentValue
            onCheckedChange={handleChange}
          />
        )}
      </div>

      {description && (
        <p className="text-xs whitespace-pre-line text-gray-500">
          {description}
        </p>
      )}

      {type === "text" && (
        <Input
          id={id}
          value={currentValue || ""} // Use currentValue
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
        />
      )}

      {type === "textarea" && (
        <Textarea
          id={id}
          value={currentValue || ""} // Use currentValue
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          className="min-h-[100px]"
        />
      )}

      {type === "number" && (
        <Input
          id={id}
          type="number"
          value={currentValue !== undefined ? currentValue : ""} // Use currentValue
          onChange={(e) => {
            // Handle potential empty string or invalid number input
            const val = e.target.value;
            if (val === "") {
              handleChange(undefined); // Treat empty string as clearing the value
            } else {
              const num = Number(val);
              // Only call handleChange if it's a valid number
              if (!isNaN(num)) {
                handleChange(num);
              }
              // If not a valid number (e.g., '1.2.3'), do nothing, keep the last valid state
            }
          }}
          min={min}
          max={max}
          step={step}
        />
      )}

      {type === "slider" && (
        <div className="pt-2">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs text-gray-500">{min ?? ""}</span>
            <span className="text-sm font-medium">
              {/* Use currentValue */}
              {currentValue !== undefined
                ? currentValue
                : min !== undefined && max !== undefined
                  ? (min + max) / 2
                  : ""}
            </span>
            <span className="text-xs text-gray-500">{max ?? ""}</span>
          </div>
          <Slider
            id={id}
            // Use currentValue, provide default based on min/max if undefined
            value={[
              currentValue !== undefined
                ? currentValue
                : min !== undefined && max !== undefined
                  ? (min + max) / 2
                  : 0,
            ]}
            min={min}
            max={max}
            step={step}
            onValueChange={(vals) => handleChange(vals[0])}
            disabled={min === undefined || max === undefined} // Disable slider if min/max not provided
          />
        </div>
      )}

      {type === "select" && (
        <Select
          value={currentValue ?? ""} // Use currentValue, provide default empty string if undefined/null
          onValueChange={handleChange}
        >
          <SelectTrigger>
            {/* Display selected value or placeholder */}
            <SelectValue placeholder={placeholder || "Select an option"} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {type === "json" && (
        <>
          <Textarea
            id={id}
            value={
              typeof currentValue === "string"
                ? currentValue
                : (JSON.stringify(currentValue, null, 2) ?? "")
            } // Use currentValue
            onChange={(e) => handleJsonChange(e.target.value)}
            placeholder={placeholder || '{\n  "key": "value"\n}'}
            className={cn(
              "min-h-[120px] font-mono text-sm",
              jsonError &&
              "border-red-500 focus:border-red-500 focus-visible:ring-red-500", // Add error styling
            )}
          />
          <div className="flex w-full items-start justify-between gap-2 pt-1">
            {" "}
            {/* Use items-start */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleFormatJson(currentValue ?? "")}
              // Disable if value is empty, not a string, or already has a JSON error
              disabled={
                !currentValue || typeof currentValue !== "string" || !!jsonError
              }
              className="mt-1" // Add margin top to align better with textarea
            >
              Format
            </Button>
            {jsonError && (
              <Alert
                variant="destructive"
                className="flex-grow px-3 py-1" // Adjusted styling
              >
                <div className="flex items-center gap-2">
                  {" "}
                  {/* Ensure icon and text are aligned */}
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />{" "}
                  {/* Added flex-shrink-0 */}
                  <AlertDescription className="text-xs">
                    {jsonError}
                  </AlertDescription>
                </div>
              </Alert>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function ConfigFieldTool({
  id,
  label,
  description,
  agentId,
  className,
  toolId,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
> & { toolId: string }) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:selected-tools`;

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[toolId]
  ) as ConfigurableFieldMCPMetadata["default"] | undefined;

  if (!defaults) {
    return null;
  }

  const checked = defaults.tools?.some((t) => t === label);

  const handleCheckedChange = (checked: boolean) => {
    const newValue = checked
      ? {
        ...defaults,
        // Remove duplicates
        tools: Array.from(
          new Set<string>([...(defaults.tools || []), label]),
        ),
      }
      : {
        ...defaults,
        tools: defaults.tools?.filter((t) => t !== label),
      };

    if (isExternallyManaged) {
      externalSetValue(newValue);
      return;
    }

    store.updateConfig(actualAgentId, toolId, newValue);
  };

  return (
    <div className={cn("w-full space-y-2", className)}>
      <div className="flex items-center justify-between">
        <Label
          htmlFor={id}
          className="text-sm font-medium"
        >
          {_.startCase(label)}
        </Label>
        <Switch
          id={id}
          checked={checked} // Use currentValue
          onCheckedChange={handleCheckedChange}
        />
      </div>

      {description && (
        <p className="text-xs whitespace-pre-line text-gray-500">
          {description}
        </p>
      )}
    </div>
  );
}

export function ConfigFieldRAG({
  id,
  label,
  agentId,
  className,
  graphOnly = false,
  ragOnly = false,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
}: Pick<
  ConfigFieldProps,
  "id" | "label" | "agentId" | "className" | "value" | "setValue"
> & { graphOnly?: boolean; ragOnly?: boolean }) {
  const { collections } = useRagContext();
  const { session } = useAuthContext();
  const store = useConfigStore();
  const actualAgentId = `${agentId}:rag`;
  const [open, setOpen] = useState(false);
  const [dataSources, setDataSources] = useState<Array<{ id: string; name: string; type: string }>>([]);
  const [graphCollectionIds, setGraphCollectionIds] = useState<Set<string>>(new Set());

  // Whether we need to know which collections have graphs
  const needsGraphIds = graphOnly;

  // Fetch data sources from agent API
  useEffect(() => {
    const fetchDataSources = async () => {
      try {
        const agentApiUrl = process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8123";
        const res = await fetch(`${agentApiUrl}/datasources`);
        if (res.ok) {
          const data = await res.json();
          setDataSources(data.map((ds: any) => ({
            id: ds.id,
            name: ds.name,
            type: ds.config?.type || "database"
          })));
        }
      } catch (error) {
        console.error("Failed to fetch data sources:", error);
      }
    };
    fetchDataSources();
  }, []);

  // Fetch graph collection IDs when we need to filter (graphOnly or ragOnly)
  useEffect(() => {
    if (!needsGraphIds) return;
    const fetchGraphIds = async () => {
      try {
        const ragApiUrl = process.env.NEXT_PUBLIC_RAG_API_URL || "http://localhost:8083";
        const headers: HeadersInit = {
          "Content-Type": "application/json",
        };
        if (session?.accessToken) {
          headers["Authorization"] = `Bearer ${session.accessToken}`;
        }
        const res = await fetch(`${ragApiUrl}/graph/collections`, { headers });
        if (res.ok) {
          const ids: string[] = await res.json();
          setGraphCollectionIds(new Set(ids));
        }
      } catch (error) {
        console.error("Failed to fetch graph collection IDs:", error);
      }
    };
    fetchGraphIds();
  }, [needsGraphIds, session?.accessToken]);

  // Filter collections and data sources based on mode:
  // - graphOnly: ONLY show collections WITH a knowledge graph
  // - ragOnly: show ALL collections (a collection with a graph still has vector
  //   embeddings and can be used for standard RAG)
  // - neither: show all
  const filteredCollections = graphOnly
    ? collections.filter((c) => graphCollectionIds.has(c.uuid))
    : collections;
  const filteredDataSources = graphOnly
    ? dataSources.filter((ds) => graphCollectionIds.has(ds.id))
    : dataSources;

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as ConfigurableFieldRAGMetadata["default"];

  if (!defaults) {
    return null;
  }

  const selectedCollections = defaults.collections?.length
    ? defaults.collections
    : [];

  const handleSelect = (collectionId: string) => {
    const newValue = selectedCollections.some((s) => s === collectionId)
      ? selectedCollections.filter((s) => s !== collectionId)
      : [...selectedCollections, collectionId];

    if (isExternallyManaged) {
      externalSetValue({
        ...defaults,
        collections: Array.from(new Set(newValue)),
      });
      return;
    }

    store.updateConfig(actualAgentId, label, {
      ...defaults,
      collections: Array.from(new Set(newValue)),
    });
  };

  const getCollectionNameFromId = (collectionId: string) => {
    // Check RAG collections first
    const collection = filteredCollections.find((c) => c.uuid === collectionId);
    if (collection) return collection.name;

    // Then check data sources
    const dataSource = filteredDataSources.find((ds) => ds.id === collectionId);
    if (dataSource) return `${dataSource.name} (${dataSource.type})`;

    return "Unknown Collection";
  };


  return (
    <div className={cn("flex w-full flex-col items-start gap-2", className)}>
      <Label
        htmlFor={id}
        className="text-sm font-medium"
      >
        {graphOnly ? "Graph Collections" : ragOnly ? "RAG Collections" : "Selected Collections & Data Sources"}
      </Label>
      <Popover
        open={open}
        onOpenChange={setOpen}
      >
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
          >
            {selectedCollections.length > 0
              ? selectedCollections.length > 1
                ? `${selectedCollections.length} selected`
                : getCollectionNameFromId(selectedCollections[0])
              : graphOnly
                ? "Select graph collections"
                : ragOnly
                  ? "Select RAG collections"
                  : "Select collections or data sources"}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-full p-0"
          align="start"
        >
          <Command className="w-full">
            <CommandInput placeholder="Search..." />
            <CommandList>
              <CommandEmpty>No items found.</CommandEmpty>
              {filteredCollections.length > 0 && (
                <CommandGroup heading="RAG Collections">
                  {filteredCollections.map((collection) => (
                    <CommandItem
                      key={collection.uuid}
                      value={collection.uuid}
                      onSelect={() => handleSelect(collection.uuid)}
                      className="flex items-center justify-between"
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4",
                          selectedCollections.includes(collection.uuid)
                            ? "opacity-100"
                            : "opacity-0",
                        )}
                      />
                      <p className="line-clamp-1 flex-1 truncate pr-2">
                        {collection.name}
                      </p>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              {filteredDataSources.length > 0 && (
                <CommandGroup heading="Data Sources">
                  {filteredDataSources.map((ds) => (
                    <CommandItem
                      key={ds.id}
                      value={ds.id}
                      onSelect={() => handleSelect(ds.id)}
                      className="flex items-center justify-between"
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4",
                          selectedCollections.includes(ds.id)
                            ? "opacity-100"
                            : "opacity-0",
                        )}
                      />
                      <p className="line-clamp-1 flex-1 truncate pr-2">
                        {ds.name}
                        <span className="ml-2 text-xs text-muted-foreground">({ds.type})</span>
                      </p>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export function ConfigFieldAgents({
  label,
  agentId,
  className,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
>) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:agents`;

  const { agents, loading } = useAgentsContext();
  const deployments = getDeployments();

  // Do not allow adding itself as a sub-agent
  const filteredAgents = agents.filter((a) => a.assistant_id !== agentId);

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as ConfigurableFieldAgentsMetadata["default"] | undefined;

  if (!defaults) {
    return null;
  }

  const handleSelectChange = (ids: string[]) => {
    if (!ids.length || ids.every((id) => !id)) {
      if (isExternallyManaged) {
        externalSetValue([]);
        return;
      }

      store.updateConfig(actualAgentId, label, []);
      return;
    }

    const newDefaults = ids.map((id) => {
      const [agent_id, deploymentId] = id.split(":");
      const deployment_url = deployments.find(
        (d) => d.id === deploymentId,
      )?.deploymentUrl;
      if (!deployment_url) {
        toast.error("Deployment not found");
      }

      return {
        agent_id,
        deployment_url,
        name: agents.find((a) => a.assistant_id === agent_id)?.name,
      };
    });

    if (isExternallyManaged) {
      externalSetValue(newDefaults);
      return;
    }

    store.updateConfig(actualAgentId, label, newDefaults);
  };

  return (
    <div className={cn("w-full space-y-2", className)}>
      <AgentsCombobox
        agents={filteredAgents}
        agentsLoading={loading}
        value={defaults.map(
          (defaultValue) =>
            `${defaultValue.agent_id}:${deployments.find((d) => d.deploymentUrl === defaultValue.deployment_url)?.id}`,
        )}
        setValue={(v) =>
          Array.isArray(v) ? handleSelectChange(v) : handleSelectChange([v])
        }
        multiple
        className="w-full"
      />

      <p className="text-xs text-gray-500">
        The agents to make available to this supervisor.
      </p>
    </div>
  );
}

/**
 * ConfigFieldSubAgents - For flat supervisor agent selection
 * Allows selecting multiple existing agents to be managed by a supervisor
 */
export function ConfigFieldSubAgents({
  label,
  agentId,
  className,
  value: externalValue,
  setValue: externalSetValue,
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
>) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:sub_agents`;

  const { agents, loading } = useAgentsContext();

  // Do not allow adding itself as a sub-agent
  const filteredAgents = agents.filter((a) => a.assistant_id !== agentId);

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as ConfigurableFieldSubAgentsMetadata["default"] | undefined;

  const selectedAgentIds = defaults || [];

  const handleSelectChange = (ids: string[]) => {
    if (!ids.length || ids.every((id) => !id)) {
      if (isExternallyManaged) {
        externalSetValue([]);
        return;
      }
      store.updateConfig(actualAgentId, label, []);
      return;
    }

    // For sub_agents, we store just the agent IDs
    const newDefaults = ids.map((id) => {
      const [agent_id] = id.split(":");
      return agent_id;
    });

    if (isExternallyManaged) {
      externalSetValue(newDefaults);
      return;
    }

    store.updateConfig(actualAgentId, label, newDefaults);
  };

  // Convert agent IDs to combo format for display
  const comboValue = selectedAgentIds.map((agentIdStr) => {
    const agent = agents.find((a) => a.assistant_id === agentIdStr);
    if (agent) {
      return `${agentIdStr}:${agent.deploymentId}`;
    }
    return agentIdStr;
  });

  return (
    <div className={cn("w-full space-y-2", className)}>
      <Label className="text-sm font-medium">Select Sub-Agents</Label>
      <AgentsCombobox
        agents={filteredAgents}
        agentsLoading={loading}
        value={comboValue}
        setValue={(v) =>
          Array.isArray(v) ? handleSelectChange(v) : handleSelectChange([v])
        }
        multiple
        className="w-full"
      />
      <p className="text-xs text-gray-500">
        Select agents that will be managed by this supervisor. Each agent brings its own tools and capabilities.
      </p>
    </div>
  );
}

/**
 * ConfigFieldPipelineStages - For hierarchy/pipeline supervisor configuration
 * Allows configuring sequential stages with custom prompts and MCP tools
 */
export function ConfigFieldPipelineStages({
  label,
  agentId,
  className,
  mcpUrl = "http://mcp-server:8001/mcp",
  modelOptions,
  value: externalValue,
  setValue: externalSetValue,
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
> & { mcpUrl?: string; modelOptions?: Array<{ label: string; value: string }> }) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:pipeline_stages`;

  const [availableTools, setAvailableTools] = useState<Array<{ name: string; description: string }>>([]);
  const [loadingTools, setLoadingTools] = useState(false);

  const isExternallyManaged = externalSetValue !== undefined;

  const stages = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as PipelineStage[] | undefined;

  const currentStages = stages || [];

  // Fetch available MCP tools
  useEffect(() => {
    const fetchTools = async () => {
      setLoadingTools(true);
      try {
        // Fetch from the MCP server's list tools endpoint
        const agentApiUrl = process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8123";
        const res = await fetch(`${agentApiUrl}/mcp/tools?url=${encodeURIComponent(mcpUrl)}`);
        if (res.ok) {
          const data = await res.json();
          setAvailableTools(data.tools || []);
        }
      } catch (error) {
        console.error("Failed to fetch MCP tools:", error);
      } finally {
        setLoadingTools(false);
      }
    };
    fetchTools();
  }, [mcpUrl]);

  const updateStages = (newStages: PipelineStage[]) => {
    if (isExternallyManaged) {
      externalSetValue(newStages);
      return;
    }
    store.updateConfig(actualAgentId, label, newStages);
  };

  const addStage = () => {
    const newStage: PipelineStage = {
      name: `Stage ${currentStages.length + 1}`,
      system_prompt: "You are a helpful assistant for this pipeline stage.",
      mcp_tools: [],
    };
    updateStages([...currentStages, newStage]);
  };

  const removeStage = (index: number) => {
    const newStages = currentStages.filter((_, i) => i !== index);
    updateStages(newStages);
  };

  const updateStage = (index: number, field: keyof PipelineStage, value: any) => {
    const newStages = [...currentStages];
    newStages[index] = { ...newStages[index], [field]: value };
    updateStages(newStages);
  };

  const toggleTool = (stageIndex: number, toolName: string) => {
    const stage = currentStages[stageIndex];
    const currentTools = stage.mcp_tools || [];
    const newTools = currentTools.includes(toolName)
      ? currentTools.filter((t) => t !== toolName)
      : [...currentTools, toolName];
    updateStage(stageIndex, "mcp_tools", newTools);
  };

  return (
    <div className={cn("w-full space-y-4", className)}>
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Pipeline Stages</Label>
        <Button
          variant="outline"
          size="sm"
          onClick={addStage}
          className="h-8"
        >
          <Plus className="mr-1 h-4 w-4" />
          Add Stage
        </Button>
      </div>
      
      <p className="text-xs text-gray-500">
        Configure sequential pipeline stages. Each stage runs in order, passing its output to the next stage.
      </p>

      {currentStages.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-8 text-center">
            <p className="text-sm text-muted-foreground">
              No stages configured yet. Click "Add Stage" to create your first pipeline stage.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Accordion type="multiple" className="space-y-2">
          {currentStages.map((stage, index) => (
            <AccordionItem
              key={index}
              value={`stage-${index}`}
              className="rounded-lg border px-4"
            >
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-2">
                  <GripVertical className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium">{stage.name || `Stage ${index + 1}`}</span>
                  <span className="text-xs text-muted-foreground">
                    ({stage.mcp_tools?.length || 0} tools)
                  </span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label className="text-xs">Stage Name</Label>
                  <Input
                    value={stage.name}
                    onChange={(e) => updateStage(index, "name", e.target.value)}
                    placeholder="Enter stage name..."
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs">System Prompt</Label>
                  <Textarea
                    value={stage.system_prompt}
                    onChange={(e) => updateStage(index, "system_prompt", e.target.value)}
                    placeholder="Enter the system prompt for this stage..."
                    className="min-h-[100px]"
                  />
                </div>

                {modelOptions && modelOptions.length > 0 && (
                  <div className="space-y-2">
                    <Label className="text-xs">Model</Label>
                    <p className="text-xs text-muted-foreground">
                      Optional. If not selected, the supervisor&apos;s model will be used.
                    </p>
                    <Select
                      value={stage.model || ""}
                      onValueChange={(val) => updateStage(index, "model", val || undefined)}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Use supervisor model (default)" />
                      </SelectTrigger>
                      <SelectContent>
                        {modelOptions.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {stage.model && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs text-muted-foreground"
                        onClick={() => updateStage(index, "model", undefined)}
                      >
                        Reset to supervisor model
                      </Button>
                    )}
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-xs">MCP Tools</Label>
                  {loadingTools ? (
                    <p className="text-xs text-muted-foreground">Loading tools...</p>
                  ) : availableTools.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No MCP tools available</p>
                  ) : (
                    <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-2">
                      {availableTools.map((tool) => (
                        <div
                          key={tool.name}
                          className="flex items-center justify-between rounded-md p-2 hover:bg-muted"
                        >
                          <div className="flex-1">
                            <p className="text-sm font-medium">{tool.name}</p>
                            {tool.description && (
                              <p className="text-xs text-muted-foreground line-clamp-1">
                                {tool.description}
                              </p>
                            )}
                          </div>
                          <Switch
                            checked={stage.mcp_tools?.includes(tool.name) || false}
                            onCheckedChange={() => toggleTool(index, tool.name)}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => removeStage(index)}
                  >
                    <Trash2 className="mr-1 h-4 w-4" />
                    Remove Stage
                  </Button>
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </div>
  );
}

/**
 * ConfigFieldSubAgentsConfig - For flat supervisor configuration
 * Allows configuring agents that work in PARALLEL (not sequential)
 * Each agent has a name, system prompt, and MCP tools
 */
export function ConfigFieldSubAgentsConfig({
  label,
  agentId,
  className,
  mcpUrl = "http://mcp-server:8001/mcp",
  modelOptions,
  value: externalValue,
  setValue: externalSetValue,
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
> & { mcpUrl?: string; modelOptions?: Array<{ label: string; value: string }> }) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:sub_agents_config`;

  const [availableTools, setAvailableTools] = useState<Array<{ name: string; description: string }>>([]);
  const [loadingTools, setLoadingTools] = useState(false);

  const isExternallyManaged = externalSetValue !== undefined;

  const agents = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as SubAgentConfig[] | undefined;

  const currentAgents = agents || [];

  // Fetch available MCP tools
  useEffect(() => {
    const fetchTools = async () => {
      setLoadingTools(true);
      try {
        const agentApiUrl = process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8123";
        const res = await fetch(`${agentApiUrl}/mcp/tools?url=${encodeURIComponent(mcpUrl)}`);
        if (res.ok) {
          const data = await res.json();
          setAvailableTools(data.tools || []);
        }
      } catch (error) {
        console.error("Failed to fetch MCP tools:", error);
      } finally {
        setLoadingTools(false);
      }
    };
    fetchTools();
  }, [mcpUrl]);

  const updateAgents = (newAgents: SubAgentConfig[]) => {
    if (isExternallyManaged) {
      externalSetValue(newAgents);
      return;
    }
    store.updateConfig(actualAgentId, label, newAgents);
  };

  const addAgent = () => {
    const newAgent: SubAgentConfig = {
      name: `agent-${currentAgents.length + 1}`,
      system_prompt: "You are a specialized assistant.",
      mcp_tools: [],
    };
    updateAgents([...currentAgents, newAgent]);
  };

  const removeAgent = (index: number) => {
    const newAgents = currentAgents.filter((_, i) => i !== index);
    updateAgents(newAgents);
  };

  const updateAgent = (index: number, field: keyof SubAgentConfig, value: any) => {
    const newAgents = [...currentAgents];
    newAgents[index] = { ...newAgents[index], [field]: value };
    updateAgents(newAgents);
  };

  const toggleTool = (agentIndex: number, toolName: string) => {
    const agent = currentAgents[agentIndex];
    const currentTools = agent.mcp_tools || [];
    const newTools = currentTools.includes(toolName)
      ? currentTools.filter((t) => t !== toolName)
      : [...currentTools, toolName];
    updateAgent(agentIndex, "mcp_tools", newTools);
  };

  return (
    <div className={cn("w-full space-y-4", className)}>
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Sub-Agents (Parallel)</Label>
        <Button
          variant="outline"
          size="sm"
          onClick={addAgent}
          className="h-8"
        >
          <Plus className="mr-1 h-4 w-4" />
          Add Agent
        </Button>
      </div>
      
      <p className="text-xs text-gray-500">
        Configure agents that work in <strong>parallel</strong>. The supervisor will delegate tasks to one or more agents based on the request.
      </p>

      {currentAgents.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-8 text-center">
            <p className="text-sm text-muted-foreground">
              No agents configured yet. Click "Add Agent" to create your first sub-agent.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Accordion type="multiple" className="space-y-2">
          {currentAgents.map((agent, index) => (
            <AccordionItem
              key={index}
              value={`agent-${index}`}
              className="rounded-lg border px-4"
            >
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-medium text-blue-700">
                    {index + 1}
                  </span>
                  <span className="font-medium">{agent.name || `Agent ${index + 1}`}</span>
                  <span className="text-xs text-muted-foreground">
                    ({agent.mcp_tools?.length || 0} tools)
                  </span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label className="text-xs">Agent Name</Label>
                  <Input
                    value={agent.name}
                    onChange={(e) => updateAgent(index, "name", e.target.value)}
                    placeholder="Enter agent name (e.g., pdf-analyzer)..."
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs">System Prompt</Label>
                  <Textarea
                    value={agent.system_prompt}
                    onChange={(e) => updateAgent(index, "system_prompt", e.target.value)}
                    placeholder="Enter the system prompt for this agent..."
                    className="min-h-[100px]"
                  />
                </div>

                {modelOptions && modelOptions.length > 0 && (
                  <div className="space-y-2">
                    <Label className="text-xs">Model</Label>
                    <p className="text-xs text-muted-foreground">
                      Optional. If not selected, the supervisor&apos;s model will be used.
                    </p>
                    <Select
                      value={agent.model || ""}
                      onValueChange={(val) => updateAgent(index, "model", val || undefined)}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Use supervisor model (default)" />
                      </SelectTrigger>
                      <SelectContent>
                        {modelOptions.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {agent.model && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs text-muted-foreground"
                        onClick={() => updateAgent(index, "model", undefined)}
                      >
                        Reset to supervisor model
                      </Button>
                    )}
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-xs">MCP Tools</Label>
                  {loadingTools ? (
                    <p className="text-xs text-muted-foreground">Loading tools...</p>
                  ) : availableTools.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No MCP tools available</p>
                  ) : (
                    <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-2">
                      {availableTools.map((tool) => (
                        <div
                          key={tool.name}
                          className="flex items-center justify-between rounded-md p-2 hover:bg-muted"
                        >
                          <div className="flex-1">
                            <p className="text-sm font-medium">{tool.name}</p>
                            {tool.description && (
                              <p className="text-xs text-muted-foreground line-clamp-1">
                                {tool.description}
                              </p>
                            )}
                          </div>
                          <Switch
                            checked={agent.mcp_tools?.includes(tool.name) || false}
                            onCheckedChange={() => toggleTool(index, tool.name)}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => removeAgent(index)}
                  >
                    <Trash2 className="mr-1 h-4 w-4" />
                    Remove Agent
                  </Button>
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </div>
  );
}

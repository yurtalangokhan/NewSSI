"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import Button from "@/refresh-components/buttons/Button";
import { Input } from "@/components/ui/input";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, ArrowLeft, Search } from "lucide-react";
import { toast } from "@/hooks/useToast";
import { cn } from "@/lib/utils";
import { BuiltInTool } from "@/lib/tools/interfaces";
import {
  getBuiltInTools,
  executeBuiltInTool,
  ToolExecuteResponse,
} from "@/lib/tools/mcpService";
import {
  buildCategoryLabelMap,
  groupToolsByCategory,
  parseToolCategory,
  ToolWithCategory,
} from "@/lib/tools/builtInToolUtils";
import _ from "lodash";

function getDefaultValueForSchema(schema: any): any {
  if (!schema) return null;
  if (schema.default !== undefined) return schema.default;

  switch (schema.type) {
    case "object":
      return getDefaultFormValues(schema);
    case "array":
      return [];
    case "boolean":
      return false;
    case "number":
    case "integer":
      return 0;
    default:
      return "";
  }
}

function getDefaultFormValues(schema: any): Record<string, any> {
  if (!schema || typeof schema !== "object") return {};
  const values: Record<string, any> = {};

  const properties = schema.properties || {};
  Object.entries(properties).forEach(([key, prop]: [string, any]) => {
    if (prop.default !== undefined) {
      values[key] = prop.default;
      return;
    }

    if (prop.type === "object" || prop.properties) {
      values[key] = getDefaultFormValues(prop);
      return;
    }

    if (prop.type === "array") {
      values[key] = [];
      return;
    }

    values[key] = getDefaultValueForSchema(prop);
  });

  return values;
}

function initializeFormValues(schema: any, values: Record<string, any>) {
  const normalizedSchema = normalizeSchema(schema);
  if (!normalizedSchema.properties) return values || {};
  return {
    ...getDefaultFormValues(normalizedSchema),
    ...(values || {}),
  };
}

function getValueAtPath(values: any, path: Array<string | number>) {
  return path.reduce((current, segment) => {
    if (current == null) return undefined;
    return current[segment];
  }, values);
}

function setValueAtPath(values: any, path: Array<string | number>, newValue: any): any {
  if (path.length === 0) return newValue;
  const head = path[0] as string | number;
  const tail = path.slice(1);
  return {
    ...values,
    [head]: tail.length
      ? setValueAtPath(values?.[head] ?? {}, tail, newValue)
      : newValue,
  };
}

function normalizeSchema(schema: any): any {
  if (!schema) {
    return { type: "object", properties: {} };
  }
  if (typeof schema !== "object") {
    return { type: "object", properties: {} };
  }
  if (!schema.properties) {
    return { ...schema, properties: {} };
  }
  return schema;
}

function SchemaForm({
  schema,
  values,
  onChange,
}: {
  schema: Record<string, any>;
  values: Record<string, any>;
  onChange: (values: Record<string, any>) => void;
}) {
  const [formValues, setFormValues] = useState<Record<string, any>>(
    initializeFormValues(schema, values),
  );

  const handleChange = (path: string[], value: any) => {
    const nextValues = setValueAtPath(formValues, path, value);
    setFormValues(nextValues);
    onChange(nextValues);
  };

  useEffect(() => {
    setFormValues(initializeFormValues(schema, values));
  }, [schema, values]);

  if (!schema || !schema.properties || Object.keys(schema.properties).length === 0) {
    return <div className="text-gray-500">No input parameters required</div>;
  }

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties).map(([name, property]: [string, any]) => {
        const isRequired = schema.required?.includes(name);
        const label = property.title || name;
        const description = property.description;

        return (
          <div key={name} className="space-y-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor={name}
                className={cn(
                  "text-sm font-medium",
                  isRequired && "after:ml-0.5 after:text-red-500 after:content-['*']",
                )}
              >
                {_.startCase(label)}
              </label>
              {isRequired && (
                <span className="text-xs text-gray-500">Required</span>
              )}
            </div>
            {description && (
              <p className="text-xs text-gray-500">{description}</p>
            )}
            {renderField(
              [name],
              property,
              formValues[name],
              (value: any) => handleChange([name], value),
            )}
          </div>
        );
      })}
    </div>
  );
}

function renderField(
  path: string[],
  property: any,
  value: any,
  onChange: (value: any) => void,
) {
  const fieldId = path.join(".");
  const label = property.title || path[path.length - 1];

  if (property.enum) {
    return (
      <select
        id={fieldId}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select an option</option>
        {property.enum.map((option: string) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (property.type === "object" || property.properties) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium">{_.startCase(label)}</div>
            {property.description && (
              <p className="text-xs text-gray-500">{property.description}</p>
            )}
          </div>
        </div>
        <SchemaForm
          schema={normalizeSchema(property)}
          values={value || {}}
          onChange={(nextValues) => onChange(nextValues)}
        />
      </div>
    );
  }

  if (property.type === "array" && property.items) {
    const items = Array.isArray(value) ? value : [];
    return (
      <div className="space-y-3">
        {items.map((item: any, index: number) => (
          <div
            key={`${fieldId}-${index}`}
            className="rounded-lg border border-gray-200 bg-white p-4"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-sm font-medium">Item {index + 1}</div>
              <Button
                secondary
                size="md"
                onClick={() => {
                  const nextItems = [...items];
                  nextItems.splice(index, 1);
                  onChange(nextItems);
                }}
              >
                Remove
              </Button>
            </div>
            {renderField(
              [...path, String(index)],
              property.items,
              item,
              (nextValue: any) => {
                const nextItems = [...items];
                nextItems[index] = nextValue;
                onChange(nextItems);
              },
            )}
          </div>
        ))}

        <Button
          secondary
          size="md"
          onClick={() => onChange([...items, getDefaultValueForSchema(property.items)])}
        >
          Add item
        </Button>
      </div>
    );
  }

  if (property.type === "string") {
    const isTextArea =
      property.format === "textarea" ||
      property.maxLength > 200 ||
      property.widget === "textarea";

    if (isTextArea) {
      return (
        <InputTextArea
          id={fieldId}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={property.example || `Enter ${_.startCase(label)}`}
          rows={5}
        />
      );
    }

    return (
      <Input
        id={fieldId}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={property.example || `Enter ${_.startCase(label)}`}
      />
    );
  }

  if (property.type === "number" || property.type === "integer") {
    if (property.minimum !== undefined && property.maximum !== undefined) {
      return (
        <div className="space-y-2">
          <Input
            id={fieldId}
            type="number"
            value={value ?? ""}
            onChange={(e) => onChange(Number(e.target.value))}
            min={property.minimum}
            max={property.maximum}
            step={property.type === "integer" ? 1 : 0.1}
            placeholder={property.example || `Enter ${_.startCase(label)}`}
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>{property.minimum}</span>
            <span>{value !== undefined ? value : "-"}</span>
            <span>{property.maximum}</span>
          </div>
        </div>
      );
    }

    return (
      <Input
        id={fieldId}
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        min={property.minimum}
        max={property.maximum}
        step={property.type === "integer" ? 1 : 0.1}
        placeholder={property.example || `Enter ${_.startCase(label)}`}
      />
    );
  }

  if (property.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <input
          id={fieldId}
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{value ? "Enabled" : "Disabled"}</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <InputTextArea
        id={fieldId}
        value={JSON.stringify(value ?? {}, null, 2)}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value));
          } catch {
            onChange(e.target.value);
          }
        }}
        placeholder={`Enter JSON for ${_.startCase(label)}`}
        rows={6}
      />
      <p className="text-xs text-gray-500">
        Unsupported field type. You can enter raw JSON here.
      </p>
    </div>
  );
}

function ResponseViewer({
  response,
  isLoading,
  error,
}: {
  response: any;
  isLoading: boolean;
  error: string | null;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-6 animate-spin mr-2" />
        <span>Executing tool...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
        <p className="font-semibold">Error</p>
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (!response) {
    return (
      <div className="text-center py-8 text-gray-500">
        Run the tool to see results
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-sm font-semibold text-emerald-700">Result</div>
      <pre className="max-h-[60vh] overflow-auto rounded-lg bg-gray-100 p-4 text-sm">
        {typeof response === "string"
          ? response
          : JSON.stringify(response, null, 2)}
      </pre>
    </div>
  );
}

export default function ToolsPlaygroundPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toolName = searchParams.get("tool") || "";

  const [tools, setTools] = useState<BuiltInTool[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [inputValues, setInputValues] = useState<Record<string, any>>({});
  const [response, setResponse] = useState<any>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    async function loadTools() {
      setIsLoading(true);
      try {
        const response = await getBuiltInTools();
        if (response.error) {
          setError(response.error);
          toast.error(response.error);
        } else {
          setTools(response.tools);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to fetch tools";
        setError(message);
        toast.error(message);
      } finally {
        setIsLoading(false);
      }
    }

    loadTools();
  }, []);

  const toolsWithCategory = useMemo(
    () => tools.map((tool) => parseToolCategory(tool)),
    [tools]
  );

  const filteredTools = useMemo(() => {
    if (!searchQuery.trim()) return toolsWithCategory;
    const query = searchQuery.toLowerCase();
    return toolsWithCategory.filter(
      (tool) =>
        tool.name.toLowerCase().includes(query) ||
        tool.description?.toLowerCase().includes(query) ||
        tool.category?.toLowerCase().includes(query)
    );
  }, [toolsWithCategory, searchQuery]);

  const groupedTools = useMemo(
    () => groupToolsByCategory(filteredTools),
    [filteredTools]
  );

  const categoryLabelMap = useMemo(
    () => buildCategoryLabelMap(filteredTools),
    [filteredTools]
  );

  const selectedTool = useMemo(
    () =>
      toolsWithCategory.find((tool) => tool.name === toolName) ?? null,
    [toolsWithCategory, toolName]
  );

  const handleSelectTool = useCallback(
    (tool: ToolWithCategory) => {
      setResponse(null);
      setRunError(null);
      setInputValues({});
      router.push(`/tools/playground?tool=${encodeURIComponent(tool.name)}`);
    },
    [router]
  );

  const handleRunTool = useCallback(async () => {
    if (!selectedTool) return;
    setIsRunning(true);
    setResponse(null);
    setRunError(null);

    try {
      const result: ToolExecuteResponse = await executeBuiltInTool(
        selectedTool.name,
        inputValues
      );
      if (result.error) {
        setRunError(result.error);
      } else {
        setResponse(result.result);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Tool execution failed";
      setRunError(message);
    } finally {
      setIsRunning(false);
    }
  }, [inputValues, selectedTool]);

  const pageTitle = selectedTool ? `${selectedTool.name} Playground` : "Tools Playground";

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Button secondary onClick={() => router.back()} className="px-3 py-2 text-sm">
            <ArrowLeft className="size-4 mr-2" /> Back
          </Button>
          <h1 className="mt-3 text-2xl font-bold">{pageTitle}</h1>
          <p className="mt-1 text-sm text-gray-600">
            Run built-in MCP tools with custom input and inspect the raw result.
          </p>
        </div>
        {selectedTool && (
          <Button onClick={handleRunTool} disabled={isRunning}>
            {isRunning ? (
              <>
                <Loader2 className="size-4 animate-spin mr-2" /> Running...
              </>
            ) : (
              "Run Tool"
            )}
          </Button>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold text-gray-900">Tool selector</div>
            <p className="text-sm text-gray-500">Choose a tool or search for one to open the playground.</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-gray-400" />
              <Input
                type="text"
                placeholder="Search tools..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            {toolsWithCategory.length > 0 && (
              <Select
                value={toolName}
                onValueChange={(value) => {
                  const tool = toolsWithCategory.find((t) => t.name === value);
                  if (tool) {
                    handleSelectTool(tool);
                  }
                }}
              >
                <SelectTrigger className="w-full sm:w-64">
                  <SelectValue placeholder="Select a tool..." />
                </SelectTrigger>
                <SelectContent>
                  {Object.keys(groupedTools).map((category) => (
                    <SelectItem key={category} value={category} disabled className="font-medium">
                      {categoryLabelMap[category] || _.startCase(category)}
                    </SelectItem>
                  ))}
                  {filteredTools.map((tool) => (
                    <SelectItem key={tool.name} value={tool.name}>
                      {tool.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-14">
          <Loader2 className="size-6 animate-spin mr-2" />
          <span>Loading tools...</span>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      ) : selectedTool ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(360px,1fr)_minmax(420px,560px)]">
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <div className="mb-4 space-y-2">
              <div className="text-sm font-semibold text-gray-900">{selectedTool.name}</div>
              <p className="text-sm text-gray-600">{selectedTool.description}</p>
            </div>
            <div className="space-y-6">
              <div>
                <div className="mb-3 text-sm font-semibold">Input</div>
                <SchemaForm
                  schema={normalizeSchema(selectedTool.input_schema)}
                  values={inputValues}
                  onChange={setInputValues}
                />
              </div>
              {runError && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
                  {runError}
                </div>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <div className="mb-4 text-sm font-semibold text-gray-900">Response</div>
            <ResponseViewer response={response} isLoading={isRunning} error={runError} />
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {filteredTools.length === 0 ? (
            <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-gray-600">
              No tools match your search.
            </div>
          ) : (
            Object.keys(groupedTools).map((category) => {
              const toolsInCategory = groupedTools[category] ?? [];
              return (
                <div key={category} className="rounded-lg border border-gray-200 bg-white p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        {categoryLabelMap[category] || _.startCase(category)}
                      </div>
                      <div className="text-xs text-gray-500">{toolsInCategory.length} tools</div>
                    </div>
                    <Badge variant="secondary">{toolsInCategory.length}</Badge>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {toolsInCategory.map((tool) => (
                      <div key={tool.name} className="rounded-lg border border-gray-200 p-4">
                        <div className="mb-2 text-sm font-semibold text-gray-900">{tool.name}</div>
                        <p className="mb-4 text-sm text-gray-600 line-clamp-3">{tool.description}</p>
                        <Button
                          secondary
                          onClick={() => handleSelectTool(tool)}
                          className="px-3 py-2 text-sm"
                        >
                          Open playground
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

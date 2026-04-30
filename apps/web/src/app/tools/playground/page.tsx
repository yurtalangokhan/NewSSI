"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Switch from "@/refresh-components/inputs/Switch";
import Text from "@/refresh-components/texts/Text";
import { ThreeDotsLoader } from "@/components/Loading";
import { SvgArrowLeft } from "@opal/icons";
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

function isFieldEmpty(value: any): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

function getMissingRequiredFields(schema: any, values: Record<string, any>): string[] {
  if (!schema?.required || !schema?.properties) return [];
  return schema.required.filter((field: string) => isFieldEmpty(values[field]));
}

function SchemaForm({
  schema,
  values,
  onChange,
  fieldErrors = {},
}: {
  schema: Record<string, any>;
  values: Record<string, any>;
  onChange: (values: Record<string, any>) => void;
  fieldErrors?: Record<string, string>;
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
    return <Text as="p" text03 mainContentBody>No input parameters required</Text>;
  }

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties).map(([name, property]: [string, any]) => {
        const isRequired = schema.required?.includes(name);
        const label = property.title || name;
        const description = property.description;
        const errorMsg = fieldErrors[name];

        return (
          <div key={name} className="space-y-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor={name}
                className={cn(
                  "text-sm font-medium text-text-04",
                  isRequired && "after:ml-0.5 after:text-status-error-05 after:content-['*']",
                )}
              >
                {_.startCase(label)}
              </label>
              {isRequired && (
                <Text as="span" text03 secondaryBody className="text-xs">Required</Text>
              )}
            </div>
            {description && (
              <Text as="p" text03 secondaryBody className="text-xs">{description}</Text>
            )}
            <div className={cn(errorMsg && "ring-1 ring-status-error-04 rounded-md")}>
              {renderField(
                [name],
                property,
                formValues[name],
                (value: any) => handleChange([name], value),
              )}
            </div>
            {errorMsg && (
              <Text as="p" className="text-xs text-status-error-05">{errorMsg}</Text>
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
        className="w-full rounded-08 border border-border-01 bg-background-tint-00 px-3 py-2 text-sm text-text-04 focus:outline-none focus:ring-1 focus:ring-theme-primary-04"
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
      <div className="rounded-lg border border-border-01 bg-background-tint-00 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <Text as="p" mainUiAction text04 className="text-sm font-medium">{_.startCase(label)}</Text>
            {property.description && (
              <Text as="p" text03 secondaryBody className="text-xs">{property.description}</Text>
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
            className="rounded-lg border border-border-01 bg-background-neutral-00 p-4"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <Text as="p" text04 mainUiAction className="text-sm font-medium">Item {index + 1}</Text>
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
      <InputTypeIn
        id={fieldId}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={property.example || `Enter ${_.startCase(label)}`}
        showClearButton={false}
      />
    );
  }

  if (property.type === "number" || property.type === "integer") {
    if (property.minimum !== undefined && property.maximum !== undefined) {
      return (
        <div className="space-y-2">
          <InputTypeIn
            id={fieldId}
            type="number"
            value={value ?? ""}
            onChange={(e) => onChange(Number(e.target.value))}
            min={property.minimum}
            max={property.maximum}
            step={property.type === "integer" ? 1 : 0.1}
            placeholder={property.example || `Enter ${_.startCase(label)}`}
            showClearButton={false}
          />
          <div className="flex justify-between text-xs text-text-03">
            <span>{property.minimum}</span>
            <span>{value !== undefined ? value : "-"}</span>
            <span>{property.maximum}</span>
          </div>
        </div>
      );
    }

    return (
      <InputTypeIn
        id={fieldId}
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        min={property.minimum}
        max={property.maximum}
        step={property.type === "integer" ? 1 : 0.1}
        placeholder={property.example || `Enter ${_.startCase(label)}`}
        showClearButton={false}
      />
    );
  }

  if (property.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <Switch
          checked={!!value}
          onCheckedChange={onChange}
          aria-label={`toggle-${fieldId}`}
        />
        <Text as="span" text03 mainUiBody>{value ? "Enabled" : "Disabled"}</Text>
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
      <Text as="p" text03 secondaryBody className="text-xs">
        Unsupported field type. You can enter raw JSON here.
      </Text>
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
        <ThreeDotsLoader />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-status-error-03 bg-status-error-01 p-4 text-status-error-06">
        <Text as="p" className="font-semibold text-status-error-06">Error</Text>
        <Text as="p" className="text-sm text-status-error-06">{error}</Text>
      </div>
    );
  }

  if (!response) {
    return (
      <div className="text-center py-8">
        <Text as="p" text03 mainContentMuted>Run the tool to see results</Text>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Text as="p" className="text-sm font-semibold text-status-success-06">Result</Text>
      <pre className="max-h-[60vh] overflow-auto rounded-lg bg-background-neutral-01 p-4 text-sm whitespace-pre-wrap break-words text-text-04">
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
  const [inputValues, setInputValues] = useState<Record<string, any>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
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

  const groupedTools = useMemo(
    () => groupToolsByCategory(toolsWithCategory),
    [toolsWithCategory]
  );

  const categoryLabelMap = useMemo(
    () => buildCategoryLabelMap(toolsWithCategory),
    [toolsWithCategory]
  );

  const sortedCategories = useMemo(
    () =>
      Object.keys(groupedTools).sort((a, b) => {
        if (a === "other") return 1;
        if (b === "other") return -1;
        const labelA = categoryLabelMap[a] || _.startCase(a);
        const labelB = categoryLabelMap[b] || _.startCase(b);
        return labelA.localeCompare(labelB);
      }),
    [groupedTools, categoryLabelMap]
  );

  const filteredTools = toolsWithCategory;

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
      setFieldErrors({});
      router.push(`/tools/playground?tool=${encodeURIComponent(tool.name)}`);
    },
    [router]
  );

  const handleInputChange = useCallback(
    (values: Record<string, any>) => {
      setInputValues(values);
      setFieldErrors((prev) => {
        const next = { ...prev };
        Object.keys(next).forEach((field) => {
          if (!isFieldEmpty(values[field])) delete next[field];
        });
        return next;
      });
    },
    []
  );

  const handleRunTool = useCallback(async () => {
    if (!selectedTool) return;

    const schema = normalizeSchema(selectedTool.input_schema);
    const missing = getMissingRequiredFields(schema, inputValues);
    if (missing.length > 0) {
      const errors: Record<string, string> = {};
      missing.forEach((field) => {
        errors[field] = "This field is required";
      });
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
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

  const pageTitle = selectedTool ? `${_.startCase(selectedTool.name)} Playground` : "Tools Playground";

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <IconButton
            icon={SvgArrowLeft}
            onClick={() => router.back()}
            tooltip="Back"
            aria-label="Back"
          />
          <h1 className="mt-3 text-2xl font-bold text-text-05">{pageTitle}</h1>
          <Text as="p" text03 mainContentBody className="mt-1 text-sm">
            Run built-in MCP tools with custom input and inspect the raw result.
          </Text>
        </div>
        {selectedTool && (
          <Button primary onClick={handleRunTool} disabled={isRunning}>
            {isRunning ? "Running..." : "Run Tool"}
          </Button>
        )}
      </div>

      <div className="rounded-lg border border-border-01 bg-background-neutral-00 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Text as="p" text05 className="text-sm font-semibold">Tool selector</Text>
            <Text as="p" text03 mainContentBody className="text-sm">Choose a tool to open the playground.</Text>
          </div>
          {toolsWithCategory.length > 0 && (
            <InputSelect
              value={toolName}
              onValueChange={(value) => {
                const tool = toolsWithCategory.find((t) => t.name === value);
                if (tool) handleSelectTool(tool);
              }}
            >
              <div className="w-full sm:w-72">
                <InputSelect.Trigger placeholder="Select a tool..." />
              </div>
              <InputSelect.Content>
                {sortedCategories.map((category) => (
                  <InputSelect.Group key={category}>
                    <InputSelect.Label>
                      {categoryLabelMap[category] || _.startCase(category)}
                    </InputSelect.Label>
                    {(groupedTools[category] ?? []).map((tool) => (
                      <InputSelect.Item key={tool.name} value={tool.name}>
                        {_.startCase(tool.name)}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Group>
                ))}
              </InputSelect.Content>
            </InputSelect>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-14">
          <ThreeDotsLoader />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-status-error-03 bg-status-error-01 p-4 text-status-error-06">
          {error}
        </div>
      ) : selectedTool ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(360px,1fr)_minmax(420px,560px)]">
          <div className="rounded-lg border border-border-01 bg-background-neutral-00 p-6">
            <div className="mb-4 space-y-2">
              <Text as="p" text05 className="text-sm font-semibold">{_.startCase(selectedTool.name)}</Text>
              <Text as="p" text03 mainContentBody className="text-sm">{selectedTool.description}</Text>
            </div>
            <div className="space-y-6">
              <div>
                <Text as="p" text04 mainUiAction className="mb-3 text-sm font-semibold">Input</Text>
                <SchemaForm
                  schema={normalizeSchema(selectedTool.input_schema)}
                  values={inputValues}
                  onChange={handleInputChange}
                  fieldErrors={fieldErrors}
                />
              </div>
              {runError && (
                <div className="rounded-lg border border-status-error-03 bg-status-error-01 p-4">
                  <Text as="p" className="text-status-error-06">{runError}</Text>
                </div>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-border-01 bg-background-neutral-00 p-6">
            <Text as="p" text05 className="mb-4 text-sm font-semibold">Response</Text>
            <ResponseViewer response={response} isLoading={isRunning} error={runError} />
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {filteredTools.length === 0 ? (
            <div className="rounded-lg border border-border-01 bg-background-neutral-00 p-6 text-center">
              <Text as="p" text03 mainContentBody>No tools match your search.</Text>
            </div>
          ) : (
            Object.keys(groupedTools).map((category) => {
              const toolsInCategory = groupedTools[category] ?? [];
              return (
                <div key={category} className="rounded-lg border border-border-01 bg-background-neutral-00 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <Text as="p" text05 className="text-sm font-semibold">
                        {categoryLabelMap[category] || _.startCase(category)}
                      </Text>
                      <Text as="p" text03 secondaryBody className="text-xs">{toolsInCategory.length} tools</Text>
                    </div>
                    <span className="rounded-full border border-border-01 px-2 py-0.5 text-xs text-text-03">
                      {toolsInCategory.length}
                    </span>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {toolsInCategory.map((tool) => (
                      <div key={tool.name} className="rounded-lg border border-border-01 bg-background-tint-00 p-4">
                        <Text as="p" text04 mainUiAction className="mb-2 text-sm font-semibold">{_.startCase(tool.name)}</Text>
                        <Text as="p" text03 mainContentBody className="mb-4 text-sm line-clamp-3">{tool.description}</Text>
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

"use client";

import { useFormikContext } from "formik";
import { useTranslation } from "react-i18next";

import Button from "@/refresh-components/buttons/Button";
import { Card } from "@/refresh-components/cards";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import Text from "@/refresh-components/texts/Text";
import {
  CONNECTOR_OPERATIONS,
  ConnectorBinding,
  ConnectorToolOption,
} from "@/hooks/useConnectorToolOptions";

interface ConnectorBindingsFieldProps {
  options: ConnectorToolOption[] | undefined;
  isLoading: boolean;
  error: unknown;
}

interface FormValues {
  connector_bindings: ConnectorBinding[];
}

export default function ConnectorBindingsField({
  options,
  isLoading,
  error,
}: ConnectorBindingsFieldProps) {
  const { t } = useTranslation();
  const operationLabels: Record<string, string> = {
    list_resources: t("agentEditor.connectors.listResources", {
      defaultValue: "List resources",
    }),
    read: t("agentEditor.connectors.read", { defaultValue: "Read" }),
  };
  const { values, setFieldValue } = useFormikContext<FormValues>();
  const bindings = values.connector_bindings ?? [];
  const optionsById = new Map(
    (options ?? []).map((option) => [option.id, option])
  );
  const missingBindings = isLoading
    ? []
    : bindings.filter((binding) => !optionsById.has(binding.datasource_id));

  function setBindings(next: ConnectorBinding[]) {
    void setFieldValue("connector_bindings", next);
  }

  function toggleConnector(option: ConnectorToolOption, selected: boolean) {
    if (option.unavailable_reason && selected) return;
    if (selected) {
      const allowed = CONNECTOR_OPERATIONS.filter((operation) =>
        option.operations.includes(operation)
      );
      setBindings([
        ...bindings,
        { datasource_id: option.id, operations: [...allowed] },
      ]);
    } else {
      setBindings(
        bindings.filter((binding) => binding.datasource_id !== option.id)
      );
    }
  }

  function toggleOperation(
    option: ConnectorToolOption,
    operation: string,
    selected: boolean
  ) {
    if (!option.operations.includes(operation) || option.unavailable_reason)
      return;
    setBindings(
      bindings.map((binding) =>
        binding.datasource_id === option.id
          ? {
              ...binding,
              operations: selected
                ? Array.from(new Set([...binding.operations, operation]))
                : binding.operations.filter((value) => value !== operation),
            }
          : binding
      )
    );
  }

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-1">
        <Text mainUiAction text03>
          {t("agentEditor.connectors.title", { defaultValue: "Connectors" })}
        </Text>
        <Text mainUiMuted text03>
          {t("agentEditor.connectors.description", {
            defaultValue:
              "Choose saved connections and what this agent may do with each one.",
          })}
        </Text>
      </div>

      {Boolean(error) && (
        <Text mainUiMuted text03>
          {t("agentEditor.connectors.loadError", {
            defaultValue:
              "Connector options could not be loaded. Saved selections are preserved.",
          })}
        </Text>
      )}
      {isLoading && (
        <Text mainUiMuted text03>
          {t("agentEditor.connectors.loading", {
            defaultValue: "Loading connectors…",
          })}
        </Text>
      )}
      {!isLoading && !error && options?.length === 0 && (
        <Text mainUiMuted text03>
          {t("agentEditor.connectors.empty", {
            defaultValue: "No configured connectors are available.",
          })}
        </Text>
      )}

      {(options ?? []).map((option) => {
        const binding = bindings.find(
          (value) => value.datasource_id === option.id
        );
        const selected = Boolean(binding);
        const unavailable = Boolean(option.unavailable_reason);
        return (
          <div
            key={option.id}
            className="flex flex-col gap-2 rounded-08 border border-border-02 p-3"
          >
            <div className="flex items-start gap-2">
              <Checkbox
                aria-label={option.name}
                checked={selected}
                disabled={unavailable || (!selected && bindings.length >= 32)}
                onCheckedChange={(checked) => toggleConnector(option, checked)}
              />
              <div className="flex min-w-0 flex-col gap-0.5">
                <Text mainUiAction text03>
                  {option.name}
                </Text>
                <Text mainUiMuted text03>
                  {option.connector_type}
                  {option.unavailable_reason
                    ? ` · ${option.unavailable_reason}`
                    : ""}
                </Text>
              </div>
              {selected && unavailable && (
                <Button
                  type="button"
                  secondary
                  size="md"
                  aria-label={t("agentEditor.connectors.removeNamed", {
                    defaultValue: "Remove {{name}}",
                    name: option.name,
                  })}
                  onClick={() => toggleConnector(option, false)}
                >
                  {t("agentEditor.connectors.remove", {
                    defaultValue: "Remove",
                  })}
                </Button>
              )}
            </div>
            <div className="flex flex-wrap gap-4 pl-6">
              {CONNECTOR_OPERATIONS.map((operation) => {
                const supported = option.operations.includes(operation);
                return (
                  <div key={operation} className="flex items-center gap-2">
                    <Checkbox
                      aria-label={`${option.name}: ${operationLabels[operation]}`}
                      checked={binding?.operations.includes(operation) ?? false}
                      disabled={!selected || !supported || unavailable}
                      onCheckedChange={(checked) =>
                        toggleOperation(option, operation, checked)
                      }
                    />
                    <Text mainUiMuted text03>
                      {operationLabels[operation]}
                    </Text>
                  </div>
                );
              })}
            </div>
            {selected && binding?.operations.length === 0 && (
              <Text mainUiMuted text03>
                {t("agentEditor.connectors.operationRequired", {
                  defaultValue:
                    "Select at least one operation or remove this connector.",
                })}
              </Text>
            )}
          </div>
        );
      })}

      {missingBindings.map((binding) => {
        const label = error
          ? t("agentEditor.connectors.saved", {
              defaultValue: "Saved connector ({{id}})",
              id: binding.datasource_id,
            })
          : t("agentEditor.connectors.deleted", {
              defaultValue: "Deleted connector ({{id}})",
              id: binding.datasource_id,
            });
        return (
          <div
            key={binding.datasource_id}
            className="flex items-center justify-between gap-3 rounded-08 border border-border-02 p-3"
          >
            <div className="flex flex-col gap-0.5">
              <Text mainUiAction text03>
                {label}
              </Text>
              <Text mainUiMuted text03>
                {t("agentEditor.connectors.unavailable", {
                  defaultValue:
                    "This saved connection is unavailable. Remove it before saving if it is no longer needed.",
                })}
              </Text>
            </div>
            <Button
              type="button"
              secondary
              size="md"
              aria-label={t("agentEditor.connectors.removeNamed", {
                defaultValue: "Remove {{name}}",
                name: label,
              })}
              onClick={() =>
                setBindings(
                  bindings.filter(
                    (value) => value.datasource_id !== binding.datasource_id
                  )
                )
              }
            >
              {t("agentEditor.connectors.remove", { defaultValue: "Remove" })}
            </Button>
          </div>
        );
      })}
    </Card>
  );
}

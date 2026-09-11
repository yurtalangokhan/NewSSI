"use client";

import InputSelect from "@/refresh-components/inputs/InputSelect";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import AgentPreviewTooltip from "@/refresh-components/agents/AgentPreviewTooltip";
import { getProviderIcon } from "@/app/admin/configuration/llm/utils";
import { useFieldOptions } from "./useFieldOptions";
import type { FieldRendererProps } from "./types";
import { useTranslation } from "react-i18next";

export function OptionsField({
  fieldKey,
  field,
  value,
  onChange,
  disabled,
  allValues,
}: FieldRendererProps) {
  const { t } = useTranslation();
  // Narrowing by a sibling field (the chosen provider for `llm.models`) now
  // happens on the server, driven by the template's `depends_on`. The list
  // that arrives is already the right one.
  const { options, isLoading, unavailable } = useFieldOptions(field, allValues);

  const selectedProvider =
    typeof allValues?.provider === "string" ? allValues.provider.trim() : null;

  if (isLoading) {
    return <div className="h-8 w-full animate-pulse rounded-08 bg-muted" />;
  }

  const hasNoOptions = options.length === 0 || unavailable;
  const placeholderText = unavailable
    ? t(
        "flowCanvas.fields.options.sourceUnavailable",
        "Option source unavailable"
      )
    : options.length === 0
      ? t(
          "flowCanvas.fields.options.noOptions",
          `No ${field.display_name.toLowerCase()} available`,
          { field: field.display_name.toLowerCase() }
        )
      : t(
          "flowCanvas.fields.options.select",
          `Select ${field.display_name.toLowerCase()}...`,
          { field: field.display_name.toLowerCase() }
        );

  return (
    <InputSelect
      value={
        typeof value === "string" && value !== "" && !hasNoOptions
          ? value
          : undefined
      }
      onValueChange={onChange}
      disabled={disabled || hasNoOptions}
    >
      <InputSelect.Trigger placeholder={placeholderText} />
      <InputSelect.Content>
        {options.map((o) => {
          let Icon: ReturnType<typeof getProviderIcon> | undefined = undefined;
          if (field.options_source === "llm.providers") {
            Icon = getProviderIcon(o.description || o.value || o.label);
          } else if (field.options_source === "llm.models") {
            const provName = o.description
              ? o.description.split("|").pop()
              : "";
            Icon = getProviderIcon(
              provName || selectedProvider || o.value,
              o.value
            );
          } else if (field.options_source === "ollama.models") {
            Icon = getProviderIcon("ollama", o.value);
          }

          const item = (
            <InputSelect.Item key={o.value} value={o.value} icon={Icon}>
              {o.label}
            </InputSelect.Item>
          );

          if (field.options_source === "agents.definitions" && o.description) {
            return (
              <SimpleTooltip
                key={o.value}
                tooltip={<AgentPreviewTooltip preview={o.description} />}
                side="right"
              >
                {item}
              </SimpleTooltip>
            );
          }

          return item;
        })}
      </InputSelect.Content>
    </InputSelect>
  );
}

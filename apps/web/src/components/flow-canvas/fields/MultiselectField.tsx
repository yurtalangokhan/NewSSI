"use client";

import { useMemo, useRef, useState } from "react";
import Chip from "@/refresh-components/Chip";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import AgentPreviewTooltip from "@/refresh-components/agents/AgentPreviewTooltip";
import Text from "@/refresh-components/texts/Text";
import { useFieldOptions } from "./useFieldOptions";
import type { FieldRendererProps } from "./types";
import { useTranslation } from "react-i18next";

export function MultiselectField({
  field,
  value,
  onChange,
  disabled,
  allValues,
}: FieldRendererProps) {
  const { t } = useTranslation();
  const {
    options: rawOptions,
    isLoading,
    unavailable,
  } = useFieldOptions(field);
  const selected = Array.isArray(value) ? (value as string[]) : [];

  // InputSelect wraps a single-select Radix primitive that closes on every
  // pick. We drive its open state so choosing a tool doesn't collapse the
  // menu — only an outside click, Escape, or the trigger itself closes it.
  const [open, setOpen] = useState(false);
  const keepOpenAfterSelect = useRef(false);

  // The External MCP Server node stores its picked provider in the sibling
  // `provider` field. Its `mcp.external_tools` source returns every external
  // provider's tools flat, each tagged `"<providerId>|<description>"`; narrow
  // the list to the provider chosen on the same node (mirrors OptionsField's
  // llm.models/provider filtering).
  const isExternalMcp = field.options_source === "mcp.external_tools";
  const selectedProvider =
    typeof allValues?.provider === "string" ? allValues.provider.trim() : null;

  const options = useMemo(() => {
    if (!isExternalMcp) return rawOptions;
    return rawOptions
      .filter(
        (o) => (o.description ?? "").split("|", 1)[0] === selectedProvider
      )
      .map((o) => {
        const desc = o.description ?? "";
        const sep = desc.indexOf("|");
        return { ...o, description: sep >= 0 ? desc.slice(sep + 1) : null };
      });
  }, [rawOptions, isExternalMcp, selectedProvider]);

  if (isLoading) {
    return <div className="h-8 w-full animate-pulse rounded-08 bg-muted" />;
  }

  if (unavailable) {
    return (
      <Text text03 secondaryBody>
        {t(
          "flowCanvas.fields.multiselect.sourceUnavailable",
          "This option source is currently unavailable."
        )}
      </Text>
    );
  }

  if (isExternalMcp && !selectedProvider) {
    return (
      <Text text03 secondaryBody>
        {t(
          "flowCanvas.fields.multiselect.selectProviderFirst",
          "Select a provider first"
        )}
      </Text>
    );
  }

  const available = options.filter((o) => !selected.includes(o.value));

  function remove(v: string) {
    onChange(selected.filter((s) => s !== v));
  }

  function add(v: string) {
    if (!v) return;
    if (!selected.includes(v)) {
      onChange([...selected, v]);
    }
  }

  return (
    <div className="flex w-full flex-col gap-1.5">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map((v) => {
            const label = options.find((o) => o.value === v)?.label ?? v;
            return (
              <Chip key={v} onRemove={disabled ? undefined : () => remove(v)}>
                {label}
              </Chip>
            );
          })}
        </div>
      )}
      <InputSelect
        value=""
        open={open}
        onOpenChange={(next) => {
          if (!next && keepOpenAfterSelect.current) {
            keepOpenAfterSelect.current = false;
            return; // a pick tried to close the menu — keep it open
          }
          setOpen(next);
        }}
        onValueChange={(val) => {
          if (!val) return;
          add(val);
          // more than the one just picked left → stay open for the next
          keepOpenAfterSelect.current = available.length > 1;
        }}
        disabled={disabled || available.length === 0}
      >
        <InputSelect.Trigger
          placeholder={
            available.length === 0
              ? t(
                  "flowCanvas.fields.multiselect.noMoreOptions",
                  "No more options"
                )
              : t("flowCanvas.fields.multiselect.add", "Add...")
          }
        />
        <InputSelect.Content>
          {available.map((o) => {
            const isAgentSource = field.options_source === "agents.definitions";
            const item = (
              <InputSelect.Item
                key={o.value}
                value={o.value}
                description={
                  isAgentSource ? undefined : o.description ?? undefined
                }
              >
                {o.label}
              </InputSelect.Item>
            );

            if (isAgentSource && o.description) {
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
    </div>
  );
}

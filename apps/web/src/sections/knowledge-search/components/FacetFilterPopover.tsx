"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { IconProps } from "@opal/types";
import { SvgCheck } from "@opal/icons";
import { filterByText } from "@/lib/text/textFilter";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import FilterButton from "@/refresh-components/buttons/FilterButton";
import LineItem from "@/refresh-components/buttons/LineItem";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import BlankIcon from "@/sections/knowledge-search/components/BlankIcon";

export interface FacetOption {
  value: string;
  label: string;
  count?: number;
  description?: string;
}

interface FacetFilterPopoverProps {
  icon: React.FunctionComponent<IconProps>;
  label: string;
  options: readonly FacetOption[];
  selected: readonly string[];
  onToggle: (value: string) => void;
  onClear: () => void;
  /** Shows a name filter above the options. */
  searchPlaceholder?: string;
}

/** A filter chip whose popover multi-selects facet values. */
export default function FacetFilterPopover({
  icon,
  label,
  options,
  selected,
  onToggle,
  onClear,
  searchPlaceholder,
}: FacetFilterPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const visible = useMemo(
    () => filterByText(options, filter, (option) => option.label),
    [options, filter]
  );

  const buttonText =
    selected.length === 0
      ? label
      : selected.length === 1
        ? options.find((option) => option.value === selected[0])?.label ??
          selected[0]!
        : t("knowledgeSearch.filters.selectedCount", {
            label,
            count: selected.length,
          });

  const items: React.ReactNode[] = visible.map((option) => {
    const isSelected = selected.includes(option.value);
    return (
      <LineItem
        key={option.value}
        icon={isSelected ? SvgCheck : BlankIcon}
        selected={isSelected}
        emphasized
        description={option.description}
        rightChildren={
          option.count !== undefined ? (
            <Text as="span" secondaryMono text03 className="tabular-nums">
              {option.count}
            </Text>
          ) : undefined
        }
        onClick={() => onToggle(option.value)}
      >
        {option.label}
      </LineItem>
    );
  });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <FilterButton
          leftIcon={icon}
          active={selected.length > 0}
          transient={open}
          onClear={onClear}
        >
          {buttonText}
        </FilterButton>
      </Popover.Trigger>
      <Popover.Content align="start" width="xl">
        <PopoverMenu>
          {[
            ...(searchPlaceholder
              ? [
                  <InputTypeIn
                    key="facet-filter"
                    variant="internal"
                    leftSearchIcon
                    placeholder={searchPlaceholder}
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                  />,
                ]
              : []),
            ...(items.length > 0
              ? items
              : [
                  <Text
                    key="empty"
                    as="p"
                    secondaryBody
                    text03
                    className="px-2 py-1.5"
                  >
                    {t("knowledgeSearch.filters.noOptions")}
                  </Text>,
                ]),
          ]}
        </PopoverMenu>
      </Popover.Content>
    </Popover>
  );
}

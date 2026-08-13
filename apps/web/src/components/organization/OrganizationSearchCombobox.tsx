"use client";

import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import type { OrganizationNode } from "@/components/organization/organizationTypes";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface Props {
  activeIndex: number;
  className?: string;
  error: string | null;
  limited: boolean;
  loading: boolean;
  onActiveIndexChange: (index: number) => void;
  onQueryChange: (query: string) => void;
  onReveal: (result: OrganizationNode) => void;
  onSearch: (query: string) => void;
  query: string;
  results: OrganizationNode[];
  revealLoading: boolean;
}

export function OrganizationSearchCombobox({
  activeIndex,
  className,
  error,
  limited,
  loading,
  onActiveIndexChange,
  onQueryChange,
  onReveal,
  onSearch,
  query,
  results,
  revealLoading,
}: Props) {
  const { t } = useTranslation();
  const listboxId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const trimmedQuery = query.trim();
  const canSearch = trimmedQuery.length >= 2;

  useEffect(() => {
    if (!canSearch) return;
    const timeoutId = window.setTimeout(() => onSearch(trimmedQuery), 250);
    return () => window.clearTimeout(timeoutId);
  }, [canSearch, onSearch, trimmedQuery]);

  const selectResult = (result: OrganizationNode) => {
    setIsOpen(false);
    onReveal(result);
  };

  const moveActive = (direction: 1 | -1) => {
    if (results.length === 0) return;
    const nextIndex =
      activeIndex < 0
        ? direction === 1
          ? 0
          : results.length - 1
        : (activeIndex + direction + results.length) % results.length;
    onActiveIndexChange(nextIndex);
  };

  const showPopover = isOpen && canSearch;
  const activeResult = results[activeIndex];

  return (
    <div className={cn("relative min-w-0 flex-1", className)}>
      <InputTypeIn
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={showPopover}
        aria-activedescendant={
          showPopover && activeResult
            ? `${listboxId}-${activeResult.id}`
            : undefined
        }
        aria-label={t("admin.organizations.tree.searchLabel")}
        className={cn(
          "border border-border-02 bg-background-neutral-01 shadow-sm transition-[border-color,box-shadow] duration-200 focus-within:border-action-link-05 focus-within:ring-1 focus-within:ring-action-link-05 motion-reduce:transition-none"
        )}
        leftSearchIcon
        placeholder={t("admin.organizations.tree.searchPlaceholder")}
        value={query}
        onChange={(event) => {
          onQueryChange(event.target.value);
          onActiveIndexChange(-1);
          setIsOpen(Boolean(event.target.value.trim()));
        }}
        onFocus={() => setIsOpen(Boolean(trimmedQuery))}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setIsOpen(true);
            moveActive(event.key === "ArrowDown" ? 1 : -1);
          } else if (event.key === "Enter" && activeResult) {
            event.preventDefault();
            selectResult(activeResult);
          } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            if (showPopover) setIsOpen(false);
            else {
              onQueryChange("");
              onActiveIndexChange(-1);
            }
          }
        }}
      />
      {showPopover && (
        <div
          className={cn(
            "absolute inset-x-0 top-full z-50 mt-1 max-h-80 overflow-y-auto rounded-08 border border-border-02 bg-background-neutral-00 p-1 shadow-lg"
          )}
        >
          <div id={listboxId} role="listbox">
            {results.map((result, index) => (
              <Button
                key={result.id}
                id={`${listboxId}-${result.id}`}
                role="option"
                aria-selected={index === activeIndex}
                tertiary
                className={cn(
                  "w-full justify-start rounded-08 px-2 py-1.5 text-left",
                  index === activeIndex && "bg-background-neutral-03"
                )}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectResult(result)}
              >
                <span className={cn("flex min-w-0 flex-col items-start") }>
                  <Text mainUiBody text04 className={cn("truncate") }>
                    {result.name}
                  </Text>
                  <Text secondaryBody text03 className={cn("truncate") }>
                    {result.path}
                  </Text>
                </span>
              </Button>
            ))}
          </div>
          <div aria-live="polite" className={cn("px-2 py-1.5") }>
            <Text secondaryBody text03>
              {loading
                ? t("admin.organizations.tree.searchLoading")
                : revealLoading
                  ? t("admin.organizations.tree.revealLoading")
                  : error
                    ? error
                    : limited
                      ? t("admin.organizations.tree.searchLimited")
                      : results.length === 0
                        ? t("admin.organizations.tree.searchEmpty")
                        : t("admin.organizations.tree.searchCount", {
                            count: results.length,
                          })}
            </Text>
          </div>
        </div>
      )}
    </div>
  );
}

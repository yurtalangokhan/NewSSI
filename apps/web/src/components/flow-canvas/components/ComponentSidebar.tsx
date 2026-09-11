/**
 * Ported from Langflow (MIT) — src/frontend/src/pages/FlowPage/components/flowSidebarComponent/index.tsx
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Layout and styling follow upstream: a `w-64` panel with a single-row
 * search at the top (searchInput.tsx — `rounded-lg bg-canvas-panel text-sm`
 * with a leading icon and a `/` shortcut hint), then category disclosures
 * whose triggers use upstream's
 * `user-select-none flex cursor-pointer items-center gap-2` with a chevron
 * that rotates on expand (categoryDisclouse.tsx:111-136).
 *
 * The search was one row too tall because it used the shared `InputTypeIn`
 * with its own label/clear chrome; upstream's is a bare `Input` with an
 * icon, which is what this now renders.
 *
 * Adapted for Onyx: data comes from GET /flow-components (P1 Task 6) via
 * useSWR, already grouped by category server-side — Langflow's own
 * category-grouping/bundle logic is not needed. Search is a from-scratch
 * matcher (componentSearch.ts), not a Fuse.js port (fuse.js is not a
 * dependency here). Recents is our own addition (Langflow has none).
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

"use client";

import EmptyMessage from "@/refresh-components/EmptyMessage";
import { cn } from "@/lib/utils";
import {
  SvgChevronRight,
  SvgClock,
  SvgSearch,
  SvgSidebar,
  SvgX,
} from "@opal/icons";
import {
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type SVGProps,
} from "react";
import { useTranslation } from "react-i18next";
import { ComponentSidebarItem } from "./ComponentSidebarItem";
import { useComponentTemplates } from "../hooks/useComponentTemplates";
import { useRecentComponents } from "../hooks/useRecentComponents";
import type { ComponentTemplate } from "../types/componentTemplate";
import { resolveCategoryIcon } from "../utils/categoryIcon";
import { filterGroupedTemplates } from "../utils/componentSearch";

const RECENTS_CATEGORY = "__recents__";

/** upstream searchInput.tsx — one row: icon, field, and a `/` hint that
 * disappears once the field is focused or non-empty. */
function SearchRow({
  value,
  onChange,
  inputRef,
}: {
  value: string;
  onChange: (next: string) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const { t } = useTranslation();
  const [focused, setFocused] = useState(false);
  return (
    <div className="relative w-full">
      <SvgSearch className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={inputRef}
        type="text"
        data-testid="sidebar-search-input"
        aria-label={t(
          "flowCanvas.sidebar.searchAriaLabel",
          "Search components"
        )}
        placeholder={t("flowCanvas.sidebar.searchPlaceholder", "Search...")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="h-8 w-full rounded-lg border border-canvas-border bg-canvas-panel pl-8 pr-8 text-sm text-canvas-fg outline-none ring-ring placeholder:text-muted-foreground focus-visible:ring-1"
      />
      {value === "" && !focused && (
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-canvas-border px-1 text-xs text-muted-foreground">
          /
        </span>
      )}
      {value !== "" && (
        <button
          type="button"
          aria-label={t(
            "flowCanvas.sidebar.clearSearchAriaLabel",
            "Clear search"
          )}
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-canvas-fg"
        >
          <SvgX className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

/** upstream categoryDisclouse.tsx:103-140 — trigger row plus a chevron
 * that rotates 90° when the section is open. */
function CategorySection({
  label,
  icon: Icon,
  open,
  onToggle,
  testId,
  children,
}: {
  label: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  open: boolean;
  onToggle: () => void;
  testId?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        data-testid={testId}
        className="user-select-none group/collapsible flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted"
      >
        {/* upstream categoryDisclouse.tsx:113-116 — the category's own
            glyph sits before the label; the chevron trails it. */}
        {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <span
          className={cn(
            "min-w-0 flex-1 truncate text-sm capitalize text-canvas-fg",
            open && "font-semibold"
          )}
        >
          {label}
        </span>
        <SvgChevronRight
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-90"
          )}
        />
      </button>
      {open && <div className="flex flex-col gap-1 px-1 pb-1">{children}</div>}
    </div>
  );
}

export type ComponentSidebarProps = {
  /** Rendered in the header row, right of the "Components" caption — the
   * collapse-panel trigger lives here rather than as an absolute overlay
   * on top of the search row, which it used to visually collide with. */
  onCollapse?: () => void;
};

export function ComponentSidebar({ onCollapse }: ComponentSidebarProps = {}) {
  const { t } = useTranslation();
  const { data: grouped, isLoading, error } = useComponentTemplates();
  const { recents, recordUsage } = useRecentComponents();
  const [search, setSearch] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(
    () => new Set()
  );

  const filtered = useMemo(
    () => (grouped ? filterGroupedTemplates(grouped, search) : {}),
    [grouped, search]
  );

  const recentTemplates: ComponentTemplate[] = useMemo(() => {
    if (!grouped || recents.length === 0) return [];
    const byType = new Map<string, ComponentTemplate>();
    for (const templates of Object.values(grouped)) {
      for (const t of templates) byType.set(t.type, t);
    }
    return recents
      .map((type) => byType.get(type))
      .filter((t): t is ComponentTemplate => !!t);
  }, [grouped, recents]);

  const toggleCategory = (category: string) => {
    setCollapsedCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  const categories = Object.keys(filtered);
  const hasAnyResults = categories.some((c) => filtered[c]!.length > 0);

  return (
    <aside
      className="flex h-full w-64 shrink-0 flex-col gap-2 border-r border-canvas-border bg-canvas-panel p-2"
      data-testid="component-sidebar"
    >
      <SearchRow
        value={search}
        onChange={setSearch}
        inputRef={searchInputRef}
      />

      {/* upstream sidebarHeader.tsx — a "Components" caption sits between
          the search and the category list; the collapse trigger sits in
          this same row rather than overlaying the search input above. */}
      <div className="flex items-center justify-between px-2 pt-1">
        <span className="text-sm font-medium text-canvas-fg">
          {t("flowCanvas.sidebar.title", "Components")}
        </span>
        {onCollapse && (
          <button
            type="button"
            aria-label={t(
              "flowCanvas.sidebar.collapsePanel",
              "Collapse component panel"
            )}
            onClick={onCollapse}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-canvas-fg"
          >
            <SvgSidebar className="h-4 w-4" />
          </button>
        )}
      </div>

      {isLoading && (
        <div
          className="flex flex-col gap-3 p-2"
          data-testid="sidebar-loading-skeleton"
        >
          {[
            { labelW: "w-20", items: ["w-28", "w-32"] },
            { labelW: "w-24", items: ["w-36", "w-24"] },
            { labelW: "w-16", items: ["w-28"] },
          ].map((cat, idx) => (
            <div key={idx} className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2 py-1">
                <div className="h-4 w-4 rounded bg-muted animate-pulse shrink-0" />
                <div
                  className={`h-3.5 ${cat.labelW} rounded bg-muted animate-pulse`}
                />
                <div className="flex-1" />
                <div className="h-3 w-3 rounded bg-muted animate-pulse" />
              </div>
              <div className="flex flex-col gap-1 pl-6">
                {cat.items.map((itemW, iIdx) => (
                  <div
                    key={iIdx}
                    className={`h-6 ${itemW} rounded border border-canvas-border/40 bg-muted/40 animate-pulse`}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {error && !isLoading && (
        <EmptyMessage
          icon={SvgSearch}
          title={t("flowCanvas.sidebar.loadError", "Couldn't load components")}
          description={t(
            "flowCanvas.sidebar.loadErrorDescription",
            "Try reloading the page."
          )}
        />
      )}

      {!isLoading && !error && !hasAnyResults && (
        <EmptyMessage
          icon={SvgSearch}
          title={t(
            "flowCanvas.sidebar.noComponentsFound",
            "No components found"
          )}
          description={t(
            "flowCanvas.sidebar.noComponentsFoundDescription",
            "Try a different search term."
          )}
        />
      )}

      {!isLoading && !error && (
        <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto">
          {recentTemplates.length > 0 && !search && (
            <CategorySection
              label={t("flowCanvas.sidebar.recentlyUsed", "Recently used")}
              icon={SvgClock}
              open={!collapsedCategories.has(RECENTS_CATEGORY)}
              onToggle={() => toggleCategory(RECENTS_CATEGORY)}
            >
              {recentTemplates.map((t) => (
                <ComponentSidebarItem
                  key={`recent-${t.type}`}
                  template={t}
                  onDragStart={recordUsage}
                />
              ))}
            </CategorySection>
          )}

          {categories.map((category) => {
            const templates = filtered[category] ?? [];
            if (templates.length === 0) return null;
            return (
              <CategorySection
                key={category}
                label={t(
                  `flowCanvas.sidebar.categories.${category
                    .toLowerCase()
                    .replace(/[^a-z0-9]/g, "")}`,
                  category
                )}
                icon={resolveCategoryIcon(category)}
                open={!collapsedCategories.has(category)}
                onToggle={() => toggleCategory(category)}
                testId={`sidebar-category-${category}`}
              >
                {templates.map((t) => (
                  <ComponentSidebarItem
                    key={t.type}
                    template={t}
                    onDragStart={recordUsage}
                  />
                ))}
              </CategorySection>
            );
          })}
        </div>
      )}
    </aside>
  );
}

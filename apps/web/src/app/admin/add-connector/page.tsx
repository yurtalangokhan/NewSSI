"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Message from "@/refresh-components/messages/Message";
import Text from "@/refresh-components/texts/Text";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import {
  useCallback,
  useDeferredValue,
  useMemo,
  useRef,
  useEffect,
  useState,
} from "react";
import {
  useAirbyteConnectors,
  useAirbyteDatasources,
  AirbyteConnector,
} from "@/lib/airbyte";
import { useRouter } from "next/navigation";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

// ── Connector tile helpers ──────────────────────────────────────────────────

const MAX_INLINE_SVG_LENGTH = 200_000;

function connectorIconSrc(connector: AirbyteConnector): string | null {
  const raw = connector.icon_url || connector.icon;
  if (!raw) return null;
  const trimmed = raw.trim();

  // If it's already a data URI
  if (trimmed.startsWith("data:")) {
    // If it's an unencoded data SVG like "data:image/svg+xml;utf8,<svg..."
    if (
      trimmed.startsWith("data:image/svg+xml") &&
      !trimmed.includes(";base64,")
    ) {
      const commaIndex = trimmed.indexOf(",");
      if (commaIndex !== -1) {
        const svgContent = trimmed.slice(commaIndex + 1);
        return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
          svgContent.trim()
        )}`;
      }
    }
    return trimmed;
  }

  // Handle raw SVG markup (starts with <svg, <?xml, <!--, or contains <svg)
  if (trimmed.startsWith("<") || trimmed.includes("<svg")) {
    if (trimmed.length > MAX_INLINE_SVG_LENGTH) {
      return null;
    }
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(trimmed)}`;
  }

  // Handle raw base64 encoded SVG or PNG without data: prefix
  if (trimmed.startsWith("PHN2Zy") || trimmed.startsWith("PD94bW")) {
    return `data:image/svg+xml;base64,${trimmed}`;
  }
  if (trimmed.startsWith("iVBORw0KGgo")) {
    return `data:image/png;base64,${trimmed}`;
  }

  // Handle regular web URLs (http, https, relative /)
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("/")
  ) {
    return encodeURI(trimmed);
  }

  return null;
}

function ConnectorTile({
  connector,
  preSelect,
  onClick,
}: {
  connector: AirbyteConnector;
  preSelect?: boolean;
  onClick: (c: AirbyteConnector) => void;
}) {
  const iconSrc = useMemo(() => connectorIconSrc(connector), [connector]);
  const [imageError, setImageError] = useState(false);

  return (
    <button
      type="button"
      onClick={() => onClick(connector)}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-12 border p-3.5 w-36 h-28 text-center transition-all duration-150 group cursor-pointer",
        "bg-background-neutral-00 hover:bg-background-tint-01 hover:border-border-02 hover:shadow-01",
        preSelect
          ? "border-action-link-05 bg-background-tint-01 ring-1 ring-action-link-05"
          : "border-border-01"
      )}
    >
      <div className="h-8 w-8 shrink-0 flex items-center justify-center">
        {iconSrc && !imageError ? (
          <img
            src={iconSrc}
            alt=""
            width={32}
            height={32}
            onError={() => setImageError(true)}
            className="h-8 w-8 shrink-0 object-contain transition-transform group-hover:scale-105"
          />
        ) : (
          <span className="h-8 w-8 shrink-0 rounded-08 bg-background-tint-02 flex items-center justify-center text-sm font-bold text-text-02">
            {connector.display_name
              ? connector.display_name.charAt(0).toUpperCase() || "C"
              : "C"}
          </span>
        )}
      </div>
      <Text
        as="span"
        secondaryBody
        className="text-xs leading-tight line-clamp-2 text-center text-text-03 group-hover:text-text-04 transition-colors"
      >
        {connector.display_name}
      </Text>
    </button>
  );
}

function ConnectorTileSkeleton() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-12 border border-border-01 bg-background-neutral-00 p-3.5 w-36 h-28 text-center">
      <div className="h-8 w-8 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
      <div className="h-3 w-20 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mt-1" />
      <div className="h-2.5 w-14 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function Page() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.ADD_CONNECTOR]!;
  const router = useRouter();

  const [rawSearchTerm, setSearchTerm] = useState("");
  const searchTerm = useDeferredValue(rawSearchTerm);

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    searchInputRef.current?.focus();
  }, []);

  const {
    data: connectorsData,
    isLoading,
    error,
    mutate: refreshConnectors,
  } = useAirbyteConnectors(searchTerm || undefined);

  const { datasources } = useAirbyteDatasources();
  const connectedSourcesCount = datasources.length;
  const erroredSourcesCount = datasources.filter(
    (d) => d.sync_status === "error"
  ).length;

  // When searching, we get a flat list; otherwise grouped by category
  const byCategory = useMemo<Record<string, AirbyteConnector[]>>(() => {
    if (!connectorsData) return {};
    if (connectorsData.connectors) {
      // search result — put everything under a virtual "Results" category
      return connectorsData.connectors.length > 0
        ? { Results: connectorsData.connectors }
        : {};
    }
    return connectorsData.by_category ?? {};
  }, [connectorsData]);

  const categories = useMemo<string[]>(() => {
    if (!connectorsData) return [];
    // For search results use the virtual key; otherwise use API-provided order
    if (connectorsData.connectors !== undefined) {
      return connectorsData.connectors.length > 0 ? ["Results"] : [];
    }
    return connectorsData.categories ?? Object.keys(byCategory);
  }, [connectorsData, byCategory]);

  const categoryLabels = useMemo<Record<string, string>>(() => {
    if (!connectorsData) return {};
    return connectorsData.category_labels ?? {};
  }, [connectorsData]);

  const handleConnectorClick = useCallback(
    (connector: AirbyteConnector) => {
      // connector.name is e.g. "source-postgres" → route slug is "source-postgres"
      // replace underscores with hyphens to match route convention
      const slug = connector.name.replace(/_/g, "-");
      router.push(`/admin/connectors/${slug}`);
    },
    [router]
  );

  // First result for keyboard Enter shortcut
  const firstConnector = useMemo<AirbyteConnector | null>(() => {
    for (const cat of categories) {
      const list = byCategory[cat];
      if (list && list.length > 0) return list[0]!;
    }
    return null;
  }, [categories, byCategory]);

  // Only show "no results" when we actually have a response with empty data
  const hasLoadedWithNoResults =
    !isLoading && connectorsData !== null && categories.length === 0;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && firstConnector) {
      handleConnectorClick(firstConnector);
    }
  };

  const errorMessage =
    error instanceof Error && error.message
      ? error.message
      : t("admin.addConnector.couldNotLoad");

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        rightChildren={
          <Button href="/admin/indexing/status" primary>
            {t("admin.addConnector.seeConnectors")}
          </Button>
        }
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          isLoading={isLoading}
          title={t("admin.addConnector.catalogTitle", {
            defaultValue: "Connector catalog",
          })}
          description={t("admin.addConnector.catalogDescription", {
            defaultValue:
              "Search the available connectors, press Enter to open the first match, or browse by category.",
          })}
          metrics={[
            {
              label: t("admin.addConnector.categoriesLabel", {
                defaultValue: "Categories",
              }),
              value: isLoading ? "..." : String(categories.length),
            },
            {
              label: t("admin.addConnector.totalConnectorsLabel", {
                defaultValue: "Total connectors",
              }),
              value: isLoading ? "..." : String(connectorsData?.total ?? 0),
            },
            {
              label: t("admin.addConnector.connectedSourcesLabel", {
                defaultValue: "Connected sources",
              }),
              value: String(connectedSourcesCount),
            },
            {
              label: t("admin.addConnector.erroredSourcesLabel", {
                defaultValue: "Sources with errors",
              }),
              value: String(erroredSourcesCount),
              tone: erroredSourcesCount > 0 ? "warning" : "neutral",
            },
          ]}
        />
        <InputTypeIn
          type="text"
          placeholder={t("admin.addConnector.searchPlaceholder")}
          ref={searchInputRef}
          value={rawSearchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-96 flex-none"
        />

        {isLoading ? (
          <div className="w-full">
            {/* Category 1 Skeleton */}
            <div className="pt-6">
              <div className="h-6 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-3" />
              <div className="flex flex-wrap gap-3.5">
                {Array.from({ length: 8 }).map((_, i) => (
                  <ConnectorTileSkeleton key={i} />
                ))}
              </div>
            </div>

            {/* Category 2 Skeleton */}
            <div className="pt-6">
              <div className="h-6 w-28 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse mb-3" />
              <div className="flex flex-wrap gap-3.5">
                {Array.from({ length: 6 }).map((_, i) => (
                  <ConnectorTileSkeleton key={i} />
                ))}
              </div>
            </div>
          </div>
        ) : error ? (
          <div className="pt-8 max-w-2xl">
            <Message
              static
              error
              large
              close={false}
              icon
              text={t("admin.addConnector.couldNotLoad")}
              description={errorMessage}
              actions={t("common.retry", { defaultValue: "Retry" })}
              onAction={() => void refreshConnectors()}
              className="w-full"
            />
          </div>
        ) : (
          <>
            {categories
              .filter((cat) => (byCategory[cat]?.length ?? 0) > 0)
              .map((cat, categoryInd) => (
                <div key={cat} className="pt-6">
                  <Text as="p" headingH3>
                    {searchTerm
                      ? t("admin.addConnector.results")
                      : categoryLabels[cat] ??
                        cat.charAt(0).toUpperCase() + cat.slice(1)}
                  </Text>
                  <div className="flex flex-wrap gap-3.5 mt-3">
                    {(byCategory[cat] ?? []).map((connector, sourceInd) => (
                      <ConnectorTile
                        key={connector.name}
                        connector={connector}
                        preSelect={
                          (searchTerm?.length ?? 0) > 0 &&
                          categoryInd === 0 &&
                          sourceInd === 0
                        }
                        onClick={handleConnectorClick}
                      />
                    ))}
                  </div>
                </div>
              ))}

            {hasLoadedWithNoResults && (
              <div className="pt-12 text-center">
                <Text as="p" secondaryBody textLight05>
                  {searchTerm
                    ? t("admin.addConnector.noResultsFor", { searchTerm })
                    : t("admin.addConnector.noConnectors")}
                </Text>
              </div>
            )}
          </>
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

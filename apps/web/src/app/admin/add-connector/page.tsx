"use client";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
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
import { useAirbyteConnectors, AirbyteConnector } from "@/lib/airbyte";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

// ── Connector tile ──────────────────────────────────────────────────────────

function connectorIconSrc(connector: AirbyteConnector): string | null {
  if (connector.icon_url) {
    // Raw SVG string → encode as data URL
    if (connector.icon_url.trimStart().startsWith("<svg")) {
      return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(connector.icon_url)}`;
    }
    return connector.icon_url;
  }
  if (connector.icon) return connector.icon;
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
  const iconSrc = connectorIconSrc(connector);
  return (
    <button
      onClick={() => onClick(connector)}
      className={`flex flex-col items-center gap-2 rounded-lg border p-4 w-36 text-center transition-colors hover:bg-background-tint-01 ${
        preSelect ? "border-blue-500 bg-background-tint-01" : "border-border"
      }`}
    >
      {iconSrc ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={iconSrc}
          alt=""
          className="h-8 w-8 shrink-0 object-contain"
        />
      ) : (
        <span className="h-8 w-8 shrink-0 rounded bg-background-tint-02 flex items-center justify-center text-sm font-bold text-text-02">
          {connector.display_name[0]}
        </span>
      )}
      <Text as="span" secondaryBody className="text-xs leading-tight line-clamp-2 text-center">
        {connector.display_name}
      </Text>
    </button>
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

  const { data: connectorsData, isLoading, error } = useAirbyteConnectors(
    searchTerm || undefined
  );

  // When searching, we get a flat list; otherwise grouped by category
  const byCategory = useMemo<Record<string, AirbyteConnector[]>>(() => {
    if (!connectorsData) return {};
    if (connectorsData.connectors) {
      // search result — put everything under a virtual "Results" category
      return connectorsData.connectors.length > 0 ? { Results: connectorsData.connectors } : {};
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

  const handleConnectorClick = useCallback((connector: AirbyteConnector) => {
    // connector.name is e.g. "source-postgres" → route slug is "source-postgres"
    // replace underscores with hyphens to match route convention
    const slug = connector.name.replace(/_/g, "-");
    router.push(`/admin/connectors/${slug}`);
  }, [router]);

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

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        rightChildren={
          <Button href="/admin/indexing/status" primary>
            {t("admin.addConnector.seeConnectors")}
          </Button>
        }
        separator
      />
      <SettingsLayouts.Body>
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
          <div className="pt-8">
            <Text as="p" secondaryBody textLight05>
              {t("admin.addConnector.loadingConnectors")}
            </Text>
          </div>
        ) : error ? (
          <div className="pt-12 text-center">
            <Text as="p" secondaryBody textLight05>
              {t("admin.addConnector.couldNotLoad")}
            </Text>
          </div>
        ) : (
          <>
            {categories
              .filter((cat) => (byCategory[cat]?.length ?? 0) > 0)
              .map((cat, categoryInd) => (
                <div key={cat} className="pt-8">
                  <Text as="p" headingH3>
                    {searchTerm
                      ? t("admin.addConnector.results")
                      : (categoryLabels[cat] ?? cat.charAt(0).toUpperCase() + cat.slice(1))}
                  </Text>
                  <div className="flex flex-wrap gap-4 p-4">
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

"use client";

import { useTranslation } from "react-i18next";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { ThreeDotsLoader } from "@/components/Loading";
import { ErrorCallout } from "@/components/ErrorCallout";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useState, useMemo } from "react";
import AgentCard from "@/sections/cards/AgentCard";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { useAgents } from "@/hooks/useAgents";

function AgentCatalog({
  agents,
  searchQuery,
  onSearchQueryChange,
}: {
  agents: MinimalPersonaSnapshot[];
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
}) {
  const { t } = useTranslation();

  const filteredAgents = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return agents;
    }

    return agents.filter((agent) => {
      const name = agent.name?.toLowerCase() || "";
      const description = agent.description?.toLowerCase() || "";
      const owner = agent.owner?.email?.toLowerCase() || "";
      return (
        name.includes(normalizedQuery) ||
        description.includes(normalizedQuery) ||
        owner.includes(normalizedQuery)
      );
    });
  }, [agents, searchQuery]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <Title>{t("admin.agents.catalogTitle")}</Title>
        <CreateButton href="/app/agents/create?admin=true">{t("admin.agents.createButton")}</CreateButton>
      </div>

      <Text>
        {t("admin.agents.catalogDescription")}
      </Text>

      <InputTypeIn
        placeholder={t("admin.agents.searchPlaceholder")}
        value={searchQuery}
        onChange={(event) => onSearchQueryChange(event.target.value)}
        leftSearchIcon
      />

      {filteredAgents.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {filteredAgents
            .slice()
            .sort((a, b) => {
              if (typeof a.id === "number" && typeof b.id === "number") {
                return b.id - a.id;
              }
              return a.name.localeCompare(b.name);
            })
            .map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
        </div>
      ) : (
        <div className="mt-2 p-6 border border-border rounded-lg bg-background-weak text-center">
          <Text>{t("admin.agents.noSearchResults")}</Text>
        </div>
      )}
    </div>
  );
}

function MainContent({
  catalogAgents,
  searchQuery,
  onSearchQueryChange,
}: {
  catalogAgents: MinimalPersonaSnapshot[];
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
}) {
  return (
    <div>
      <AgentCatalog
        agents={catalogAgents}
        searchQuery={searchQuery}
        onSearchQueryChange={onSearchQueryChange}
      />
    </div>
  );
}

export default function Page() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.AGENTS]!;
  const [searchQuery, setSearchQuery] = useState("");
  const {
    agents: catalogAgents,
    isLoading: isCatalogLoading,
    error: catalogError,
  } = useAgents();

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header icon={route.icon} title={route.title} separator />

      <SettingsLayouts.Body>
        {isCatalogLoading && <ThreeDotsLoader />}

        {catalogError && (
          <ErrorCallout
            errorTitle={t("admin.agents.errorTitle")}
            errorMsg={
              catalogError?.info?.message ||
              catalogError?.info?.detail ||
              t("admin.agents.errorUnknown")
            }
          />
        )}

        {!isCatalogLoading && !catalogError && (
          <MainContent
            catalogAgents={catalogAgents}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
          />
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

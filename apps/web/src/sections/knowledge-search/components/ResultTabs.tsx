"use client";

import { useTranslation } from "react-i18next";
import { SvgNetworkGraph } from "@opal/icons";
import { SvgListRows } from "@/icons/KnowledgeSearchIcons";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import type { SearchTab } from "@/sections/knowledge-search/model/searchState";

interface ResultTabsProps {
  tab: SearchTab;
  onTabChange: (tab: SearchTab) => void;
  resultCount: number;
  nodeCount: number;
  listPanel: React.ReactNode;
  graphPanel: React.ReactNode;
}

function isSearchTab(value: string): value is SearchTab {
  return value === "list" || value === "graph";
}

/** List / Graph views of one search result. */
export default function ResultTabs({
  tab,
  onTabChange,
  resultCount,
  nodeCount,
  listPanel,
  graphPanel,
}: ResultTabsProps) {
  const { t } = useTranslation();
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => {
        if (isSearchTab(value)) onTabChange(value);
      }}
    >
      <div className="flex items-center justify-between gap-3 pb-2">
        <Tabs.List
          variant="contained"
          aria-label={t("knowledgeSearch.tabs.label")}
          className="w-fit"
        >
          <Tabs.Trigger value="list" icon={SvgListRows}>
            <span className="flex items-center gap-1.5">
              <Text as="span">{t("knowledgeSearch.tabs.list")}</Text>
              <Text as="span" secondaryMono text02 className="tabular-nums">
                {resultCount}
              </Text>
            </span>
          </Tabs.Trigger>
          <Tabs.Trigger value="graph" icon={SvgNetworkGraph}>
            <span className="flex items-center gap-1.5">
              <Text as="span">{t("knowledgeSearch.tabs.graph")}</Text>
              <Text as="span" secondaryBody text02 className="tabular-nums">
                {t("knowledgeSearch.tabs.nodes", { count: nodeCount })}
              </Text>
            </span>
          </Tabs.Trigger>
        </Tabs.List>
        <Text as="span" secondaryBody text02>
          {t("knowledgeSearch.sortedByRelevance")}
        </Text>
      </div>
      {/*
        Tabs.Content wraps its panel in a Section that centres and
        shrink-wraps by default, so the panel took its intrinsic width and
        long result rows spilled sideways over the summary rail. Stretch it to
        the grid column instead so the cards truncate inside it.
      */}
      <Tabs.Content
        value="list"
        justifyContent="start"
        alignItems="stretch"
        height="fit"
      >
        {listPanel}
      </Tabs.Content>
      <Tabs.Content
        value="graph"
        justifyContent="start"
        alignItems="stretch"
        height="fit"
      >
        {graphPanel}
      </Tabs.Content>
    </Tabs>
  );
}

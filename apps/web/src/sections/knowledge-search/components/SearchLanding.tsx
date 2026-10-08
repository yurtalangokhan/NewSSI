"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import { Button } from "@opal/components";
import { SvgCheck, SvgHistory, SvgServer } from "@opal/icons";
import { filterByText } from "@/lib/text/textFilter";
import { cn } from "@/lib/utils";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import FadingEdgeContainer from "@/refresh-components/FadingEdgeContainer";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import Text from "@/refresh-components/texts/Text";
import LabeledSection from "@/sections/knowledge-search/components/LabeledSection";
import SearchBox from "@/sections/knowledge-search/components/SearchBox";
import {
  sourcePresentation,
  sourceSubtitle,
} from "@/sections/knowledge-search/components/sourcePresentation";
import type {
  KnowledgeSearchSource,
  RetrievalKind,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

interface SearchLandingProps {
  draft: string;
  kind: RetrievalKind;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  onKindChange: (kind: RetrievalKind) => void;
  graphDisabled: boolean;
  sources: readonly KnowledgeSearchSource[];
  sourcesLoading: boolean;
  sourcesError: Error | undefined;
  selectedCollectionIds: readonly string[];
  onCollectionToggle: (collectionId: string) => void;
  recentSearches: readonly string[];
  onRecentSelect: (query: string) => void;
  onClearRecent: () => void;
}

/** The first view: search box, searchable sources, and recent searches. */
export default function SearchLanding({
  draft,
  kind,
  onDraftChange,
  onSubmit,
  onClear,
  onKindChange,
  graphDisabled,
  sources,
  sourcesLoading,
  sourcesError,
  selectedCollectionIds,
  onCollectionToggle,
  recentSearches,
  onRecentSelect,
  onClearRecent,
}: SearchLandingProps) {
  const { t } = useTranslation();
  const selectedCount = selectedCollectionIds.length;
  const [sourceFilter, setSourceFilter] = useState("");

  const visibleSources = useMemo(
    () => filterByText(sources, sourceFilter, (source) => source.name),
    [sources, sourceFilter]
  );

  return (
    <div className="flex w-full flex-col items-center px-6 pb-14 pt-10 animate-in fade-in duration-200 motion-reduce:animate-none">
      <div className="flex w-full max-w-[52.5rem] flex-col items-center gap-6 rounded-16 border border-border-01 bg-background-tint-00 p-6 shadow-01">
        <div className="flex max-w-[40rem] flex-col items-center gap-2 text-center">
          <Text as="h1" headingH2 text05 className="text-balance">
            {t("knowledgeSearch.landing.title")}
          </Text>
          <Text as="p" mainUiMuted text03>
            {t("knowledgeSearch.landing.subtitle")}
          </Text>
        </div>

        <SearchBox
          value={draft}
          kind={kind}
          onChange={onDraftChange}
          onSubmit={onSubmit}
          onClear={onClear}
          onKindChange={onKindChange}
          graphDisabled={graphDisabled}
          shortcut
          autoFocus
        />

        {recentSearches.length > 0 && (
          <div className="w-full">
            <LabeledSection
              as="h2"
              title={t("knowledgeSearch.landing.recent")}
              action={
                <Button prominence="tertiary" size="md" onClick={onClearRecent}>
                  {t("knowledgeSearch.landing.clearRecent")}
                </Button>
              }
            >
              <div className="flex flex-wrap gap-2">
                {recentSearches.map((query) => (
                  <Button
                    key={query}
                    icon={SvgHistory}
                    prominence="secondary"
                    size="md"
                    onClick={() => onRecentSelect(query)}
                  >
                    {query}
                  </Button>
                ))}
              </div>
            </LabeledSection>
          </div>
        )}

        <div className="w-full">
          <LabeledSection
            as="h2"
            title={t("knowledgeSearch.landing.sources")}
            action={
              selectedCount > 0 ? (
                <Text as="span" secondaryBody text03>
                  {t("knowledgeSearch.landing.selectedSources", {
                    count: selectedCount,
                  })}
                </Text>
              ) : undefined
            }
          >
            {sourcesError ? (
              <Text as="p" secondaryBody text03>
                {t("knowledgeSearch.landing.sourcesError")}
              </Text>
            ) : sourcesLoading ? (
              <div
                role="status"
                className="flex items-center gap-2 rounded-12 border border-border-01 bg-background-neutral-01 px-3 py-2"
              >
                <SimpleLoader className="h-4 w-4 shrink-0" />
                <Text as="p" secondaryBody text03>
                  {t("knowledgeSearch.landing.sourcesLoading")}
                </Text>
              </div>
            ) : sources.length === 0 ? (
              <EmptyMessage
                icon={SvgServer}
                title={t("knowledgeSearch.landing.noSources")}
                description={t("knowledgeSearch.landing.noSourcesDescription")}
              />
            ) : (
              <>
                <InputTypeIn
                  variant="internal"
                  leftSearchIcon
                  placeholder={t("knowledgeSearch.landing.filterSources")}
                  aria-label={t("knowledgeSearch.landing.filterSources")}
                  value={sourceFilter}
                  onChange={(event) => setSourceFilter(event.target.value)}
                  className="max-w-[20rem]"
                />
                {visibleSources.length === 0 ? (
                  <Text as="p" secondaryBody text03>
                    {t("knowledgeSearch.landing.noMatchingSources")}
                  </Text>
                ) : (
                  <FadingEdgeContainer
                    direction="bottom"
                    className="max-h-[20rem] overflow-y-auto overscroll-contain pr-1"
                    fadeClassName="from-background-tint-00"
                  >
                    <div
                      role="group"
                      aria-label={t("knowledgeSearch.landing.sources")}
                      className="grid grid-cols-1 gap-2.5 sm:grid-cols-2"
                    >
                      {visibleSources.map((source) => {
                        const presentation = sourcePresentation(source);
                        const Icon = presentation.icon;
                        const pressed = selectedCollectionIds.includes(
                          source.id
                        );
                        return (
                          <Interactive.Base
                            key={source.id}
                            variant="select"
                            prominence="light"
                            selected={pressed}
                            group="group/SourceCard"
                            onClick={() => onCollectionToggle(source.id)}
                          >
                            <Interactive.Container
                              type="button"
                              aria-pressed={pressed}
                              heightVariant="fit"
                              widthVariant="full"
                              roundingVariant="default"
                            >
                              <span
                                className={cn(
                                  "flex w-full items-start gap-3 rounded-12 border p-3.5 text-left transition-colors",
                                  pressed
                                    ? "border-action-link-05 bg-action-link-01"
                                    : "border-border-01 bg-background-neutral-01 group-hover/SourceCard:bg-background-tint-01"
                                )}
                              >
                                <span
                                  className={cn(
                                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-08",
                                    presentation.tone
                                  )}
                                >
                                  <Icon className="h-4 w-4 stroke-inherit" />
                                </span>
                                <span className="flex min-w-0 flex-1 flex-col">
                                  <Text
                                    as="span"
                                    mainUiAction
                                    text05
                                    className={cn(
                                      "truncate",
                                      pressed && "text-action-link-05"
                                    )}
                                  >
                                    {source.name}
                                  </Text>
                                  <Text as="span" secondaryBody text03>
                                    {sourceSubtitle(source, t)}
                                  </Text>
                                </span>
                                {pressed && (
                                  <SvgCheck
                                    className="h-4 w-4 shrink-0 stroke-action-link-05"
                                    aria-hidden
                                  />
                                )}
                              </span>
                            </Interactive.Container>
                          </Interactive.Base>
                        );
                      })}
                    </div>
                  </FadingEdgeContainer>
                )}
              </>
            )}
          </LabeledSection>
        </div>
      </div>
    </div>
  );
}

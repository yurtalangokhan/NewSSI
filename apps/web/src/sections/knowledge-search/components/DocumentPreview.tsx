"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Tag } from "@opal/components";
import { SvgFileText, SvgServer } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import { HighlightedText } from "@/refresh-components/texts/HighlightedText";
import FileTypeBadge from "@/sections/knowledge-search/components/FileTypeBadge";
import PassageCard from "@/sections/knowledge-search/components/PassageCard";
import RelevanceMeter from "@/sections/knowledge-search/components/RelevanceMeter";
import KeyValueList from "@/sections/knowledge-search/components/KeyValueList";
import LabeledSection from "@/sections/knowledge-search/components/LabeledSection";
import PreviewBody from "@/sections/knowledge-search/components/PreviewBody";
import PreviewHeader from "@/sections/knowledge-search/components/PreviewHeader";
import {
  findChunkIndex,
  surroundingChunks,
} from "@/sections/knowledge-search/model/documentChunks";
import { documentTitle } from "@/sections/knowledge-search/model/resultsView";
import { useDocumentChunks } from "@/lib/api/domains/knowledge/hooks";
import type { KnowledgeSearchHit } from "@/lib/api/domains/knowledge/knowledge-search-types";

/** Extra chunk pages fetched automatically to locate the matched passage. */
const MAX_AUTO_PAGES = 5;

interface DocumentPreviewProps {
  hit: KnowledgeSearchHit;
  query: string;
  onClose: () => void;
}

/** A document passage with its surrounding passages and full document. */
export default function DocumentPreview({
  hit,
  query,
  onClose,
}: DocumentPreviewProps) {
  const { t } = useTranslation();
  const [showDocument, setShowDocument] = useState(false);
  const document = hit.document;
  const fileId = document?.fileId ?? null;
  const { chunks, stats, hasMore, loadMore, isLoadingMore, error } =
    useDocumentChunks(hit.collectionId, fileId);
  const matchedIndex = document
    ? findChunkIndex(chunks, hit.id, document.content)
    : -1;
  const autoPages = useRef(0);

  useEffect(() => {
    if (!fileId || matchedIndex >= 0 || !hasMore || isLoadingMore) return;
    if (autoPages.current >= MAX_AUTO_PAGES) return;
    autoPages.current += 1;
    loadMore();
  }, [fileId, matchedIndex, hasMore, isLoadingMore, loadMore]);

  if (!document) return null;
  const { previous, next } = surroundingChunks(chunks, matchedIndex);
  const total = stats?.total_chunks ?? chunks.length;

  return (
    <>
      <PreviewHeader
        marker={<FileTypeBadge fileType={document.fileType} />}
        title={documentTitle(document) ?? t("knowledgeSearch.hit.untitled")}
        onClose={onClose}
        tags={
          <>
            <Tag icon={SvgServer} title={hit.collectionName} />
            {document.page !== null && (
              <Tag
                title={t("knowledgeSearch.hit.page", { page: document.page })}
              />
            )}
            {document.section && <Tag title={`# ${document.section}`} />}
            <RelevanceMeter value={hit.relevance} />
          </>
        }
        actions={
          <>
            {fileId && (
              <Button
                icon={SvgFileText}
                prominence="secondary"
                onClick={() => setShowDocument((shown) => !shown)}
              >
                {showDocument
                  ? t("knowledgeSearch.preview.hideDocument")
                  : t("knowledgeSearch.preview.showDocument")}
              </Button>
            )}
          </>
        }
      />
      <PreviewBody>
        <LabeledSection title={t("knowledgeSearch.preview.matchedPassage")}>
          <PassageCard
            testId="matched-passage"
            highlighted
            label={
              matchedIndex >= 0
                ? t("knowledgeSearch.preview.chunkPosition", {
                    index: matchedIndex + 1,
                    total,
                  })
                : undefined
            }
          >
            <HighlightedText text={document.content} query={query} />
          </PassageCard>
        </LabeledSection>

        {error && (
          <Text as="p" secondaryBody text03>
            {t("knowledgeSearch.preview.loadError")}
          </Text>
        )}

        {fileId && (previous || next) && !showDocument && (
          <LabeledSection title={t("knowledgeSearch.preview.surrounding")}>
            {previous && (
              <PassageCard label={t("knowledgeSearch.preview.previous")}>
                {previous.content}
              </PassageCard>
            )}
            {next && (
              <PassageCard label={t("knowledgeSearch.preview.next")}>
                {next.content}
              </PassageCard>
            )}
          </LabeledSection>
        )}

        {fileId && showDocument && (
          <LabeledSection title={t("knowledgeSearch.preview.fullDocument")}>
            <ul
              aria-label={t("knowledgeSearch.preview.fullDocument")}
              className="flex flex-col gap-2"
            >
              {chunks.map((chunk, index) => (
                <li
                  key={chunk.id}
                  aria-current={index === matchedIndex ? "true" : undefined}
                >
                  <PassageCard
                    highlighted={index === matchedIndex}
                    label={t("knowledgeSearch.preview.chunkPosition", {
                      index: index + 1,
                      total,
                    })}
                  >
                    {index === matchedIndex ? (
                      <HighlightedText text={chunk.content} query={query} />
                    ) : (
                      chunk.content
                    )}
                  </PassageCard>
                </li>
              ))}
            </ul>
            {hasMore && (
              <div>
                <Button
                  prominence="secondary"
                  disabled={isLoadingMore}
                  onClick={loadMore}
                >
                  {t("knowledgeSearch.preview.loadMore")}
                </Button>
              </div>
            )}
          </LabeledSection>
        )}

        <LabeledSection title={t("knowledgeSearch.preview.metadata")}>
          <KeyValueList entries={document.metadata} />
        </LabeledSection>
      </PreviewBody>
    </>
  );
}

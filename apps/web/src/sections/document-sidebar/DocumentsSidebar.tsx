"use client";

import { MinimalOnyxDocument, OnyxDocument } from "@/lib/search/interfaces";
import ChatDocumentDisplay from "@/sections/document-sidebar/ChatDocumentDisplay";
import { Dispatch, SetStateAction, useMemo, memo } from "react";
import { getCitations } from "@/app/app/services/packetUtils";
import {
  useCurrentMessageTree,
  useSelectedNodeForDocDisplay,
} from "@/app/app/stores/useChatSessionStore";
import Text from "@/refresh-components/texts/Text";
import { Button } from "@opal/components";
import { SvgLink, SvgSearch, SvgSearchMenu, SvgX } from "@opal/icons";
import Separator from "@/refresh-components/Separator";
import { groupSourcesByDomain, splitMessageSources } from "./webSourceGrouping";
import DomainGroupedSources from "./DomainGroupedSources";

import { useTranslation } from "react-i18next";

// Build an OnyxDocument from basic file info
const buildOnyxDocumentFromFile = (
  id: string,
  name?: string | null,
  appendProjectPrefix?: boolean
): OnyxDocument => {
  const document_id = appendProjectPrefix ? `project_file__${id}` : id;
  return {
    document_id,
    semantic_identifier: name || id,
    link: "",
    source_type: "file" as any,
    blurb: "",
    boost: 0,
    hidden: false,
    score: 1,
    chunk_ind: 0,
    match_highlights: [],
    metadata: {},
    updated_at: null,
    is_internet: false,
  } as any;
};

interface HeaderProps {
  children: string;
  onClose: () => void;
}

function Header({ children, onClose }: HeaderProps) {
  const { t } = useTranslation("common", { keyPrefix: "documentSidebar" });
  return (
    <div className="sticky top-0 z-sticky bg-background-tint-01">
      <div className="flex flex-row w-full items-center justify-between gap-2 py-3">
        <div className="flex items-center gap-2 w-full px-3">
          <SvgSearchMenu className="w-[1.3rem] h-[1.3rem] stroke-text-03" />
          <Text as="p" headingH3 text03>
            {children}
          </Text>
        </div>
        <Button
          icon={SvgX}
          prominence="tertiary"
          onClick={onClose}
          tooltip={t("closeSidebarTooltip")}
        />
      </div>
      <Separator noPadding />
    </div>
  );
}

interface SectionHeaderProps {
  title: string;
  icon?: React.ReactNode;
}

function SectionHeader({ title, icon }: SectionHeaderProps) {
  return (
    <div className="flex items-center gap-2 px-1 pt-2 pb-1">
      {icon}
      <Text as="p" secondaryAction text03>
        {title}
      </Text>
    </div>
  );
}

interface ChatDocumentDisplayWrapperProps {
  children?: React.ReactNode;
}

function ChatDocumentDisplayWrapper({
  children,
}: ChatDocumentDisplayWrapperProps) {
  return (
    <div className="flex flex-col gap-1 items-center justify-center">
      {children}
    </div>
  );
}

interface DocumentsSidebarProps {
  closeSidebar: () => void;
  selectedDocuments: OnyxDocument[] | null;
  modal: boolean;
  setPresentingDocument: Dispatch<SetStateAction<MinimalOnyxDocument | null>>;
}

const DocumentsSidebar = memo(
  ({
    closeSidebar,
    modal,
    selectedDocuments,
    setPresentingDocument,
  }: DocumentsSidebarProps) => {
    const { t } = useTranslation("common", { keyPrefix: "documentSidebar" });
    const idOfMessageToDisplay = useSelectedNodeForDocDisplay();
    const currentMessageTree = useCurrentMessageTree();

    const selectedMessage = idOfMessageToDisplay
      ? currentMessageTree?.get(idOfMessageToDisplay)
      : null;

    // Get citations in order and build a set of cited document IDs (Hooks called unconditionally at top)
    const { citedDocumentIds, citationOrder } = useMemo(() => {
      if (!selectedMessage) {
        return {
          citedDocumentIds: new Set<string>(),
          citationOrder: new Map<string, number>(),
        };
      }

      const citedDocumentIds = new Set<string>();
      const citationOrder = new Map<string, number>();
      const citations = getCitations(selectedMessage.packets);
      citations.forEach((citation, index) => {
        citedDocumentIds.add(citation.document_id);
        // Only set the order for the first occurrence
        if (!citationOrder.has(citation.document_id)) {
          citationOrder.set(citation.document_id, index);
        }
      });
      return { citedDocumentIds, citationOrder };
    }, [idOfMessageToDisplay, selectedMessage?.packets]);

    const { readDocuments, searchDocuments, internalDocuments } =
      useMemo(() => {
        if (!selectedMessage) {
          return {
            readDocuments: [],
            searchDocuments: [],
            internalDocuments: [],
          };
        }
        return splitMessageSources(
          selectedMessage.packets || [],
          selectedMessage.documents || []
        );
      }, [selectedMessage?.packets, selectedMessage?.documents]);

    const citedInternalDocuments = useMemo(() => {
      return internalDocuments
        .filter(
          (doc) =>
            doc.document_id !== null &&
            doc.document_id !== undefined &&
            citedDocumentIds.has(doc.document_id)
        )
        .sort((a, b) => {
          const orderA = citationOrder.get(a.document_id) ?? Infinity;
          const orderB = citationOrder.get(b.document_id) ?? Infinity;
          return orderA - orderB;
        });
    }, [internalDocuments, citedDocumentIds, citationOrder]);

    const otherInternalDocuments = useMemo(() => {
      return internalDocuments.filter(
        (doc) =>
          doc.document_id === null ||
          doc.document_id === undefined ||
          !citedDocumentIds.has(doc.document_id)
      );
    }, [internalDocuments, citedDocumentIds]);

    if (!selectedMessage || !currentMessageTree) return null;

    const humanMessage = selectedMessage.parentNodeId
      ? currentMessageTree.get(selectedMessage.parentNodeId)
      : null;
    const humanFileDescriptors = humanMessage?.files.filter(
      (file) => file.user_file_id !== null
    );
    const selectedDocumentIds =
      selectedDocuments?.map((document) => document.document_id) || [];

    const hasRead = readDocuments.length > 0;
    const hasSearch = searchDocuments.length > 0;
    const hasCitedInternal = citedInternalDocuments.length > 0;
    const hasOtherInternal = otherInternalDocuments.length > 0;
    const hasUserFiles = Boolean(
      humanFileDescriptors && humanFileDescriptors.length > 0
    );

    const totalSourcesCount =
      readDocuments.length +
      searchDocuments.length +
      internalDocuments.length +
      (humanFileDescriptors?.length || 0);

    return (
      <div
        id="onyx-chat-sidebar"
        className="bg-background-tint-01 overflow-y-scroll h-full w-full border-l"
      >
        <Header onClose={closeSidebar}>
          {t("allSourcesHeader", { count: totalSourcesCount })}
        </Header>

        <div className="flex flex-col px-3 py-4 gap-6">
          {hasRead && (
            <div className="flex flex-col gap-2">
              <SectionHeader
                title={t("readPagesHeader", { count: readDocuments.length })}
                icon={<SvgLink className="w-4 h-4 stroke-text-03" />}
              />
              <DomainGroupedSources
                groups={groupSourcesByDomain(readDocuments)}
                modal={modal}
                selectedDocumentIds={selectedDocumentIds}
                setPresentingDocument={setPresentingDocument}
              />
            </div>
          )}

          {hasSearch && (
            <div className="flex flex-col gap-2">
              <SectionHeader
                title={t("searchResultsHeader", {
                  count: searchDocuments.length,
                })}
                icon={<SvgSearch className="w-4 h-4 stroke-text-03" />}
              />
              <DomainGroupedSources
                groups={groupSourcesByDomain(searchDocuments)}
                modal={modal}
                selectedDocumentIds={selectedDocumentIds}
                setPresentingDocument={setPresentingDocument}
              />
            </div>
          )}

          {hasCitedInternal && (
            <div className="flex flex-col gap-2">
              <SectionHeader title={t("citedSourcesHeader")} />
              <ChatDocumentDisplayWrapper>
                {citedInternalDocuments.map((document) => (
                  <ChatDocumentDisplay
                    key={document.document_id}
                    setPresentingDocument={setPresentingDocument}
                    modal={modal}
                    document={document}
                    isSelected={selectedDocumentIds.includes(
                      document.document_id
                    )}
                  />
                ))}
              </ChatDocumentDisplayWrapper>
            </div>
          )}

          {hasOtherInternal && (
            <div className="flex flex-col gap-2">
              <SectionHeader
                title={
                  hasCitedInternal
                    ? t("moreSourcesHeader")
                    : t("foundSourcesHeader")
                }
              />
              <ChatDocumentDisplayWrapper>
                {otherInternalDocuments.map((document) => (
                  <ChatDocumentDisplay
                    key={document.document_id}
                    setPresentingDocument={setPresentingDocument}
                    modal={modal}
                    document={document}
                    isSelected={selectedDocumentIds.includes(
                      document.document_id
                    )}
                  />
                ))}
              </ChatDocumentDisplayWrapper>
            </div>
          )}

          {hasUserFiles && humanFileDescriptors && (
            <div className="flex flex-col gap-2">
              <SectionHeader title={t("userFilesHeader")} />
              <ChatDocumentDisplayWrapper>
                {humanFileDescriptors.map((file) => (
                  <ChatDocumentDisplay
                    key={file.id}
                    setPresentingDocument={setPresentingDocument}
                    modal={modal}
                    document={buildOnyxDocumentFromFile(
                      file.id,
                      file.name,
                      false
                    )}
                    isSelected={false}
                  />
                ))}
              </ChatDocumentDisplayWrapper>
            </div>
          )}
        </div>
      </div>
    );
  }
);

DocumentsSidebar.displayName = "DocumentsSidebar";

export default DocumentsSidebar;

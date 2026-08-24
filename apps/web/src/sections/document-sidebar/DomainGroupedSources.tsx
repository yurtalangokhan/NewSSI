"use client";

import { Dispatch, SetStateAction, useState } from "react";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import { DomainGroup } from "./webSourceGrouping";
import ChatDocumentDisplay from "@/sections/document-sidebar/ChatDocumentDisplay";
import { WebResultIcon } from "@/components/WebResultIcon";
import Text from "@/refresh-components/texts/Text";
import { SvgChevronDown, SvgChevronRight } from "@opal/icons";

interface DomainGroupedSourcesProps {
  groups: DomainGroup[];
  modal?: boolean;
  selectedDocumentIds: string[];
  setPresentingDocument: Dispatch<SetStateAction<MinimalOnyxDocument | null>>;
}

function CollapsedDomainGroup({
  group,
  modal,
  selectedDocumentIds,
  setPresentingDocument,
}: {
  group: DomainGroup;
  modal?: boolean;
  selectedDocumentIds: string[];
  setPresentingDocument: Dispatch<SetStateAction<MinimalOnyxDocument | null>>;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex flex-col w-full">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 p-3 rounded-12 hover:bg-background-tint-00 cursor-pointer"
      >
        <WebResultIcon url={group.documents[0].link} />
        <Text as="span" className="flex-1 text-left" secondaryBody text03>
          {group.domain || group.documents[0].link}
        </Text>
        <Text as="span" secondaryBody text03>
          {group.documents.length}
        </Text>
        {expanded ? (
          <SvgChevronDown className="w-4 h-4" />
        ) : (
          <SvgChevronRight className="w-4 h-4" />
        )}
      </button>
      {expanded && (
        <div className="flex flex-col pl-4">
          {group.documents.map((document) => (
            <ChatDocumentDisplay
              key={document.document_id}
              setPresentingDocument={setPresentingDocument}
              modal={modal}
              document={document}
              isSelected={selectedDocumentIds.includes(document.document_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function DomainGroupedSources({
  groups,
  modal,
  selectedDocumentIds,
  setPresentingDocument,
}: DomainGroupedSourcesProps) {
  return (
    <div className="flex flex-col gap-1 items-center justify-center">
      {groups.map((group) =>
        group.documents.length > 1 ? (
          <CollapsedDomainGroup
            key={group.domain || group.documents[0].document_id}
            group={group}
            modal={modal}
            selectedDocumentIds={selectedDocumentIds}
            setPresentingDocument={setPresentingDocument}
          />
        ) : (
          <ChatDocumentDisplay
            key={group.documents[0].document_id}
            setPresentingDocument={setPresentingDocument}
            modal={modal}
            document={group.documents[0]}
            isSelected={selectedDocumentIds.includes(group.documents[0].document_id)}
          />
        )
      )}
    </div>
  );
}

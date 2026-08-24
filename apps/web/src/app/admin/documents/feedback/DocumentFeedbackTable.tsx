"use client";

import { toast } from "@/hooks/useToast";
import { useState } from "react";
import {
  Table,
  TableHead,
  TableRow,
  TableHeader,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { PageSelector } from "@/components/PageSelector";
import { DocumentBoostStatus } from "@/lib/types";
import { updateHiddenStatus } from "../lib";
import { numToDisplay } from "./constants";
import { FiEye, FiEyeOff } from "react-icons/fi";
import { getErrorMsg } from "@/lib/fetchUtils";
import { HoverPopup } from "@/components/HoverPopup";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import { ScoreSection } from "../ScoreEditor";
import { truncateString } from "@/lib/utils";
import { useTranslation } from "react-i18next";

const IsVisibleSection = ({
  document,
  onUpdate,
}: {
  document: DocumentBoostStatus;
  onUpdate: (response: Response) => void;
}) => {
  const { t } = useTranslation();
  return (
    <HoverPopup
      mainContent={
        document.hidden ? (
          <div
            onClick={async () => {
              const response = await updateHiddenStatus(
                document.document_id,
                false
              );
              onUpdate(response);
            }}
            className="flex text-error cursor-pointer hover:bg-accent-background-hovered py-1 px-2 w-fit rounded-full"
          >
            <div className="select-none">
              {t("admin.documentsFeedback.hidden")}
            </div>
            <div className="ml-1 my-auto">
              <Checkbox checked={false} />
            </div>
          </div>
        ) : (
          <div
            onClick={async () => {
              const response = await updateHiddenStatus(
                document.document_id,
                true
              );
              onUpdate(response);
            }}
            className="flex cursor-pointer hover:bg-accent-background-hovered py-1 px-2 w-fit rounded-full"
          >
            <div className="my-auto select-none">
              {t("admin.documentsFeedback.visible")}
            </div>
            <div className="ml-1 my-auto">
              <Checkbox checked={true} />
            </div>
          </div>
        )
      }
      popupContent={
        <div className="text-xs">
          {document.hidden ? (
            <div className="flex">
              <FiEye className="my-auto mr-1" />{" "}
              {t("admin.documentsFeedback.unhide")}
            </div>
          ) : (
            <div className="flex">
              <FiEyeOff className="my-auto mr-1" />
              {t("admin.documentsFeedback.unhide")}
            </div>
          )}
        </div>
      }
      direction="left"
    />
  );
};

export const DocumentFeedbackTable = ({
  documents,
  refresh,
}: {
  documents: DocumentBoostStatus[];
  refresh: () => void;
}) => {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  return (
    <div>
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.documentsFeedback.documentName")}</TableHead>
            <TableHead>{t("admin.documentsFeedback.isSearchable")}</TableHead>
            <TableHead>{t("admin.documentsFeedback.score")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents
            .slice((page - 1) * numToDisplay, page * numToDisplay)
            .map((document) => {
              return (
                <TableRow key={document.document_id}>
                  <TableCell className="whitespace-normal break-all">
                    <a
                      className="text-blue-600 dark:text-blue-300"
                      href={document.link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {truncateString(document.semantic_id, 100)}
                    </a>
                  </TableCell>
                  <TableCell>
                    <IsVisibleSection
                      document={document}
                      onUpdate={async (response) => {
                        if (response.ok) {
                          refresh();
                        } else {
                          toast.error(
                            t("admin.documentsFeedback.errorUpdatingHidden", {
                              error: getErrorMsg(response),
                            })
                          );
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="relative">
                      <div
                        key={document.document_id}
                        className="h-10 ml-auto mr-8"
                      >
                        <ScoreSection
                          documentId={document.document_id}
                          initialScore={document.boost}
                          refresh={refresh}
                        />
                      </div>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
        </TableBody>
      </Table>

      <div className="mt-3 flex">
        <div className="mx-auto">
          <PageSelector
            totalPages={Math.ceil(documents.length / numToDisplay)}
            currentPage={page}
            onPageChange={(newPage) => setPage(newPage)}
          />
        </div>
      </div>
    </div>
  );
};

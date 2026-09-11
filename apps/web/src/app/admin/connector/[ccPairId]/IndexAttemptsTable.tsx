"use client";

import { useState } from "react";
import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
  TableHeader,
} from "@/components/ui/table";
import Text from "@/components/ui/text";
import { Callout } from "@/components/ui/callout";
import { CCPairFullInfo } from "./types";
import { IndexAttemptSnapshot } from "@/lib/types";
import { IndexAttemptStatus } from "@/components/Status";
import { PageSelector } from "@/components/PageSelector";
import { localizeAndPrettify } from "@/lib/time";
import { getDocsProcessedPerMinute } from "@/lib/indexAttempt";
import { InfoIcon } from "@/components/icons/icons";
import ExceptionTraceModal from "@/components/modals/ExceptionTraceModal";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { SvgClock } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface IndexingAttemptsTableProps {
  ccPair: CCPairFullInfo;
  indexAttempts: IndexAttemptSnapshot[];
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function IndexAttemptsTable({
  indexAttempts,
  currentPage,
  totalPages,
  onPageChange,
}: IndexingAttemptsTableProps) {
  const { t } = useTranslation();
  const [indexAttemptTracePopupId, setIndexAttemptTracePopupId] = useState<
    number | null
  >(null);

  if (!indexAttempts?.length) {
    return (
      <Callout
        className="mt-4"
        title={t("admin.connector.indexAttempts.noAttemptsTitle")}
        type="notice"
      >
        {t("admin.connector.indexAttempts.noAttemptsDescription")}
      </Callout>
    );
  }

  const indexAttemptToDisplayTraceFor = indexAttempts?.find(
    (indexAttempt) => indexAttempt.id === indexAttemptTracePopupId
  );

  return (
    <>
      {indexAttemptToDisplayTraceFor?.full_exception_trace && (
        <ExceptionTraceModal
          onOutsideClick={() => setIndexAttemptTracePopupId(null)}
          exceptionTrace={indexAttemptToDisplayTraceFor.full_exception_trace}
        />
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>
              {t("admin.connector.indexAttempts.columns.timeStarted")}
            </TableHead>
            <TableHead>
              {t("admin.connector.indexAttempts.columns.status")}
            </TableHead>
            <TableHead className="whitespace-nowrap">
              {t("admin.connector.indexAttempts.columns.newDocs")}
            </TableHead>
            <TableHead>
              <SimpleTooltip
                tooltip={t("admin.connector.indexAttempts.tooltips.totalDocs")}
                side="top"
              >
                <span className="flex items-center">
                  {t("admin.connector.indexAttempts.columns.totalDocs")}
                  <InfoIcon className="ml-1 w-4 h-4" />
                </span>
              </SimpleTooltip>
            </TableHead>
            <TableHead>
              {t("admin.connector.indexAttempts.columns.errorMessage")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {indexAttempts.map((indexAttempt) => {
            const rawDocsPerMinute = getDocsProcessedPerMinute(indexAttempt);
            const docsPerMinute = rawDocsPerMinute
              ? Number(rawDocsPerMinute.toFixed(2))
              : null;
            const isReindexInProgress =
              indexAttempt.status === "in_progress" ||
              indexAttempt.status === "not_started";
            const reindexTooltip = isReindexInProgress
              ? t("admin.connector.indexAttempts.tooltips.reindexActive")
              : t("admin.connector.indexAttempts.tooltips.reindexPast");

            return (
              <TableRow key={indexAttempt.id}>
                <TableCell>
                  {indexAttempt.time_started
                    ? localizeAndPrettify(indexAttempt.time_started)
                    : "-"}
                </TableCell>
                <TableCell>
                  <IndexAttemptStatus
                    status={indexAttempt.status || "not_started"}
                  />
                  {docsPerMinute !== null ? (
                    <div className="text-xs mt-1">
                      {t("admin.connector.indexAttempts.docsPerMinute", {
                        count: docsPerMinute,
                      })}
                    </div>
                  ) : (
                    indexAttempt.status === "success" && (
                      <div className="text-xs mt-1">
                        {t("admin.connector.indexAttempts.noDocsProcessed")}
                      </div>
                    )
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex">
                    <div className="text-right">
                      <div>{indexAttempt.new_docs_indexed}</div>
                      {indexAttempt.docs_removed_from_index > 0 && (
                        <div className="text-xs w-52 text-wrap flex italic overflow-hidden whitespace-normal px-1">
                          {t("admin.connector.indexAttempts.removedDocs", {
                            count: indexAttempt.docs_removed_from_index,
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center">
                    {indexAttempt.total_docs_indexed}
                    {indexAttempt.from_beginning && (
                      <SimpleTooltip side="top" tooltip={reindexTooltip}>
                        <span className="cursor-help flex items-center">
                          <SvgClock className="ml-2 h-3.5 w-3.5 stroke-current" />
                        </span>
                      </SimpleTooltip>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div>
                    {indexAttempt.status === "success" && (
                      <Text className="flex flex-wrap whitespace-normal">
                        {"-"}
                      </Text>
                    )}

                    {indexAttempt.status === "failed" &&
                      indexAttempt.error_msg && (
                        <Text className="flex flex-wrap whitespace-normal">
                          {indexAttempt.error_msg}
                        </Text>
                      )}

                    {indexAttempt.full_exception_trace && (
                      <div
                        onClick={() => {
                          setIndexAttemptTracePopupId(indexAttempt.id);
                        }}
                        className="mt-2 text-link cursor-pointer select-none"
                      >
                        {t("admin.connector.indexAttempts.viewFullTrace")}
                      </div>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {totalPages > 1 && (
        <div className="mt-3 flex">
          <div className="mx-auto">
            <PageSelector
              totalPages={totalPages}
              currentPage={currentPage}
              onPageChange={onPageChange}
            />
          </div>
        </div>
      )}
    </>
  );
}

"use client";

import { useTranslation } from "react-i18next";
import { format } from "date-fns";
import { errorHandlingFetcher, authenticatedFetch } from "@/lib/fetcher";

import { FiDownload, FiDownloadCloud } from "react-icons/fi";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import Button from "@/refresh-components/buttons/Button";
import useSWR from "swr";
import React, { useState } from "react";
import { UsageReport } from "./types";
import TableSkeleton from "@/refresh-components/skeletons/TableSkeleton";
import Link from "next/link";
import { humanReadableFormat, humanReadableFormatWithTime } from "@/lib/time";
import { ErrorCallout } from "@/components/ErrorCallout";
import { PageSelector } from "@/components/PageSelector";
import Separator from "@/refresh-components/Separator";
import { DateRangePickerValue } from "../../../../../components/dateRangeSelectors/AdminDateRangeSelector";
import Popover from "@/refresh-components/Popover";
import Calendar from "@/refresh-components/Calendar";
import { cn } from "@/lib/utils";
import { SvgCalendar } from "@opal/icons";

function GenerateReportInput({
  onReportGenerated,
  isWaitingForReport,
}: {
  onReportGenerated: () => void;
  isWaitingForReport: boolean;
}) {
  const [dateRange, setDateRange] = useState<DateRangePickerValue | undefined>(
    undefined
  );
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);

  const [errorOccurred, setErrorOccurred] = useState<Error | null>(null);

  const requestReport = async () => {
    setIsLoading(true);
    setErrorOccurred(null);
    try {
      let period_from: string | null = null;
      let period_to: string | null = null;

      if (dateRange?.selectValue != "allTime" && dateRange?.from) {
        period_from = dateRange?.from?.toISOString();
        period_to = dateRange?.to?.toISOString() ?? new Date().toISOString();
      }

      const res = await authenticatedFetch("/api/admin/usage-report", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          period_from: period_from,
          period_to: period_to,
        }),
      });

      if (!res.ok) {
        throw Error(`Received an error: ${res.statusText}`);
      }

      // Trigger refresh of the reports list
      onReportGenerated();
    } catch (e) {
      setErrorOccurred(e as Error);
    } finally {
      setIsLoading(false);
    }
  };

  const today = new Date();

  const lastWeek = new Date();
  lastWeek.setDate(today.getDate() - 7);

  const lastMonth = new Date();
  lastMonth.setMonth(today.getMonth() - 1);

  const lastYear = new Date();
  lastYear.setFullYear(today.getFullYear() - 1);

  return (
    <div className="mb-8">
      <Title className="mb-2">{t("usageReports.generateTitle")}</Title>
      <Text className="mb-8">{t("usageReports.generateDescription")}</Text>
      <div className="grid gap-2 mb-3">
        <Popover>
          <Popover.Trigger asChild>
            <Button
              secondary
              className={cn(
                "w-[300px] justify-start text-left font-normal",
                !dateRange && "text-muted-foreground"
              )}
              leftIcon={SvgCalendar}
            >
              {dateRange?.from ? (
                dateRange.to ? (
                  <>
                    {format(dateRange.from, "LLL dd, y")} -{" "}
                    {format(dateRange.to, "LLL dd, y")}
                  </>
                ) : (
                  format(dateRange.from, "LLL dd, y")
                )
              ) : (
                <span>{t("usageReports.pickDateRange")}</span>
              )}
            </Button>
          </Popover.Trigger>
          <Popover.Content align="start">
            <Calendar
              initialFocus
              mode="range"
              defaultMonth={dateRange?.from}
              selected={dateRange}
              onSelect={(range) =>
                range?.from &&
                setDateRange({
                  from: range.from,
                  to: range.to ?? range.from,
                  selectValue: "custom",
                })
              }
              numberOfMonths={2}
              disabled={(date) => date > new Date()}
            />
            <div className="border-t p-3">
              <Button
                tertiary
                className="w-full justify-start"
                onClick={() => {
                  setDateRange({
                    from: lastWeek,
                    to: new Date(),
                    selectValue: "lastWeek",
                  });
                }}
              >
                {t("usageReports.last7Days")}
              </Button>
              <Button
                tertiary
                className="w-full justify-start"
                onClick={() => {
                  setDateRange({
                    from: lastMonth,
                    to: new Date(),
                    selectValue: "lastMonth",
                  });
                }}
              >
                {t("usageReports.last30Days")}
              </Button>
              <Button
                tertiary
                className="w-full justify-start"
                onClick={() => {
                  setDateRange({
                    from: lastYear,
                    to: new Date(),
                    selectValue: "lastYear",
                  });
                }}
              >
                {t("usageReports.lastYear")}
              </Button>
              <Button
                tertiary
                className="w-full justify-start"
                onClick={() => {
                  setDateRange({
                    from: new Date(1970, 0, 1),
                    to: new Date(),
                    selectValue: "allTime",
                  });
                }}
              >
                {t("usageReports.allTime")}
              </Button>
            </div>
          </Popover.Content>
        </Popover>
      </div>
      <Button
        color={"blue"}
        leftIcon={FiDownloadCloud}
        disabled={isLoading || isWaitingForReport}
        onClick={() => requestReport()}
      >
        {isWaitingForReport
          ? t("usageReports.generating")
          : t("usageReports.generateReport")}
      </Button>
      <Text className="mt-1 text-xs">
        {isWaitingForReport
          ? t("usageReports.generatingWait")
          : t("usageReports.backgroundGeneration")}
      </Text>
      {errorOccurred && (
        <ErrorCallout
          errorTitle={t("usageReports.somethingWentWrong")}
          errorMsg={errorOccurred?.toString()}
        />
      )}
    </div>
  );
}

const USAGE_REPORT_URL = "/api/admin/usage-report";

function UsageReportsTable({
  refreshTrigger,
  isWaitingForReport,
  onNewReportDetected,
}: {
  refreshTrigger: number;
  isWaitingForReport: boolean;
  onNewReportDetected: () => void;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const NUM_IN_PAGE = 10;
  const [previousReportCount, setPreviousReportCount] = useState<number | null>(
    null
  );

  const {
    data: usageReportsMetadata,
    error: usageReportsError,
    isLoading: usageReportsIsLoading,
    mutate,
  } = useSWR<UsageReport[]>(USAGE_REPORT_URL, errorHandlingFetcher, {
    refreshInterval: isWaitingForReport ? 3000 : 0, // Poll every 3 seconds when waiting
  });

  // Refresh when refreshTrigger changes
  React.useEffect(() => {
    if (refreshTrigger > 0) {
      mutate();
    }
  }, [refreshTrigger, mutate]);

  // Detect when a new report appears
  React.useEffect(() => {
    if (usageReportsMetadata && previousReportCount !== null) {
      if (usageReportsMetadata.length > previousReportCount) {
        onNewReportDetected();
      }
    }
    if (usageReportsMetadata) {
      setPreviousReportCount(usageReportsMetadata.length);
    }
  }, [usageReportsMetadata, previousReportCount, onNewReportDetected]);

  const paginatedReports = usageReportsMetadata
    ? usageReportsMetadata
        .slice(0)
        .reverse()
        .slice(NUM_IN_PAGE * (page - 1), NUM_IN_PAGE * page)
    : [];

  const totalPages = usageReportsMetadata
    ? Math.ceil(usageReportsMetadata.length / NUM_IN_PAGE)
    : 0;

  return (
    <div>
      <Title className="mb-2 mt-6 mx-auto">
        {t("usageReports.previousReports")}
      </Title>
      {usageReportsIsLoading && !isWaitingForReport ? (
        <div className="w-full">
          <TableSkeleton
            rowCount={3}
            columns={[
              { type: "text", width: "w-48", headerWidth: "w-24" },
              { type: "badge", width: "w-24", headerWidth: "w-16" },
              { type: "actions", width: "w-20", headerWidth: "w-16" },
            ]}
          />
        </div>
      ) : usageReportsError ? (
        <ErrorCallout
          errorTitle={t("usageReports.somethingWentWrong")}
          errorMsg={(usageReportsError as Error).toString()}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("usageReports.report")}</TableHead>
                <TableHead>{t("usageReports.period")}</TableHead>
                <TableHead>{t("usageReports.generatedBy")}</TableHead>
                <TableHead>{t("usageReports.timeGenerated")}</TableHead>
                <TableHead>{t("usageReports.download")}</TableHead>
              </TableRow>
            </TableHeader>

            <TableBody>
              {paginatedReports.map((r) => (
                <TableRow key={r.report_name}>
                  <TableCell>
                    {r.report_name.split("_")[1]?.substring(0, 8) ||
                      r.report_name.substring(0, 8)}
                  </TableCell>
                  <TableCell>
                    {r.period_from
                      ? `${humanReadableFormat(
                          r.period_from
                        )} - ${humanReadableFormat(r.period_to!)}`
                      : t("usageReports.allTimePeriod")}
                  </TableCell>
                  <TableCell>
                    {r.requestor ?? t("usageReports.autoGenerated")}
                  </TableCell>
                  <TableCell>
                    {humanReadableFormatWithTime(r.time_created)}
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/api/admin/usage-report/${r.report_name}`}
                      className="flex justify-center"
                    >
                      <FiDownload color="primary" />
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-3 flex">
            <div className="mx-auto">
              <PageSelector
                totalPages={totalPages}
                currentPage={page}
                onPageChange={(newPage) => {
                  setPage(newPage);
                  window.scrollTo({
                    top: 0,
                    left: 0,
                    behavior: "smooth",
                  });
                }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function UsageReports() {
  const { t } = useTranslation();
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isWaitingForReport, setIsWaitingForReport] = useState(false);
  const [timeoutMessage, setTimeoutMessage] = useState<string | null>(null);
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  const handleReportGenerated = () => {
    setRefreshTrigger((prev) => prev + 1);
    setIsWaitingForReport(true);
    setTimeoutMessage(null);

    // Clear any existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Set a 15 second timeout
    timeoutRef.current = setTimeout(() => {
      setIsWaitingForReport(false);
      setTimeoutMessage("timeout");
      timeoutRef.current = null;
    }, 15000);
  };

  const handleNewReportDetected = () => {
    setIsWaitingForReport(false);
    setTimeoutMessage(null);
    // Clear the timeout if report completed before timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  };

  // Cleanup on unmount
  React.useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return (
    <>
      <>
        <GenerateReportInput
          onReportGenerated={handleReportGenerated}
          isWaitingForReport={isWaitingForReport}
        />
        {timeoutMessage && (
          <div className="mb-4 p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-regular">
            <div className="flex items-start gap-2">
              <div className="text-amber-600 dark:text-amber-500 mt-0.5">
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <div className="flex-1">
                <Text className="text-amber-800 dark:text-amber-200 font-medium mb-1">
                  {t("usageReports.reportGenerationInProgress")}
                </Text>
                <Text className="text-amber-700 dark:text-amber-300 text-sm">
                  {timeoutMessage === "timeout"
                    ? t("usageReports.reportLongTime")
                    : timeoutMessage}
                </Text>
              </div>
            </div>
          </div>
        )}
        <Separator />
        <UsageReportsTable
          refreshTrigger={refreshTrigger}
          isWaitingForReport={isWaitingForReport}
          onNewReportDetected={handleNewReportDetected}
        />
      </>
    </>
  );
}

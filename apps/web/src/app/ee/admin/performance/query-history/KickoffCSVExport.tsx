import { authenticatedFetch } from "@/lib/fetcher";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import { useRef, useState } from "react";
import { DateRange } from "../../../../../components/dateRangeSelectors/AdminDateRangeSelector";
import { withRequestId, withDateRange } from "./utils";
import {
  CHECK_QUERY_HISTORY_EXPORT_STATUS_URL,
  DOWNLOAD_QUERY_HISTORY_URL,
  MAX_RETRIES,
  PREVIOUS_CSV_TASK_BUTTON_NAME,
  RETRY_COOLDOWN_MILLISECONDS,
} from "./constants";
import {
  CheckQueryHistoryExportStatusResponse,
  SpinnerStatus,
  StartQueryHistoryExportResponse,
} from "./types";
import { cn } from "@/lib/utils";
import { SvgLoader, SvgPlayCircle } from "@opal/icons";
import { useTranslation } from "react-i18next";
export default function KickoffCSVExport({
  dateRange,
}: {
  dateRange: DateRange;
}) {
  const timerIdRef = useRef<null | number>(null);
  const { t } = useTranslation();
  const retryCount = useRef<number>(0);
  const [, rerender] = useState<void>();
  const [spinnerStatus, setSpinnerStatus] = useState<SpinnerStatus>("static");

  const reset = (failure: boolean = false) => {
    setSpinnerStatus("static");
    if (timerIdRef.current) {
      clearInterval(timerIdRef.current);
      timerIdRef.current = null;
    }
    retryCount.current = 0;

    if (failure) {
      toast.error(t("admin.performance.queryHistory.downloadFailed"));
    }

    rerender();
  };

  const startExport = async () => {
    // If the button is pressed again while we're spinning, then we reset and cancel the request.
    if (spinnerStatus === "spinning") {
      reset();
      return;
    }

    setSpinnerStatus("spinning");
    toast.info(
      t("admin.performance.queryHistory.generatingCsv", {
        buttonName: PREVIOUS_CSV_TASK_BUTTON_NAME,
      })
    );
    const response = await authenticatedFetch(withDateRange(dateRange), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      reset(true);
      return;
    }

    const { request_id } =
      (await response.json()) as StartQueryHistoryExportResponse;
    const timer = setInterval(
      () => checkStatus(request_id),
      RETRY_COOLDOWN_MILLISECONDS
    ) as unknown as number;
    timerIdRef.current = timer;
    rerender();
  };

  const checkStatus = async (requestId: string) => {
    if (retryCount.current >= MAX_RETRIES) {
      reset();
      return;
    }
    retryCount.current += 1;
    rerender();

    const response = await fetch(
      withRequestId(CHECK_QUERY_HISTORY_EXPORT_STATUS_URL, requestId),
      {
        method: "GET",
      }
    );

    if (!response.ok) {
      reset(true);
      return;
    }

    const { status } =
      (await response.json()) as CheckQueryHistoryExportStatusResponse;

    if (status === "SUCCESS") {
      reset();
      window.location.href = withRequestId(
        DOWNLOAD_QUERY_HISTORY_URL,
        requestId
      );
    } else if (status === "FAILURE") {
      reset(true);
    }
  };

  return (
    <div className="flex flex-1 flex-col w-full justify-center">
      <Button
        className="ml-auto"
        onClick={startExport}
        danger={spinnerStatus === "spinning"}
        leftIcon={
          spinnerStatus === "spinning"
            ? ({ className }) => (
                <SvgLoader className={cn(className, "animate-spin")} />
              )
            : SvgPlayCircle
        }
      >
        {spinnerStatus === "spinning"
          ? t("admin.performance.queryHistory.cancel")
          : t("admin.performance.queryHistory.kickoffExport")}
      </Button>
    </div>
  );
}

import { systemEndpoints } from "@/lib/api/domains/system/endpoints";

export const LIST_QUERY_HISTORY_URL =
  systemEndpoints.queryHistoryList.browserPath;
export const START_QUERY_HISTORY_EXPORT_URL =
  systemEndpoints.queryHistoryStartExport.browserPath;
export const CHECK_QUERY_HISTORY_EXPORT_STATUS_URL =
  systemEndpoints.queryHistoryExportStatus.browserPath;
export const DOWNLOAD_QUERY_HISTORY_URL =
  systemEndpoints.queryHistoryDownload.browserPath;
export const MAX_RETRIES = 10;
export const RETRY_COOLDOWN_MILLISECONDS = 200;

export const ITEMS_PER_PAGE = 20;
export const PAGES_PER_BATCH = 2;
export const NUM_IN_PAGE = 10;

export const PREVIOUS_CSV_TASK_BUTTON_NAME = "View Exports";

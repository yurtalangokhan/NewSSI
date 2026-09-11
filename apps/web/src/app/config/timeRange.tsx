import { getXDaysAgo, getXYearsAgo } from "@/lib/dateUtils";

export function getTimeRangeValues(t: (key: string) => string) {
  return [
    {
      label: t("admin.documentExplorer.timeRanges.last2Years"),
      value: getXYearsAgo(2),
    },
    {
      label: t("admin.documentExplorer.timeRanges.lastYear"),
      value: getXYearsAgo(1),
    },
    {
      label: t("admin.documentExplorer.timeRanges.last30Days"),
      value: getXDaysAgo(30),
    },
    {
      label: t("admin.documentExplorer.timeRanges.last7Days"),
      value: getXDaysAgo(7),
    },
    {
      label: t("admin.documentExplorer.timeRanges.today"),
      value: getXDaysAgo(1),
    },
  ];
}

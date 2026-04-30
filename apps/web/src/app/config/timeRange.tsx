import { getXDaysAgo, getXYearsAgo } from "@/lib/dateUtils";

export const timeRangeValues = [
  {
    label: "Last 2 years",
    labelKey: "admin.documentExplorer.timeRanges.last2Years",
    value: getXYearsAgo(2),
  },
  {
    label: "Last year",
    labelKey: "admin.documentExplorer.timeRanges.lastYear",
    value: getXYearsAgo(1),
  },
  {
    label: "Last 30 days",
    labelKey: "admin.documentExplorer.timeRanges.last30Days",
    value: getXDaysAgo(30),
  },
  {
    label: "Last 7 days",
    labelKey: "admin.documentExplorer.timeRanges.last7Days",
    value: getXDaysAgo(7),
  },
  {
    label: "Today",
    labelKey: "admin.documentExplorer.timeRanges.today",
    value: getXDaysAgo(1),
  },
];

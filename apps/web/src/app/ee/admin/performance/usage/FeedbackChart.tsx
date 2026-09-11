import ChartSkeleton from "@/refresh-components/skeletons/ChartSkeleton";
import { getDatesList, useQueryAnalytics } from "../lib";
import Text from "@/refresh-components/texts/Text";
import Title from "@/components/ui/title";

import { DateRangePickerValue } from "@/components/dateRangeSelectors/AdminDateRangeSelector";
import CardSection from "@/components/admin/CardSection";
import { AreaChartDisplay } from "@/components/ui/areaChart";
import { useTranslation } from "react-i18next";

export function FeedbackChart({
  timeRange,
}: {
  timeRange: DateRangePickerValue;
}) {
  const { t } = useTranslation();
  const {
    data: queryAnalyticsData,
    isLoading: isQueryAnalyticsLoading,
    error: queryAnalyticsError,
  } = useQueryAnalytics(timeRange);

  let chart;
  if (isQueryAnalyticsLoading) {
    chart = <ChartSkeleton height="h-64" barCount={8} />;
  } else if (
    !queryAnalyticsData ||
    queryAnalyticsData[0] === undefined ||
    queryAnalyticsError
  ) {
    chart = (
      <div className="h-80 text-red-600 text-bold flex flex-col">
        <Text as="p" className="m-auto">
          {t("admin.performance.usage.feedbackFetchFailed")}
        </Text>
      </div>
    );
  } else {
    const initialDate = timeRange.from || new Date(queryAnalyticsData[0].date);
    const dateRange = getDatesList(initialDate);

    const dateToQueryAnalytics = new Map(
      queryAnalyticsData.map((queryAnalyticsEntry) => [
        queryAnalyticsEntry.date,
        queryAnalyticsEntry,
      ])
    );

    chart = (
      <AreaChartDisplay
        className="mt-4"
        data={dateRange.map((dateStr) => {
          const queryAnalyticsForDate = dateToQueryAnalytics.get(dateStr);
          return {
            Day: dateStr,
            [t("admin.performance.usage.positiveFeedback")]:
              queryAnalyticsForDate?.total_likes || 0,
            [t("admin.performance.usage.negativeFeedback")]:
              queryAnalyticsForDate?.total_dislikes || 0,
          };
        })}
        categories={[
          t("admin.performance.usage.positiveFeedback"),
          t("admin.performance.usage.negativeFeedback"),
        ]}
        index="Day"
        colors={["indigo", "fuchsia"]}
        yAxisWidth={60}
      />
    );
  }

  return (
    <CardSection className="mt-8">
      <Title>{t("admin.performance.usage.feedbackTitle")}</Title>
      <Text as="p" className="text-sm">
        {t("admin.performance.usage.feedbackDescription")}
      </Text>
      {chart}
    </CardSection>
  );
}

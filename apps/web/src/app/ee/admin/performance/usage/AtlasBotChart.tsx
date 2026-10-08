import { useTranslation } from "react-i18next";
import ChartSkeleton from "@/refresh-components/skeletons/ChartSkeleton";
import { getDatesList, useAtlasBotAnalytics } from "../lib";
import { DateRangePickerValue } from "@/lib/api/domains/knowledge/types";
import Text from "@/refresh-components/texts/Text";
import Title from "@/components/ui/title";
import CardSection from "@/components/admin/CardSection";
import { AreaChartDisplay } from "@/components/ui/areaChart";

export function AtlasBotChart({
  timeRange,
}: {
  timeRange: DateRangePickerValue;
}) {
  const { t } = useTranslation();
  const {
    data: atlasBotAnalyticsData,
    isLoading: isAtlasBotAnalyticsLoading,
    error: atlasBotAnalyticsError,
  } = useAtlasBotAnalytics(timeRange);

  let chart;
  if (isAtlasBotAnalyticsLoading) {
    chart = <ChartSkeleton height="h-64" barCount={8} />;
  } else if (
    !atlasBotAnalyticsData ||
    atlasBotAnalyticsData[0] == undefined ||
    atlasBotAnalyticsError
  ) {
    chart = (
      <div className="h-80 text-red-600 text-bold flex flex-col">
        <Text as="p" className="m-auto">
          {t("performanceCharts.failedFetchFeedback")}
        </Text>
      </div>
    );
  } else {
    const initialDate =
      timeRange.from || new Date(atlasBotAnalyticsData[0].date);
    const dateRange = getDatesList(initialDate);

    const dateToAtlasBotAnalytics = new Map(
      atlasBotAnalyticsData.map((atlasBotAnalyticsEntry) => [
        atlasBotAnalyticsEntry.date,
        atlasBotAnalyticsEntry,
      ])
    );

    const dayLabel = t("performanceCharts.dayLabel");
    const totalQueriesLabel = t("performanceCharts.totalQueriesLabel");
    const autoResolvedLabel = t("performanceCharts.autoResolvedLabel");

    chart = (
      <AreaChartDisplay
        className="mt-4"
        data={dateRange.map((dateStr) => {
          const atlasBotAnalyticsForDate = dateToAtlasBotAnalytics.get(dateStr);
          return {
            [dayLabel]: dateStr,
            [totalQueriesLabel]: atlasBotAnalyticsForDate?.total_queries || 0,
            [autoResolvedLabel]: atlasBotAnalyticsForDate?.auto_resolved || 0,
          };
        })}
        categories={[totalQueriesLabel, autoResolvedLabel]}
        index={dayLabel}
        colors={["indigo", "fuchsia"]}
        yAxisWidth={60}
      />
    );
  }

  return (
    <CardSection className="mt-8">
      <Title>{t("performanceCharts.slackChannelTitle")}</Title>
      <Text as="p" className="text-sm">
        {t("performanceCharts.totalVsAutoResolved")}
      </Text>
      {chart}
    </CardSection>
  );
}

import { useTranslation } from "react-i18next";
import { ThreeDotsLoader } from "@/components/Loading";
import { getDatesList, useOnyxBotAnalytics } from "../lib";
import { DateRangePickerValue } from "@/components/dateRangeSelectors/AdminDateRangeSelector";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import CardSection from "@/components/admin/CardSection";
import { AreaChartDisplay } from "@/components/ui/areaChart";

export function OnyxBotChart({
  timeRange,
}: {
  timeRange: DateRangePickerValue;
}) {
  const { t } = useTranslation();
  const {
    data: onyxBotAnalyticsData,
    isLoading: isOnyxBotAnalyticsLoading,
    error: onyxBotAnalyticsError,
  } = useOnyxBotAnalytics(timeRange);

  let chart;
  if (isOnyxBotAnalyticsLoading) {
    chart = (
      <div className="h-80 flex flex-col">
        <ThreeDotsLoader />
      </div>
    );
  } else if (
    !onyxBotAnalyticsData ||
    onyxBotAnalyticsData[0] == undefined ||
    onyxBotAnalyticsError
  ) {
    chart = (
      <div className="h-80 text-red-600 text-bold flex flex-col">
        <p className="m-auto">{t("performanceCharts.failedFetchFeedback")}</p>
      </div>
    );
  } else {
    const initialDate =
      timeRange.from || new Date(onyxBotAnalyticsData[0].date);
    const dateRange = getDatesList(initialDate);

    const dateToOnyxBotAnalytics = new Map(
      onyxBotAnalyticsData.map((onyxBotAnalyticsEntry) => [
        onyxBotAnalyticsEntry.date,
        onyxBotAnalyticsEntry,
      ])
    );

    const dayLabel = t("performanceCharts.dayLabel");
    const totalQueriesLabel = t("performanceCharts.totalQueriesLabel");
    const autoResolvedLabel = t("performanceCharts.autoResolvedLabel");

    chart = (
      <AreaChartDisplay
        className="mt-4"
        data={dateRange.map((dateStr) => {
          const onyxBotAnalyticsForDate = dateToOnyxBotAnalytics.get(dateStr);
          return {
            [dayLabel]: dateStr,
            [totalQueriesLabel]: onyxBotAnalyticsForDate?.total_queries || 0,
            [autoResolvedLabel]:
              onyxBotAnalyticsForDate?.auto_resolved || 0,
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
      <Text>{t("performanceCharts.totalVsAutoResolved")}</Text>
      {chart}
    </CardSection>
  );
}

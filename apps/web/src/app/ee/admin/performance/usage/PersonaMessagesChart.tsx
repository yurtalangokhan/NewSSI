import { useTranslation } from "react-i18next";
import { ThreeDotsLoader } from "@/components/Loading";
import { X, Search } from "lucide-react";
import {
  getDatesList,
  usePersonaMessages,
  usePersonaUniqueUsers,
} from "../lib";
import { DateRangePickerValue } from "@/components/dateRangeSelectors/AdminDateRangeSelector";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import CardSection from "@/components/admin/CardSection";
import { AreaChartDisplay } from "@/components/ui/areaChart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useState, useMemo, useEffect } from "react";
import { Persona } from "@/app/admin/agents/interfaces";

export function PersonaMessagesChart({
  availablePersonas,
  timeRange,
}: {
  availablePersonas: Persona[];
  timeRange: DateRangePickerValue;
}) {
  const { t } = useTranslation();
  const [selectedPersonaId, setSelectedPersonaId] = useState<
    number | undefined
  >(undefined);
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const {
    data: personaMessagesData,
    isLoading: isPersonaMessagesLoading,
    error: personaMessagesError,
  } = usePersonaMessages(selectedPersonaId, timeRange);

  const {
    data: personaUniqueUsersData,
    isLoading: isPersonaUniqueUsersLoading,
    error: personaUniqueUsersError,
  } = usePersonaUniqueUsers(selectedPersonaId, timeRange);

  const isLoading = isPersonaMessagesLoading || isPersonaUniqueUsersLoading;
  const hasError = personaMessagesError || personaUniqueUsersError;

  const filteredPersonaList = useMemo(() => {
    if (!availablePersonas) return [];
    return availablePersonas.filter((persona) =>
      persona.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [availablePersonas, searchQuery]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    e.stopPropagation();

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < filteredPersonaList.length - 1 ? prev + 1 : prev
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : prev));
        break;
      case "Enter":
        if (
          highlightedIndex >= 0 &&
          highlightedIndex < filteredPersonaList.length
        ) {
          const filteredPersona = filteredPersonaList[highlightedIndex];
          if (filteredPersona !== undefined) {
            setSelectedPersonaId(filteredPersona.id);
            setSearchQuery("");
            setHighlightedIndex(-1);
          }
        }
        break;
      case "Escape":
        setSearchQuery("");
        setHighlightedIndex(-1);
        break;
    }
  };

  // Reset highlight when search query changes
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [searchQuery]);

  const chartData = useMemo(() => {
    if (
      !personaMessagesData?.length ||
      !personaUniqueUsersData?.length ||
      selectedPersonaId === undefined
    ) {
      return null;
    }

    const initialDate =
      timeRange.from ||
      new Date(
        Math.min(
          ...personaMessagesData.map((entry) => new Date(entry.date).getTime())
        )
      );
    const dateRange = getDatesList(initialDate);

    // Create maps for messages and unique users data
    const messagesMap = new Map(
      personaMessagesData.map((entry) => [entry.date, entry])
    );
    const uniqueUsersMap = new Map(
      personaUniqueUsersData.map((entry) => [entry.date, entry])
    );

    return dateRange.map((dateStr) => {
      const messageData = messagesMap.get(dateStr);
      const uniqueUserData = uniqueUsersMap.get(dateStr);
      return {
        [t("performanceCharts.dayLabel")]: dateStr,
        [t("performanceCharts.messagesLabel")]: messageData?.total_messages || 0,
        [t("performanceCharts.uniqueUsersLabel")]: uniqueUserData?.unique_users || 0,
      };
    });
  }, [
    personaMessagesData,
    personaUniqueUsersData,
    timeRange.from,
    selectedPersonaId,
    t,
  ]);

  let content;
  if (isLoading) {
    content = (
      <div className="h-80 flex flex-col">
        <ThreeDotsLoader />
      </div>
    );
  } else if (!availablePersonas || hasError) {
    content = (
      <div className="h-80 text-red-600 text-bold flex flex-col">
        <p className="m-auto">{t("performanceCharts.failedFetchData")}</p>
      </div>
    );
  } else if (selectedPersonaId === undefined) {
    content = (
      <div className="h-80 text-text-500 flex flex-col">
        <p className="m-auto">{t("performanceCharts.selectAgentToView")}</p>
      </div>
    );
  } else if (!personaMessagesData?.length) {
    content = (
      <div className="h-80 text-text-500 flex flex-col">
        <p className="m-auto">
          {t("performanceCharts.noDataForAgent")}
        </p>
      </div>
    );
  } else if (chartData) {
    content = (
      <AreaChartDisplay
        className="mt-4"
        data={chartData}
        categories={[t("performanceCharts.messagesLabel"), t("performanceCharts.uniqueUsersLabel")]}
        index={t("performanceCharts.dayLabel")}
        colors={["indigo", "fuchsia"]}
        yAxisWidth={60}
      />
    );
  }

  return (
    <CardSection className="mt-8">
      <Title>{t("performanceCharts.agentAnalyticsTitle")}</Title>
      <div className="flex flex-col gap-4">
        <Text>{t("performanceCharts.messagesPerDay")}</Text>
        <div className="flex items-center gap-4">
          <Select
            value={selectedPersonaId?.toString() ?? ""}
            onValueChange={(value) => {
              setSelectedPersonaId(parseInt(value));
            }}
          >
            <SelectTrigger className="flex w-full max-w-xs">
              <SelectValue placeholder={t("performanceCharts.selectAgent")} />
            </SelectTrigger>
            <SelectContent>
              <div className="flex items-center px-2 pb-2 sticky top-0 bg-background border-b">
                <Search className="h-4 w-4 mr-2 shrink-0 opacity-50" />
                <input
                  className="flex h-8 w-full rounded-sm bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder={t("performanceCharts.searchAgents")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  onKeyDown={handleKeyDown}
                />
                {searchQuery && (
                  <X
                    className="h-4 w-4 shrink-0 opacity-50 cursor-pointer hover:opacity-100"
                    onClick={() => {
                      setSearchQuery("");
                      setHighlightedIndex(-1);
                    }}
                  />
                )}
              </div>
              {filteredPersonaList.map((persona, index) => (
                <SelectItem
                  key={persona.id}
                  value={persona.id.toString()}
                  className={`${highlightedIndex === index ? "hover" : ""}`}
                  onMouseEnter={() => setHighlightedIndex(index)}
                >
                  {persona.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {content}
    </CardSection>
  );
}

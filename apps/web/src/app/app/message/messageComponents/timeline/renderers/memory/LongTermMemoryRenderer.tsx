"use client";

import {
  MessageRenderer,
  RenderType,
} from "@/app/app/message/messageComponents/interfaces";
import { useTranslation } from "react-i18next";
import { BlinkingBar } from "@/app/app/message/BlinkingBar";
import Text from "@/refresh-components/texts/Text";
import { SvgEditBig } from "@opal/icons";
import { LongTermMemoryObj, Packet } from "@/app/app/services/streamingModels";

interface LtmState {
  isRecall: boolean;
  isSave: boolean;
  memories: string[];
  saved: string[];
  recallCount: number;
  isComplete: boolean;
}

function buildLtmState(packets: Packet[]): LtmState {
  let isRecall = false;
  let isSave = false;
  const memories: string[] = [];
  const saved: string[] = [];
  let recallCount = 0;
  let isComplete = false;

  for (const packet of packets) {
    const obj = packet.obj as LongTermMemoryObj;
    if (obj.type === "long_term_memory_recall") {
      isRecall = true;
      if (Array.isArray(obj.memories)) memories.push(...obj.memories);
      // fact_count is set when loaded from history (memories array is empty)
      recallCount = obj.fact_count ?? memories.length;
      isComplete = true;
    }
    if (obj.type === "long_term_memory_save") {
      isSave = true;
      if (Array.isArray(obj.saved)) saved.push(...obj.saved);
      isComplete = true;
    }
  }

  return { isRecall, isSave, memories, saved, recallCount, isComplete };
}

export const LongTermMemoryRenderer: MessageRenderer<any, {}> = ({
  packets,
  stopPacketSeen,
  renderType,
  children,
}) => {
  const { t } = useTranslation();
  const state = buildLtmState(packets);
  const isHighlight = renderType === RenderType.HIGHLIGHT;

  if (!state.isComplete && !stopPacketSeen) {
    return children([
      {
        icon: SvgEditBig,
        status: state.isRecall
          ? t("timeline.ltmRecalling")
          : t("timeline.ltmSaving"),
        content: <BlinkingBar />,
        supportsCollapsible: false,
        timelineLayout: "timeline" as const,
      },
    ]);
  }

  const label = state.isRecall
    ? t("timeline.ltmRecalled", { count: state.recallCount })
    : t("timeline.ltmSaved", { count: state.saved.length });

  const items = state.isRecall ? state.memories : state.saved;

  const content = (
    <div className="flex flex-col gap-1">
      {items.slice(0, 3).map((item, i) => (
        <Text key={i} as="p" text03 className="text-sm truncate">
          {item}
        </Text>
      ))}
      {items.length > 3 && (
        <Text as="p" text03 className="text-sm italic">
          +{items.length - 3} {t("timeline.ltmMore")}
        </Text>
      )}
    </div>
  );

  if (isHighlight) {
    return children([
      {
        icon: null,
        status: null,
        supportsCollapsible: false,
        timelineLayout: "content" as const,
        content: (
          <div className="flex flex-col">
            <Text as="p" text02 className="text-sm mb-1">
              {label}
            </Text>
            {content}
          </div>
        ),
      },
    ]);
  }

  return children([
    {
      icon: SvgEditBig,
      status: label,
      supportsCollapsible: items.length > 0,
      timelineLayout: "timeline" as const,
      content,
    },
  ]);
};

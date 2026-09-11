"use client";

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgUserManage } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import {
  HumanInputPacket,
  HumanInputRequest,
  PacketType,
} from "../../../services/streamingModels";
import { MessageRenderer } from "../interfaces";

/**
 * A FlowAgent run parked at a HumanInput node: shows the node's prompt and one
 * button per declared action.
 *
 * Picking an action is an ordinary send of that action's label. The backend
 * already knows the thread is sitting on an interrupt and turns the next
 * message into `Command(resume=...)` (AgentHelpers), so no separate resume
 * endpoint is needed — and the decision lands in the transcript, which is what
 * you want for an approval step.
 *
 * The buttons are a shortcut, not the only way in: typing the label by hand
 * resumes the run exactly the same way. That is also what keeps a page reload
 * usable, since the pending interrupt lives in the checkpoint but this packet
 * is live-only.
 */
export const HumanInputRenderer: MessageRenderer<HumanInputPacket, any> = ({
  packets,
  state,
  children,
}) => {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<string | null>(null);

  const request = packets.find((p) => p.obj.type === PacketType.HUMAN_INPUT)
    ?.obj as HumanInputRequest | undefined;

  if (!request) {
    return children([{ icon: null, status: null, content: <></> }]);
  }

  const decisions = (request.decisions ?? []).filter(
    (d) => typeof d === "string" && d.trim() !== ""
  );
  // Once a decision is sent the run is no longer parked, so the buttons must
  // not offer a second answer that would be read as a brand new turn.
  const locked = picked !== null || state?.isStreaming === true;

  return children([
    {
      icon: null,
      status: null,
      timelineLayout: "content",
      content: (
        <div
          data-testid="human-input-request"
          className="my-2 flex w-full flex-col gap-3 rounded-lg border border-border-02 bg-background-tint-01 p-4"
        >
          <div className="flex items-start gap-2">
            <SvgUserManage className="mt-0.5 h-4 w-4 shrink-0 stroke-text-03" />
            <div className="flex flex-col gap-1">
              <Text text03 secondaryBody>
                {t("humanInput.waiting", "Kararınız bekleniyor")}
              </Text>
              {request.prompt && (
                <Text mainContentBody className="whitespace-pre-wrap">
                  {request.prompt}
                </Text>
              )}
            </div>
          </div>

          {decisions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {decisions.map((decision, index) => (
                <Button
                  key={decision}
                  data-testid={`human-input-decision-${decision}`}
                  prominence={index === 0 ? "primary" : "secondary"}
                  disabled={locked}
                  onClick={() => {
                    if (locked) return;
                    setPicked(decision);
                    state?.onHumanDecision?.(decision);
                  }}
                >
                  {decision}
                </Button>
              ))}
            </div>
          )}

          {picked !== null && (
            <Text text03 secondaryBody data-testid="human-input-picked">
              {t("humanInput.picked", "Seçiminiz: {{decision}}", {
                decision: picked,
              })}
            </Text>
          )}
        </div>
      ),
    },
  ]);
};

export default HumanInputRenderer;

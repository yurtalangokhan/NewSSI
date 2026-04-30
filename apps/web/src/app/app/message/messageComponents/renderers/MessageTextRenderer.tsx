"use client";

import React, { useEffect, useMemo, useState } from "react";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

import {
  ChatPacket,
  StopReason,
} from "../../../services/streamingModels";
import { MessageRenderer, FullChatState } from "../interfaces";
import {
  isFinalAnswerComplete,
  getTextContent,
} from "../../../services/packetUtils";
import { useMarkdownRenderer } from "../markdownUtils";
import { BlinkingBar } from "../../BlinkingBar";

// Control the rate of packet streaming (packets per second)
const PACKET_DELAY_MS = 10;

export const MessageTextRenderer: MessageRenderer<
  ChatPacket,
  FullChatState
> = ({
  packets,
  state,
  onComplete,
  renderType,
  animate,
  stopPacketSeen,
  stopReason,
  children,
}) => {
  // If we're animating and the final answer is already complete, show more packets initially
  const initialPacketCount = animate
    ? packets.length > 0
      ? 1 // Otherwise start with 1 packet
      : 0
    : -1; // Show all if not animating

  const [displayedPacketCount, setDisplayedPacketCount] =
    useState(initialPacketCount);

  const fullContent = useMemo(() => getTextContent(packets), [packets]);

  // Animation effect - gradually increase displayed packets at controlled rate
  useEffect(() => {
    if (displayedPacketCount === -1) return; // historical message, no animation

    if (displayedPacketCount < packets.length) {
      const timer = setTimeout(() => {
        setDisplayedPacketCount((prev) => Math.min(prev + 1, packets.length));
      }, PACKET_DELAY_MS);

      return () => clearTimeout(timer);
    }
  }, [displayedPacketCount, packets.length]);

  // Reset displayed count when packet array changes significantly (e.g., new message)
  useEffect(() => {
    if (animate && packets.length < displayedPacketCount) {
      const resetCount = isFinalAnswerComplete(packets)
        ? Math.min(10, packets.length)
        : packets.length > 0
          ? 1
          : 0;
      setDisplayedPacketCount(resetCount);
    }
  }, [animate, packets.length, displayedPacketCount]);

  // Only mark as complete when all packets are received AND displayed
  useEffect(() => {
    if (isFinalAnswerComplete(packets)) {
      if (displayedPacketCount >= 0 && displayedPacketCount < packets.length) {
        return; // animation still in progress, wait
      }
      onComplete();
    }
  }, [packets, onComplete, displayedPacketCount]);

  // Get content based on displayed packet count
  const content = useMemo(() => {
    if (displayedPacketCount === -1 || displayedPacketCount >= packets.length) {
      return fullContent;
    }

    return getTextContent(packets.slice(0, displayedPacketCount));
  }, [displayedPacketCount, fullContent, packets]);

  const { renderedContent } = useMarkdownRenderer(
    // the [*]() is a hack to show a blinking dot when the packet is not complete
    stopPacketSeen ? content : content + " [*]() ",
    state,
    "font-main-content-body"
  );

  const { t } = useTranslation();
  const wasUserCancelled = stopReason === StopReason.USER_CANCELLED;

  return children([
    {
      icon: null,
      status: null,
      content:
        content.length > 0 || packets.length > 0 ? (
          <>
            {renderedContent}
            {wasUserCancelled && (
              <Text as="p" secondaryBody text04>
                {t("messageText.userStoppedGeneration")}
              </Text>
            )}
          </>
        ) : (
          <BlinkingBar addMargin />
        ),
    },
  ]);
};

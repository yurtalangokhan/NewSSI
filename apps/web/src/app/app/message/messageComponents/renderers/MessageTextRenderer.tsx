"use client";

import { useEffect, useMemo, useState } from "react";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

import { ChatPacket, StopReason } from "@/lib/api/domains/chat/streaming-types";
import { MessageRenderer, FullChatState } from "../interfaces";
import {
  countReplayedPrefix,
  isFinalAnswerComplete,
  getTextContent,
} from "../../../services/packetUtils";
import { useMarkdownRenderer } from "../markdownUtils";
import { BlinkingBar } from "../../BlinkingBar";
import { useAppBackground } from "@/providers/AppBackgroundProvider";

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
  // Packets that arrived while the stream replayed the run's history (a page
  // reload or re-attach) are already "typed": only what follows them animates.
  const replayedPrefix = countReplayedPrefix(packets);

  // If we're animating, start with the first packet (or the whole replayed
  // prefix); if not, show everything.
  const initialPacketCount = animate
    ? packets.length > 0
      ? Math.max(1, replayedPrefix)
      : 0
    : -1; // Show all if not animating

  const [storedPacketCount, setDisplayedPacketCount] =
    useState(initialPacketCount);
  // Derived rather than stored, so a replay that lands on text already typing
  // shows in the same render instead of catching up a packet per tick.
  const displayedPacketCount =
    storedPacketCount === -1
      ? -1
      : Math.min(Math.max(storedPacketCount, replayedPrefix), packets.length);

  const fullContent = useMemo(() => getTextContent(packets), [packets]);
  const { foregroundTextStyle, foregroundMutedTextStyle } = useAppBackground();

  // Animation effect - gradually increase displayed packets at controlled rate
  useEffect(() => {
    if (displayedPacketCount === -1) return; // historical message, no animation

    if (displayedPacketCount < packets.length) {
      const timer = setTimeout(() => {
        setDisplayedPacketCount(
          Math.min(displayedPacketCount + 1, packets.length)
        );
      }, PACKET_DELAY_MS);

      return () => clearTimeout(timer);
    }
  }, [displayedPacketCount, packets.length]);

  // Reset displayed count when packet array changes significantly (e.g., new message)
  useEffect(() => {
    if (animate && packets.length < storedPacketCount) {
      const resetCount = isFinalAnswerComplete(packets)
        ? Math.min(10, packets.length)
        : packets.length > 0
          ? 1
          : 0;
      setDisplayedPacketCount(resetCount);
    }
  }, [animate, packets.length, storedPacketCount]);

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

  // After `stop`, the reveal animation may still be catching up. The shown
  // text is then still partial, so it counts as streaming for Mermaid.
  const isRevealing =
    displayedPacketCount >= 0 && displayedPacketCount < packets.length;
  const { renderedContent } = useMarkdownRenderer(
    // the [*]() is a hack to show a blinking dot when the packet is not complete
    stopPacketSeen ? content : content + " [*]() ",
    state,
    "font-main-content-body",
    foregroundTextStyle,
    { isStreaming: !stopPacketSeen || isRevealing }
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
              <Text
                as="p"
                secondaryBody
                text04
                style={foregroundMutedTextStyle}
              >
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

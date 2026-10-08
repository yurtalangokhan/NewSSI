"use client";

import React from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { formatFullTimestamp, formatMessageTime } from "@/lib/dateUtils";

export interface MessageTimestampProps {
  /** ISO timestamp; absent for a message the backend could not stamp. */
  timeSent?: string;
  className?: string;
}

/**
 * The clock reading under a message, spelling out its full date on hover.
 *
 * Hidden until the message is hovered: the transcript is the content, and a
 * timestamp lit on every turn is a column of noise beside it. The `group` it
 * reveals with belongs to the surrounding message, so hovering anywhere on a
 * turn brings up that turn's time.
 */
export default function MessageTimestamp({
  timeSent,
  className,
}: MessageTimestampProps) {
  const { i18n } = useTranslation();

  const time = formatMessageTime(timeSent, i18n.language);
  if (!time) return null;

  return (
    <SimpleTooltip
      tooltip={formatFullTimestamp(timeSent, i18n.language) ?? undefined}
      side="top"
      delayDuration={300}
    >
      <Text
        as="span"
        secondaryBody
        text03
        className={cn(
          "opacity-0 transition-opacity group-hover:opacity-100 select-none tabular-nums",
          className
        )}
      >
        {time}
      </Text>
    </SimpleTooltip>
  );
}

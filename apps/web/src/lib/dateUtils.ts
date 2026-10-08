"use client";

import { useEffect } from "react";
import { useState } from "react";
import i18n from "@/i18n/config";

export const useNightTime = () => {
  const [isNight, setIsNight] = useState(false);

  useEffect(() => {
    const checkNightTime = () => {
      const currentHour = new Date().getHours();
      setIsNight(currentHour >= 18 || currentHour < 6);
    };

    checkNightTime();
    const interval = setInterval(checkNightTime, 60000); // Check every minute

    return () => clearInterval(interval);
  }, []);

  return { isNight };
};

export function getXDaysAgo(daysAgo: number) {
  const today = new Date();
  const daysAgoDate = new Date(today);
  daysAgoDate.setDate(today.getDate() - daysAgo);
  return daysAgoDate;
}

export function getXYearsAgo(yearsAgo: number) {
  const today = new Date();
  const yearsAgoDate = new Date(today);
  yearsAgoDate.setFullYear(yearsAgoDate.getFullYear() - yearsAgo);
  return yearsAgoDate;
}

export const timestampToDateString = (timestamp: string) => {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = date.getMonth() + 1; // getMonth() is zero-based
  const day = date.getDate();

  const formattedDate = `${year}-${month.toString().padStart(2, "0")}-${day
    .toString()
    .padStart(2, "0")}`;
  return formattedDate;
};

// Options for formatting the date
const dateOptions: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
};

// Options for formatting the time
const timeOptions: Intl.DateTimeFormatOptions = {
  hour: "numeric",
  minute: "2-digit",
  hour12: true, // Use 12-hour format with AM/PM
};

export const timestampToReadableDate = (timestamp: string) => {
  const date = new Date(timestamp);
  return (
    date.toLocaleDateString(undefined, dateOptions) +
    ", " +
    date.toLocaleTimeString(undefined, timeOptions)
  );
};

export const buildDateString = (date: Date | null) => {
  return date
    ? i18n.t("dates.daysAgoLong", {
        count: Math.round(
          (new Date().getTime() - date.getTime()) / (1000 * 60 * 60 * 24)
        ),
      })
    : i18n.t("dates.selectTimeRange");
};

export const getFormattedDateRangeString = (
  from: Date | null,
  to: Date | null
) => {
  if (!from || !to) return null;

  const options: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };
  const fromString = from.toLocaleDateString(i18n.language, options);
  const toString = to.toLocaleDateString(i18n.language, options);

  return `${fromString} - ${toString}`;
};

export const getDateRangeString = (from: Date | null, to: Date | null) => {
  if (!from || !to) return null;

  const now = new Date();
  const fromDiffMs = now.getTime() - from.getTime();
  const toDiffMs = now.getTime() - to.getTime();

  const fromDiffDays = Math.floor(fromDiffMs / (1000 * 60 * 60 * 24));
  const toDiffDays = Math.floor(toDiffMs / (1000 * 60 * 60 * 24));

  const fromString = getTimeAgoString(from);
  const toString = getTimeAgoString(to);

  if (fromString === toString) return fromString;

  if (toDiffDays === 0) {
    return `${fromString} - ${i18n.t("dates.today")}`;
  }

  return `${fromString} - ${toString}`;
};

export const getTimeAgoString = (date: Date | null) => {
  if (!date) return null;

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);

  if (now.toDateString() === date.toDateString()) return i18n.t("dates.today");
  if (diffDays === 1) return i18n.t("dates.yesterday");
  if (diffDays < 7) return i18n.t("dates.daysAgo", { count: diffDays });
  if (diffDays < 30) return i18n.t("dates.weeksAgo", { count: diffWeeks });
  return i18n.t("dates.monthsAgo", { count: diffMonths });
};

/**
 * Format a date to short format like "Jan 27, 2026".
 * Always shows date, never time.
 */
export const formatDateShort = (dateStr: string | null | undefined): string => {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString(i18n.language, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
};

export function formatMmDdYyyy(d: string): string {
  const date = new Date(d);
  return `${date.getMonth() + 1}/${date.getDate()}/${date.getFullYear()}`;
}

export const getFormattedDateTime = (date: Date | null) => {
  if (!date) return null;

  const now = new Date();
  const isToday = now.toDateString() === date.toDateString();

  if (isToday) {
    // If it's today, return the time in format like "3:45 PM"
    return date.toLocaleTimeString(i18n.language, {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } else {
    // Otherwise return the date in format like "Jan 15, 2023"
    return date.toLocaleDateString(i18n.language, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }
};

/**
 * Chat-transcript timestamps.
 *
 * These take `locale` and `t` as arguments rather than reading the i18next
 * singleton the helpers above use: that singleton (`import i18n from
 * "i18next"`) is never initialised in this app, so it neither translates nor
 * carries a language. Callers pass what `useTranslation()` gives them, which
 * is the instance the user's language actually lives on.
 *
 * Every one of them returns `null` rather than a placeholder for a missing or
 * unparseable timestamp, so a message the backend could not stamp renders no
 * timestamp at all instead of an "Invalid Date".
 */

function parseTimestamp(timestamp: string | null | undefined): Date | null {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Identifies the local calendar day a timestamp falls on, for deciding where
 * a day separator belongs. Built from local parts (not `toISOString`) so a
 * late-evening message doesn't land on the next day for users east of UTC.
 */
export function dayKey(timestamp: string | null | undefined): string | null {
  const date = parseTimestamp(timestamp);
  if (!date) return null;
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

/** The short clock reading shown under a message, e.g. "16:06" / "4:06 PM". */
export function formatMessageTime(
  timestamp: string | null | undefined,
  locale: string
): string | null {
  const date = parseTimestamp(timestamp);
  if (!date) return null;
  // No `hour12` override: whether a locale reads the clock in 12 or 24 hours
  // is exactly what the locale is there to decide.
  return date.toLocaleTimeString(locale, {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** The unabbreviated date and time, shown on hover over a message timestamp. */
export function formatFullTimestamp(
  timestamp: string | null | undefined,
  locale: string
): string | null {
  const date = parseTimestamp(timestamp);
  if (!date) return null;
  return date.toLocaleString(locale, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * The heading on a day separator: "Today"/"Yesterday" for the two days a
 * reader thinks of by name, an explicit date otherwise — with the year left
 * off within the current year, where it carries no information.
 */
export function formatDaySeparatorLabel(
  timestamp: string | null | undefined,
  locale: string,
  t: (key: string) => string,
  now: Date = new Date()
): string | null {
  const date = parseTimestamp(timestamp);
  if (!date) return null;

  const key = dayKey(date.toISOString());
  if (key === dayKey(now.toISOString())) return t("dates.today");

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (key === dayKey(yesterday.toISOString())) return t("dates.yesterday");

  return date.toLocaleDateString(locale, {
    day: "numeric",
    month: "long",
    ...(date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  });
}

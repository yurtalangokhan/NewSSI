import { User } from "@/lib/types";
import i18n from "@/i18n/config";

export const timeAgo = (
  dateString: string | undefined | null
): string | null => {
  if (!dateString) {
    return null;
  }

  const date = new Date(dateString);
  const now = new Date();
  const secondsDiff = Math.floor((now.getTime() - date.getTime()) / 1000);
  const t = i18n.t.bind(i18n);

  if (secondsDiff < 60) {
    return t("dates.justNow");
  }

  const minutesDiff = Math.floor(secondsDiff / 60);
  if (minutesDiff < 60) {
    return minutesDiff === 1
      ? t("dates.minAgo", { count: 1 })
      : t("dates.minsAgo", { count: minutesDiff });
  }

  const hoursDiff = Math.floor(minutesDiff / 60);
  if (hoursDiff < 24) {
    return hoursDiff === 1
      ? t("dates.hourAgo", { count: 1 })
      : t("dates.hoursAgo", { count: hoursDiff });
  }

  const daysDiff = Math.floor(hoursDiff / 24);
  if (daysDiff < 30) {
    return daysDiff === 1
      ? t("dates.dayAgo", { count: 1 })
      : t("dates.daysAgo", { count: daysDiff });
  }

  const weeksDiff = Math.floor(daysDiff / 7);
  if (weeksDiff < 4) {
    return t("dates.weeksAgo", { count: weeksDiff });
  }

  const monthsDiff = Math.floor(daysDiff / 30);
  if (monthsDiff < 12) {
    return t("dates.monthsAgo", { count: monthsDiff });
  }

  const yearsDiff = Math.floor(monthsDiff / 12);
  return t("dates.yearsAgo", { count: yearsDiff });
};

export function localizeAndPrettify(dateString: string) {
  const date = new Date(dateString);
  return date.toLocaleString();
}

export function humanReadableFormat(dateString: string): string {
  // Create a Date object from the dateString
  const date = new Date(dateString);

  // Use Intl.DateTimeFormat to format the date
  // Specify the locale as 'en-US' and options for month, day, and year
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "long", // full month name
    day: "numeric", // numeric day
    year: "numeric", // numeric year
  });

  // Format the date and return it
  return formatter.format(date);
}

/**
 * Format a date as "Jan 15, 2025" (short month name).
 */
export function humanReadableFormatShort(date: string | Date | null): string {
  if (!date) return "";
  const d = typeof date === "string" ? new Date(date) : date;
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return formatter.format(d);
}

export function humanReadableFormatWithTime(datetimeString: string): string {
  // Create a Date object from the dateString
  const date = new Date(datetimeString);

  // Use Intl.DateTimeFormat to format the date
  // Specify the locale as 'en-US' and options for month, day, and year
  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "long", // full month name
    day: "numeric", // numeric day
    year: "numeric", // numeric year
    hour: "numeric",
    minute: "numeric",
  });
  // Format the date and return it
  return formatter.format(date);
}

export function getSecondsUntilExpiration(
  userInfo: User | null
): number | null {
  if (!userInfo) {
    return null;
  }

  const { oidc_expiry, current_token_created_at, current_token_expiry_length } =
    userInfo;

  const now = new Date();

  let secondsUntilTokenExpiration: number | null = null;
  let secondsUntilOIDCExpiration: number | null = null;

  if (current_token_created_at && current_token_expiry_length !== undefined) {
    const createdAt = new Date(current_token_created_at);
    const expiresAt = new Date(
      createdAt.getTime() + current_token_expiry_length * 1000
    );
    secondsUntilTokenExpiration = Math.floor(
      (expiresAt.getTime() - now.getTime()) / 1000
    );
  }

  if (oidc_expiry) {
    const expiresAtFromOIDC = new Date(oidc_expiry);
    secondsUntilOIDCExpiration = Math.floor(
      (expiresAtFromOIDC.getTime() - now.getTime()) / 1000
    );
  }

  if (
    secondsUntilTokenExpiration === null &&
    secondsUntilOIDCExpiration === null
  ) {
    return null;
  }

  return Math.max(
    0,
    Math.min(
      secondsUntilTokenExpiration ?? Infinity,
      secondsUntilOIDCExpiration ?? Infinity
    )
  );
}

export type TimeFilter = "day" | "week" | "month" | "year";

export function getTimeFilterDate(filter: TimeFilter): Date | null {
  const now = new Date();
  switch (filter) {
    case "day":
      return new Date(now.getTime() - 24 * 60 * 60 * 1000);
    case "week":
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    case "month":
      return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    case "year":
      return new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
    default:
      return null;
  }
}

export function formatDurationSeconds(seconds: number): string {
  const totalSeconds = Math.ceil(seconds);
  if (totalSeconds < 60) {
    return i18n.t("duration.seconds", {
      value: totalSeconds,
      defaultValue: "{{value}}s",
    });
  }
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return secs > 0
    ? i18n.t("duration.minutesSeconds", {
        minutes: mins,
        seconds: secs,
        defaultValue: "{{minutes}}m {{seconds}}s",
      })
    : i18n.t("duration.minutes", {
        minutes: mins,
        defaultValue: "{{minutes}}m",
      });
}

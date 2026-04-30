import React from "react";

/**
 * Escapes special regex characters in a string
 */
function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Highlights matched portions of text based on search query.
 * Matched portions get text-05 (highlighted), non-matched stay as default.
 */
export function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;

  const escapedQuery = escapeRegex(query.trim());
  const regex = new RegExp(`(${escapedQuery})`, "gi");
  const parts = text.split(regex);

  if (parts.length === 1) return text; // No matches

  return parts.map((part, i) =>
    i % 2 === 1
      ? React.createElement("span", { key: i, className: "text-text-05" }, part)
      : React.createElement(React.Fragment, { key: i }, part)
  );
}

import i18n from "i18next";

/**
 * Formats a date string for display in the chat search menu.
 * Examples: "just now", "5 mins ago", "3 hours ago", "yesterday", "3 days ago", "October 23"
 */
export function formatDisplayTime(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 0) {
    return i18n.t("dates.justNow");
  }

  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  // Just now (less than 1 minute)
  if (diffMins < 1) {
    return i18n.t("dates.justNow");
  }

  // X mins ago (1-59 minutes)
  if (diffMins < 60) {
    return i18n.t(diffMins === 1 ? "dates.minAgo" : "dates.minsAgo", {
      count: diffMins,
    });
  }

  // X hours ago (1-23 hours)
  if (diffHours < 24) {
    return i18n.t(diffHours === 1 ? "dates.hourAgo" : "dates.hoursAgo", {
      count: diffHours,
    });
  }

  // Check if yesterday
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (
    date.getDate() === yesterday.getDate() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getFullYear() === yesterday.getFullYear()
  ) {
    return i18n.t("dates.yesterday").toLowerCase();
  }

  // X days ago (2-7 days)
  if (diffDays <= 7) {
    return i18n.t(diffDays === 1 ? "dates.dayAgo" : "dates.daysAgo", {
      count: diffDays,
    });
  }

  // Month Day format (e.g., "October 23")
  return date.toLocaleDateString(i18n.language, {
    month: "long",
    day: "numeric",
  });
}

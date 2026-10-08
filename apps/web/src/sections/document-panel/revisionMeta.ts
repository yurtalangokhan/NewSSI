import type { AuthorType } from "@/lib/api/domains/documents/types";

const TIME: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };

/**
 * Time of day for a draft made today; other days include the date (and the
 * year when it differs), so an older draft is not mistaken for a recent one.
 */
export function formatRevisionTime(
  iso: string,
  locale: string,
  now: Date = new Date()
): string {
  const date = new Date(iso);
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(locale, TIME);
  }
  return date.toLocaleString(locale, {
    day: "numeric",
    month: "short",
    ...(date.getFullYear() !== now.getFullYear() && { year: "numeric" }),
    ...TIME,
  });
}

export function authorKey(authorType: AuthorType) {
  return authorType === "user"
    ? "documentPanel.author.user"
    : "documentPanel.author.agent";
}

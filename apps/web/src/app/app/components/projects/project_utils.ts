import { timeAgo } from "@/lib/time";

export function formatRelativeTime(isoDate: string): string {
  return timeAgo(isoDate) ?? "";
}

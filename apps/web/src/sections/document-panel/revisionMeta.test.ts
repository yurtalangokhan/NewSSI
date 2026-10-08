import { formatRevisionTime } from "@/sections/document-panel/revisionMeta";

const at = (iso: string) => new Date(iso);

describe("formatRevisionTime", () => {
  it("shows only the time for a draft made today", () => {
    const now = at("2026-09-28T18:00:00");
    expect(formatRevisionTime("2026-09-28T14:18:00", "en", now)).toMatch(
      /^\d{2}:\d{2}( [AP]M)?$/
    );
  });

  it("adds the date for a draft from another day", () => {
    const now = at("2026-09-29T09:00:00");
    const label = formatRevisionTime("2026-09-28T14:18:00", "en", now);
    expect(label).toMatch(/28/);
    expect(label).toMatch(/Sep/);
    expect(label).toMatch(/\d{2}:\d{2}/);
    expect(label).not.toMatch(/2026/);
  });

  it("adds the year for a draft from another year", () => {
    const now = at("2027-01-05T09:00:00");
    expect(formatRevisionTime("2026-12-30T14:18:00", "en", now)).toMatch(
      /2026/
    );
  });
});

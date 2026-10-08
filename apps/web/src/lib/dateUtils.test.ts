import {
  dayKey,
  formatMessageTime,
  formatFullTimestamp,
  formatDaySeparatorLabel,
} from "./dateUtils";

// Built from local-time parts so the expectations hold in any TZ the suite
// happens to run in — an ISO literal would shift days for anyone east of UTC.
const localIso = (
  year: number,
  month: number,
  day: number,
  hour = 12,
  minute = 0
) => new Date(year, month - 1, day, hour, minute).toISOString();

// A fixed "now" lets the relative labels ("today"/"yesterday") be asserted
// without the suite's own clock leaking into the result.
const NOW = new Date(2026, 7, 12, 16, 6);

// Stands in for i18next's `t`, which the component supplies. Returning the
// key makes it obvious in a failure which branch the label came from.
const t = (key: string) => key;

describe("dayKey", () => {
  it("gives the same key to two times on the same local day", () => {
    expect(dayKey(localIso(2026, 8, 12, 0, 1))).toBe(
      dayKey(localIso(2026, 8, 12, 23, 59))
    );
  });

  it("gives different keys across a local midnight", () => {
    expect(dayKey(localIso(2026, 8, 12, 23, 59))).not.toBe(
      dayKey(localIso(2026, 8, 13, 0, 1))
    );
  });

  it("returns null for a missing or unparseable timestamp", () => {
    expect(dayKey(undefined)).toBeNull();
    expect(dayKey("not-a-date")).toBeNull();
  });
});

describe("formatMessageTime", () => {
  it("formats Turkish as a 24-hour clock", () => {
    expect(formatMessageTime(localIso(2026, 8, 12, 16, 6), "tr")).toBe("16:06");
  });

  it("formats English as a 12-hour clock", () => {
    expect(formatMessageTime(localIso(2026, 8, 12, 16, 6), "en")).toBe(
      "4:06 PM"
    );
  });

  it("returns null for a missing or unparseable timestamp", () => {
    expect(formatMessageTime(undefined, "tr")).toBeNull();
    expect(formatMessageTime("not-a-date", "tr")).toBeNull();
  });
});

describe("formatFullTimestamp", () => {
  it("spells out weekday, date and time in the active locale", () => {
    expect(formatFullTimestamp(localIso(2026, 8, 12, 16, 6), "tr")).toBe(
      "12 Ağustos 2026 Çarşamba 16:06"
    );
    expect(formatFullTimestamp(localIso(2026, 8, 12, 16, 6), "en")).toBe(
      "Wednesday, August 12, 2026 at 4:06 PM"
    );
  });

  it("returns null for a missing or unparseable timestamp", () => {
    expect(formatFullTimestamp(undefined, "tr")).toBeNull();
  });
});

describe("formatDaySeparatorLabel", () => {
  it("labels the current day with the translated 'today' string", () => {
    expect(
      formatDaySeparatorLabel(localIso(2026, 8, 12, 9, 0), "tr", t, NOW)
    ).toBe("dates.today");
  });

  it("labels the previous day with the translated 'yesterday' string", () => {
    expect(
      formatDaySeparatorLabel(localIso(2026, 8, 11, 9, 0), "tr", t, NOW)
    ).toBe("dates.yesterday");
  });

  it("omits the year for an earlier day in the same year", () => {
    expect(
      formatDaySeparatorLabel(localIso(2026, 3, 4, 9, 0), "tr", t, NOW)
    ).toBe("4 Mart");
  });

  it("includes the year for a day in an earlier year", () => {
    expect(
      formatDaySeparatorLabel(localIso(2025, 3, 4, 9, 0), "tr", t, NOW)
    ).toBe("4 Mart 2025");
  });

  it("returns null for a missing or unparseable timestamp", () => {
    expect(formatDaySeparatorLabel(undefined, "tr", t, NOW)).toBeNull();
  });
});

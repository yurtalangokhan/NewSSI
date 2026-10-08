import { renderHook } from "@testing-library/react";
import { useScoreFormatter } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/useScoreFormatter";

let mockI18n: { language?: string } | undefined;

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: mockI18n }),
}));

describe("useScoreFormatter", () => {
  it("formats in the active locale", () => {
    mockI18n = { language: "tr" };
    expect(renderHook(() => useScoreFormatter()).result.current(0.891)).toBe(
      "0,89"
    );

    mockI18n = { language: "en" };
    expect(renderHook(() => useScoreFormatter()).result.current(0.891)).toBe(
      "0.89"
    );
  });

  it("keeps the precision of small scores when asked for more digits", () => {
    mockI18n = { language: "tr" };
    expect(renderHook(() => useScoreFormatter(4)).result.current(0.00984)).toBe(
      "0,0098"
    );
  });

  it("falls back to the app's default language, not Turkish", () => {
    mockI18n = undefined;
    expect(renderHook(() => useScoreFormatter()).result.current(0.5)).toBe(
      "0.50"
    );
  });
});

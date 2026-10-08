import { render as rtlRender, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import MessageTimestamp from "../MessageTimestamp";

// Built from local-time parts so the expectations hold in any TZ.
const localIso = (
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number
) => new Date(year, month - 1, day, hour, minute).toISOString();

const render = (ui: React.ReactElement, language: "tr" | "en" = "tr") =>
  rtlRender(
    <I18nextProvider i18n={createI18nInstance(language)}>{ui}</I18nextProvider>
  );

describe("MessageTimestamp", () => {
  it("shows the clock reading in the active language", () => {
    render(<MessageTimestamp timeSent={localIso(2026, 8, 12, 16, 6)} />);
    expect(screen.getByText("16:06")).toBeInTheDocument();
  });

  it("follows the language's own clock convention", () => {
    render(<MessageTimestamp timeSent={localIso(2026, 8, 12, 16, 6)} />, "en");
    expect(screen.getByText("4:06 PM")).toBeInTheDocument();
  });

  it("spells out the full date on hover", async () => {
    render(<MessageTimestamp timeSent={localIso(2026, 8, 12, 16, 6)} />);

    await userEvent.hover(screen.getByText("16:06"));

    await waitFor(() =>
      expect(
        screen.getAllByText("12 Ağustos 2026 Çarşamba 16:06").length
      ).toBeGreaterThan(0)
    );
  });

  it("renders nothing for a message the backend could not stamp", () => {
    const { container } = render(<MessageTimestamp timeSent={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("stays hidden until its message is hovered", () => {
    // The transcript is the content; a clock on every turn, always lit, is
    // noise. The surrounding message bubble owns the `group`.
    render(<MessageTimestamp timeSent={localIso(2026, 8, 12, 16, 6)} />);
    const className = screen.getByText("16:06").className;
    expect(className).toContain("opacity-0");
    expect(className).toContain("group-hover:opacity-100");
  });
});

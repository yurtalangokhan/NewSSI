import { render, screen } from "@tests/setup/test-utils";

import RelevanceMeter from "@/sections/knowledge-search/components/RelevanceMeter";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

describe("RelevanceMeter", () => {
  it("formats the score in the reader's locale", () => {
    render(<RelevanceMeter value={0.87} />);

    const meter = screen.getByRole("meter");
    expect(meter).toHaveAccessibleName("Göreli alaka 0,87");
    expect(screen.getByText("0,87")).toBeInTheDocument();
  });

  it("exposes the value and range to assistive technology", () => {
    render(<RelevanceMeter value={0.5} />);

    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "1");
    expect(meter).toHaveAttribute("aria-valuenow", "0.5");
  });

  it("clamps out-of-range values", () => {
    const { rerender } = render(<RelevanceMeter value={1.4} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "1");

    rerender(<RelevanceMeter value={-0.2} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
  });
});

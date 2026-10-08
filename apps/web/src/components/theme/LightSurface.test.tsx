import { render, screen } from "@testing-library/react";
import {
  LightSurface,
  useLightSurfaceElement,
} from "@/components/theme/LightSurface";

function Probe() {
  const element = useLightSurfaceElement();
  return <span data-testid="probe">{element ? "scoped" : "unscoped"}</span>;
}

it("applies the light token scope only when enabled", () => {
  const { rerender } = render(
    <LightSurface enabled={false} data-testid="surface">
      <Probe />
    </LightSurface>
  );

  expect(screen.getByTestId("surface")).not.toHaveClass("theme-light");
  expect(screen.getByTestId("probe")).toHaveTextContent("unscoped");

  rerender(
    <LightSurface enabled data-testid="surface">
      <Probe />
    </LightSurface>
  );

  expect(screen.getByTestId("surface")).toHaveClass("theme-light");
  // The node is registered after mount so JavaScript-driven colours (the
  // Mermaid theme) can follow the same scope instead of <html>.
  expect(screen.getByTestId("probe")).toHaveTextContent("scoped");
});

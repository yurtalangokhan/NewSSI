import { render, screen } from "@testing-library/react";
import CustomAgentAvatar from "@/refresh-components/avatars/CustomAgentAvatar";

describe("CustomAgentAvatar", () => {
  it("frames a letter-only agent with the round medallion", () => {
    const { container } = render(<CustomAgentAvatar name="Ada" size={36} />);
    expect(screen.getByTestId("agent-avatar-frame")).toHaveAttribute(
      "data-variant",
      "agent"
    );
    expect(container.querySelector("svg polygon")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("frames a letter-only flow with the directed medallion", () => {
    const { container } = render(
      <CustomAgentAvatar name="Fatura" variant="flow" size={36} />
    );
    expect(screen.getByTestId("agent-avatar-frame")).toHaveAttribute(
      "data-variant",
      "flow"
    );
    expect(
      container.querySelector('[data-part="flowpath"]')
    ).toBeInTheDocument();
  });

  it("keeps the plain clipped frame for an uploaded image (no medallion)", () => {
    const { container } = render(
      <CustomAgentAvatar name="Ada" src="/x.png" variant="flow" />
    );
    expect(screen.getByTestId("agent-avatar-frame")).toHaveAttribute(
      "data-variant",
      "flow"
    );
    expect(container.querySelector("polygon")).not.toBeInTheDocument();
  });
});

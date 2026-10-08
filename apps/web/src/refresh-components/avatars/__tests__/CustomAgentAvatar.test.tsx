import { fireEvent, render, screen } from "@testing-library/react";
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

  it("covers a pending uploaded image with a skeleton until it loads", () => {
    render(<CustomAgentAvatar name="Ada" src="/x.png" />);

    expect(
      screen.getByTestId("agent-avatar-image-skeleton")
    ).toBeInTheDocument();

    fireEvent.load(screen.getByRole("img"));
    expect(
      screen.queryByTestId("agent-avatar-image-skeleton")
    ).not.toBeInTheDocument();
  });

  it("re-arms the skeleton when the image source changes", () => {
    const { rerender } = render(<CustomAgentAvatar name="Ada" src="/x.png" />);
    fireEvent.load(screen.getByRole("img"));
    expect(
      screen.queryByTestId("agent-avatar-image-skeleton")
    ).not.toBeInTheDocument();

    rerender(<CustomAgentAvatar name="Ada" src="/y.png" />);
    expect(
      screen.getByTestId("agent-avatar-image-skeleton")
    ).toBeInTheDocument();

    // The listener follows the new src: a stale one would leave the skeleton
    // pulsing after the replacement image has painted.
    fireEvent.load(screen.getByRole("img"));
    expect(
      screen.queryByTestId("agent-avatar-image-skeleton")
    ).not.toBeInTheDocument();
  });

  it("never skeletons a letter, icon or default avatar", () => {
    const { rerender } = render(<CustomAgentAvatar name="Ada" />);
    expect(
      screen.queryByTestId("agent-avatar-image-skeleton")
    ).not.toBeInTheDocument();

    rerender(<CustomAgentAvatar name="Ada" iconName="Search" />);
    expect(
      screen.queryByTestId("agent-avatar-image-skeleton")
    ).not.toBeInTheDocument();
  });
});

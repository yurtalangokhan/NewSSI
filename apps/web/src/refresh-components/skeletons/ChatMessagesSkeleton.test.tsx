import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import ChatMessagesSkeleton, {
  AssistantReplySkeleton,
} from "./ChatMessagesSkeleton";

const pulsingLines = (root: HTMLElement) =>
  root.querySelectorAll(".animate-pulse");

describe("ChatMessagesSkeleton", () => {
  it("still renders whole exchanges, each with a user bubble and a reply", () => {
    renderWithI18n(<ChatMessagesSkeleton pairCount={2} />);
    const root = screen.getByRole("status", { name: /loading messages/i });
    // Per exchange: one user bubble plus a reply of pulsing lines or a card.
    expect(pulsingLines(root).length).toBeGreaterThanOrEqual(2 * 3);
  });
});

describe("AssistantReplySkeleton", () => {
  it("is just the reply lines, drawn like the chat screen's own skeleton", () => {
    renderWithI18n(<AssistantReplySkeleton />);
    const root = screen.getByTestId("resume-skeleton");
    expect(root).toHaveAttribute("role", "status");
    const lines = pulsingLines(root);
    expect(lines.length).toBeGreaterThanOrEqual(2);
    expect(lines.length).toBeLessThanOrEqual(4);
    // Same line shape as ChatMessagesSkeleton's replies: no user bubble here.
    lines.forEach((line) => expect(line.className).toContain("h-3"));
  });

  it("keeps its shape across re-renders", () => {
    const { rerender } = renderWithI18n(<AssistantReplySkeleton />);
    const before = screen.getByTestId("resume-skeleton").innerHTML;
    rerender(<AssistantReplySkeleton />);
    expect(screen.getByTestId("resume-skeleton").innerHTML).toBe(before);
  });
});

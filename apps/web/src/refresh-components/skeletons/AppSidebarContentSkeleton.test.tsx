import React from "react";
import { render, screen } from "@testing-library/react";
import AppSidebarContentSkeleton, {
  AppSidebarActionButtonsSkeleton,
} from "./AppSidebarContentSkeleton";

describe("AppSidebarContentSkeleton", () => {
  it("renders normal expanded skeleton with role='status'", () => {
    const { container } = render(<AppSidebarContentSkeleton />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-label", "Loading sidebar content...");

    const items = container.querySelectorAll(".px-3.py-2");
    // 3 agents + 2 projects + 6 recents = 11 items
    expect(items.length).toBe(11);
  });

  it("ensures recents chat items do NOT have leading icon elements", () => {
    const { container } = render(<AppSidebarContentSkeleton />);
    // In Recents (the last section), items only have a text bar without an icon
    const sections = container.querySelectorAll(".flex.flex-col.gap-1.w-full");
    // 3 sections: Agents, Projects, Recents
    expect(sections.length).toBe(3);

    const recentsSection = sections[2];
    expect(recentsSection).toBeDefined();

    const recentRows = recentsSection!.querySelectorAll(".px-3.py-2");
    expect(recentRows.length).toBe(6);

    recentRows.forEach((row) => {
      // Row must only have 1 child element (the text placeholder), no icon
      expect(row.children.length).toBe(1);
      expect(row.querySelector(".shrink-0")).toBeNull();
    });
  });

  it("renders action buttons when includeActionButtons is true", () => {
    const { container } = render(
      <AppSidebarContentSkeleton includeActionButtons />
    );
    const actionButtons = screen.getByRole("status", {
      name: "Loading action buttons...",
    });
    expect(actionButtons).toBeInTheDocument();

    const items = container.querySelectorAll(".px-3.py-2");
    // 2 action buttons + 11 content items = 13 items
    expect(items.length).toBe(13);
  });

  it("renders folded skeleton with 8 pulse squares when folded is true", () => {
    const { container } = render(<AppSidebarContentSkeleton folded />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();

    const squares = container.querySelectorAll(".h-8.w-8");
    expect(squares.length).toBe(8);
  });
});

describe("AppSidebarActionButtonsSkeleton", () => {
  it("renders 2 action button placeholders with leading icons for new session and search", () => {
    const { container } = render(<AppSidebarActionButtonsSkeleton />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-label", "Loading action buttons...");

    const rows = container.querySelectorAll(".px-3.py-2");
    expect(rows.length).toBe(2);

    rows.forEach((row) => {
      // Each action button has an icon and a text placeholder
      expect(row.children.length).toBe(2);
      expect(row.querySelector(".h-4.w-4")).toBeInTheDocument();
      expect(row.querySelector(".h-3\\.5")).toBeInTheDocument();
    });
  });
});

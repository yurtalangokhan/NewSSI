import { getOrganizationMinZoom } from "@/components/organization/organizationViewport";

describe("organization zoom bounds", () => {
  it.each(["x", "y"] as const)("fits a large layout along %s", (axis) => {
    const nodes = Array.from({ length: 10000 }, (_, index) => ({
      position: { x: 0, y: 0, [axis]: index * 400 },
    }));
    const minZoom = getOrganizationMinZoom(nodes);
    expect(minZoom).toBeGreaterThan(0);
    expect(minZoom * 4000000).toBeLessThanOrEqual(200);
  });

  it("preserves normal zoom for compact and empty diagrams", () => {
    expect(getOrganizationMinZoom([])).toBe(0.2);
    expect(
      getOrganizationMinZoom([{ position: { x: 1000000, y: -1000000 } }])
    ).toBe(0.2);
  });
});

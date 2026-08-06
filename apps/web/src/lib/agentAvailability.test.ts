import {
  getAgentAvailabilityIssues,
  isAgentAvailableForSelection,
} from "@/lib/agentAvailability";

describe("getAgentAvailabilityIssues", () => {
  test("returns only non-ok availability checks", () => {
    expect(
      getAgentAvailabilityIssues({
        status: "unavailable",
        checks: [
          {
            component: "model",
            status: "ok",
            message: "Model is available.",
          },
          {
            component: "mcp_tool",
            status: "error",
            message: "MCP tool 'slack_search' is selected but is not available.",
          },
        ],
      })
    ).toEqual([
      {
        component: "mcp_tool",
        status: "error",
        message: "MCP tool 'slack_search' is selected but is not available.",
      },
    ]);
  });

  test("treats summary availability without checks as having no issues", () => {
    expect(
      getAgentAvailabilityIssues({
        status: "available",
      })
    ).toEqual([]);
  });
});

describe("isAgentAvailableForSelection", () => {
  test("disables unavailable agents but allows available and unknown agents", () => {
    expect(
      isAgentAvailableForSelection({
        availability: { status: "unavailable", checks: [] },
      })
    ).toBe(false);
    expect(
      isAgentAvailableForSelection({
        availability: { status: "available", checks: [] },
      })
    ).toBe(true);
    expect(isAgentAvailableForSelection({ availability: undefined })).toBe(
      true
    );
  });
});

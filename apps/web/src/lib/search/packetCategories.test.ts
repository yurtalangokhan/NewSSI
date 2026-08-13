import {
  getCategoryFor,
  getGroupSuffix,
  shouldSplitCategories,
  TOOL_PACKET_TYPES,
} from "./packetCategories";

describe("generated_file category", () => {
  test("is registered with its own genfile group suffix", () => {
    expect(getGroupSuffix("generated_file")).toBe("genfile");
  });

  test("is discoverable via getCategoryFor", () => {
    expect(getCategoryFor("generated_file")?.id).toBe("generated-file");
  });

  test("splits from the custom tool category in both directions", () => {
    expect(shouldSplitCategories("custom_tool_delta", "generated_file")).toBe(true);
    expect(shouldSplitCategories("generated_file", "custom_tool_delta")).toBe(true);
  });

  test("is included in TOOL_PACKET_TYPES for live-stream turn tracking", () => {
    expect(TOOL_PACKET_TYPES.has("generated_file")).toBe(true);
  });
});

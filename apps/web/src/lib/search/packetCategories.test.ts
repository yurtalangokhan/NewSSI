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
    expect(shouldSplitCategories("custom_tool_delta", "generated_file")).toBe(
      true
    );
    expect(shouldSplitCategories("generated_file", "custom_tool_delta")).toBe(
      true
    );
  });

  test("is included in TOOL_PACKET_TYPES for live-stream turn tracking", () => {
    expect(TOOL_PACKET_TYPES.has("generated_file")).toBe(true);
  });
});

describe("document generation packets", () => {
  const lifecycle = [
    "document_generation_start",
    "document_generation_progress",
    "document_generation_end",
  ];

  test("share the generated_file group so the skeleton is replaced by the file card", () => {
    for (const type of lifecycle) {
      expect(getGroupSuffix(type)).toBe("genfile");
      expect(getCategoryFor(type)?.id).toBe("generated-file");
      expect(shouldSplitCategories(type, "generated_file")).toBe(false);
    }
  });

  test("split from tool and reasoning packets so they get their own group", () => {
    expect(
      shouldSplitCategories("reasoning_delta", "document_generation_start")
    ).toBe(true);
    expect(
      shouldSplitCategories("document_generation_progress", "custom_tool_start")
    ).toBe(true);
  });

  test("are included in TOOL_PACKET_TYPES for live-stream turn tracking", () => {
    for (const type of lifecycle) {
      expect(TOOL_PACKET_TYPES.has(type)).toBe(true);
    }
  });
});

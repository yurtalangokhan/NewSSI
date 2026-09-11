import { isValidConnection } from "../utils/isValidConnection";
import { resolveComponentIcon } from "../utils/resolveComponentIcon";
import {
  SvgSearch,
  SvgGlobe,
  SvgFileText,
  SvgHardDrive,
  SvgRefreshCw,
} from "@opal/icons";
import type { PortType } from "../types/flow";

function mockLookup(
  _nodeId: string,
  handleName: string,
  _direction: "source" | "target"
): PortType[] | null {
  if (handleName === "branch1" || handleName === "trigger") return ["Trigger"];
  if (handleName === "text" || handleName === "query") return ["Text"];
  if (handleName === "result" || handleName === "data") return ["Data"];
  return null;
}

describe("Task 48 — Web & Datasource Node UI and Connections", () => {
  it("48.1 — resolveComponentIcon resolves Web and Datasource icons correctly", () => {
    expect(resolveComponentIcon("SvgSearch")).toBe(SvgSearch);
    expect(resolveComponentIcon("SvgGlobe")).toBe(SvgGlobe);
    expect(resolveComponentIcon("SvgFileText")).toBe(SvgFileText);
    expect(resolveComponentIcon("SvgHardDrive")).toBe(SvgHardDrive);
    expect(resolveComponentIcon("SvgRefreshCw")).toBe(SvgRefreshCw);
  });

  it("48.2 — isValidConnection accepts TRIGGER to TRIGGER connection for SyncTrigger", () => {
    const valid = isValidConnection(
      {
        source: "router_1",
        sourceHandle: "branch1",
        target: "st_1",
        targetHandle: "trigger",
      },
      [],
      mockLookup
    );

    expect(valid).toBe(true);
  });

  it("48.3 — isValidConnection rejects non-TRIGGER source to SyncTrigger trigger input", () => {
    const valid = isValidConnection(
      {
        source: "text_1",
        sourceHandle: "text",
        target: "st_1",
        targetHandle: "trigger",
      },
      [],
      mockLookup
    );

    expect(valid).toBe(false);
  });
});

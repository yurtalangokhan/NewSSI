import * as OpalIcons from "@opal/icons";

// Allowed icons verified against backend templates
const BACKEND_ICON_ALLOWLIST = [
  "SvgArrowExchange",
  "SvgArrowWallRight",
  "SvgBarChart",
  "SvgBookOpen",
  "SvgBracketCurly",
  "SvgBranch",
  "SvgBubbleText",
  "SvgCheckSquare",
  "SvgClock",
  "SvgCloud",
  "SvgCode",
  "SvgCpu",
  "SvgFileBraces",
  "SvgFiles",
  "SvgFileText",
  "SvgGlobe",
  "SvgHardDrive",
  "SvgHash",
  "SvgLinkedDots",
  "SvgMcp",
  "SvgNetworkGraph",
  "SvgPlug",
  "SvgQuoteStart",
  "SvgRefreshCw",
  "SvgSearch",
  "SvgServer",
  "SvgSettings",
  "SvgShield",
  "SvgSliders",
  "SvgSparkle",
  "SvgTerminal",
  "SvgTextLines",
  "SvgWorkflow",
];

describe("Flow Canvas Icon Allowlist (Task 34)", () => {
  it("every icon in backend allowlist is a defined export from @opal/icons", () => {
    for (const iconName of BACKEND_ICON_ALLOWLIST) {
      expect((OpalIcons as Record<string, unknown>)[iconName]).toBeDefined();
    }
  });
});

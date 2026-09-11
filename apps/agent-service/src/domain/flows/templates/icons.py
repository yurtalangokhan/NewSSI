"""Icon names templates may declare.

Every entry is exported by @opal/icons
(pps/web/lib/opal/src/icons/index.ts). Templates reference icons by these
names and the canvas resolves them at render time, so a typo here produces a
blank node rather than a build error.

Keeping the allowlist here — rather than reading the frontend directory from a
Python test — keeps agent-service self-contained, which matters because its
Docker image does not include pps/web.

**When adding an icon:** confirm the export exists in
pps/web/lib/opal/src/icons/index.ts first. P4 adds a frontend test
asserting this allowlist is a subset of the real exports.
"""

from __future__ import annotations

from typing import Final

ICON_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "SvgArrowExchange",
        "SvgArrowWallRight",
        "SvgBarChart",
        "SvgBookOpen",
        "SvgBooksStackSmall",
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
        "SvgUsers",
        "SvgUserManage",
        "SvgWorkflow",
    }
)

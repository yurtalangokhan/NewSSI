import { renderHook } from "@testing-library/react";

import { PacketType } from "@/app/app/services/streamingModels";

import { useTimelineHeader } from "./useTimelineHeader";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("useTimelineHeader", () => {
  test("prioritizes long-term memory over reasoning within the same step", () => {
    const { result } = renderHook(() =>
      useTimelineHeader([
        {
          turnIndex: 0,
          isParallel: false,
          steps: [
            {
              key: "0-0",
              turnIndex: 0,
              tabIndex: 0,
              packets: [
                {
                  placement: { turn_index: 0, tab_index: 0 },
                  obj: { type: PacketType.REASONING_START },
                },
                {
                  placement: { turn_index: 0, tab_index: 0 },
                  obj: {
                    type: PacketType.LONG_TERM_MEMORY_RECALL,
                    memories: ["User likes tea"],
                    fact_count: 1,
                  },
                },
              ],
            },
          ],
        },
      ])
    );

    expect(result.current.headerText).toBe("timeline.ltmRecalling");
  });
});
import { ChatSessionSharedStatus } from "@/app/app/interfaces";
import {
  transformApiResponse,
  transformLocalSessionsToFilterableChats,
} from "@/sections/sidebar/useChatSearchOptimistic";

describe("transformApiResponse", () => {
  it("returns no chats when groups is missing", () => {
    expect(transformApiResponse({})).toEqual([]);
  });

  it("uses chat activity time from search response summaries", () => {
    expect(
      transformApiResponse({
        groups: [
          {
            title: "Today",
            chats: [
              {
                id: "with-message",
                name: "With message",
                persona_id: 0,
                time_created: "2026-08-07T09:00:00Z",
                time_updated: "2026-08-07T12:00:00Z",
                last_message_at: "2026-08-07T11:00:00Z",
                last_accessed_at: null,
                shared_status: ChatSessionSharedStatus.Private,
                current_alternate_model: null,
                current_temperature_override: null,
              },
              {
                id: "viewed-unsent",
                name: "Viewed unsent",
                persona_id: 0,
                time_created: "2026-08-07T08:00:00Z",
                time_updated: "2026-08-07T13:00:00Z",
                last_message_at: null,
                last_accessed_at: "2026-08-07T13:00:00Z",
                shared_status: ChatSessionSharedStatus.Private,
                current_alternate_model: null,
                current_temperature_override: null,
              },
            ],
          },
        ],
        has_more: false,
        next_page: null,
      })
    ).toEqual([
      {
        id: "with-message",
        label: "With message",
        time: "2026-08-07T11:00:00Z",
      },
      {
        id: "viewed-unsent",
        label: "Viewed unsent",
        time: "2026-08-07T08:00:00Z",
      },
    ]);
  });
});

describe("transformLocalSessionsToFilterableChats", () => {
  it("keeps the freshest duplicate local session before projecting search rows", () => {
    expect(
      transformLocalSessionsToFilterableChats([
        {
          id: "same-chat",
          name: "Fresh recents name",
          persona_id: 0,
          time_created: "2026-08-07T09:00:00Z",
          time_updated: "2026-08-07T14:00:00Z",
          last_message_at: "2026-08-07T11:00:00Z",
          last_accessed_at: null,
          shared_status: ChatSessionSharedStatus.Private,
          project_id: null,
          current_alternate_model: "",
          current_temperature_override: null,
        },
        {
          id: "same-chat",
          name: "Stale project name",
          persona_id: 0,
          time_created: "2026-08-07T09:00:00Z",
          time_updated: "2026-08-07T10:00:00Z",
          last_message_at: "2026-08-07T13:00:00Z",
          last_accessed_at: null,
          shared_status: ChatSessionSharedStatus.Private,
          project_id: 7,
          current_alternate_model: "",
          current_temperature_override: null,
        },
      ])
    ).toEqual([
      {
        id: "same-chat",
        label: "Fresh recents name",
        time: "2026-08-07T11:00:00Z",
      },
    ]);
  });
});

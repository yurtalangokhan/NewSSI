import { envelopeResponse } from "@tests/setup/responseModel";
import {
  createPersona,
  deletePersona,
  updatePersona,
  uploadAgentIcon,
} from "@/lib/api/domains/agents/api";
import { PersonaUpsertParameters } from "@/lib/api/domains/agents/requests";
import {
  togglePersonaFeatured,
  togglePersonaVisibility,
} from "@/lib/api/domains/agents/api";
import { apiRequest } from "@/lib/api/http/browser";

jest.mock("@/lib/api/http/browser", () => ({
  apiRequest: jest.fn(),
  parseJsonResponse: jest.fn(async (response: Response) => response.json()),
}));

describe("agent admin central request ownership", () => {
  const personaParams: PersonaUpsertParameters = {
    name: "Research Agent",
    description: "Finds things",
    system_prompt: "Be useful",
    replace_base_system_prompt: false,
    task_prompt: "",
    datetime_aware: false,
    document_set_ids: [],
    is_public: false,
    llm_model_provider_override: null,
    llm_model_version_override: null,
    starter_messages: null,
    groups: [],
    tool_ids: [],
    search_start_date: null,
    uploaded_image_id: null,
    icon_name: null,
    featured: false,
    label_ids: null,
    user_file_ids: [],
  };

  beforeEach(() => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(envelopeResponse({ file_id: "file-1" }));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("delegates persona creation to apiRequest", async () => {
    await createPersona(personaParams);

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/persona",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      })
    );
  });

  it("includes connector bindings in the persona payload", async () => {
    await createPersona({
      ...personaParams,
      connector_bindings: [
        {
          datasource_id: "github-1",
          operations: ["list_resources", "read"],
        },
      ],
    });

    const request = jest.mocked(apiRequest).mock.calls[0]?.[1];
    expect(JSON.parse(String(request?.body))).toEqual(
      expect.objectContaining({
        connector_bindings: [
          {
            datasource_id: "github-1",
            operations: ["list_resources", "read"],
          },
        ],
      })
    );
  });

  it("delegates persona updates to apiRequest", async () => {
    await updatePersona(42, personaParams);

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/persona/42",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
      })
    );
  });

  it("delegates persona deletion to apiRequest", async () => {
    await deletePersona(42);

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/persona/42",
      expect.objectContaining({
        method: "DELETE",
        credentials: "include",
      })
    );
  });

  it("delegates persona featured changes to apiRequest", async () => {
    await togglePersonaFeatured(42, false);

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/persona/42/featured",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
      })
    );
  });

  it("delegates persona visibility changes to apiRequest", async () => {
    await togglePersonaVisibility(42, true);

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/persona/42/visible",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
      })
    );
  });

  it("forwards the live icon upload FormData unchanged", async () => {
    const file = new File(["avatar"], "avatar.png", { type: "image/png" });
    const body = new FormData();
    body.append("file", file);
    const response = await uploadAgentIcon(body);
    expect(await response.json()).toEqual({ file_id: "file-1" });

    expect(apiRequest).toHaveBeenCalledWith("/api/admin/persona/upload-image", {
      method: "POST",
      body,
    });
  });
});

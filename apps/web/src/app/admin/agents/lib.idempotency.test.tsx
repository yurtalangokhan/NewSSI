import {
  createPersona,
  deletePersona,
  PersonaUpsertParameters,
  togglePersonaFeatured,
  togglePersonaVisibility,
  updatePersona,
  uploadFile,
} from "@/app/admin/agents/lib";
import { authenticatedFetch } from "@/lib/fetcher";

jest.mock("@/lib/fetcher", () => ({
  authenticatedFetch: jest.fn(),
}));

describe("agent admin idempotency", () => {
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
    jest.mocked(authenticatedFetch).mockResolvedValue(
      new Response(JSON.stringify({ file_id: "file-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("uses authenticatedFetch for persona creation idempotency", async () => {
    await createPersona(personaParams);

    expect(authenticatedFetch).toHaveBeenCalledWith(
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

    const request = jest.mocked(authenticatedFetch).mock.calls[0]?.[1];
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

  it("uses authenticatedFetch for persona updates idempotency", async () => {
    await updatePersona(42, personaParams);

    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/persona/42",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
      })
    );
  });

  it("uses authenticatedFetch for persona deletion idempotency", async () => {
    await deletePersona(42);

    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/persona/42",
      expect.objectContaining({
        method: "DELETE",
        credentials: "include",
      })
    );
  });

  it("uses authenticatedFetch for persona featured toggle idempotency", async () => {
    await togglePersonaFeatured(42, false);

    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/admin/persona/42/featured",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
      })
    );
  });

  it("uses authenticatedFetch for persona visibility toggle idempotency", async () => {
    await togglePersonaVisibility(42, true);

    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/admin/persona/42/visible",
      expect.objectContaining({
        method: "PATCH",
        credentials: "include",
      })
    );
  });

  it("uses authenticatedFetch for persona image upload idempotency", async () => {
    const file = new File(["avatar"], "avatar.png", { type: "image/png" });

    await uploadFile(file);

    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/admin/persona/upload-image",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
        credentials: "include",
      })
    );
  });
});

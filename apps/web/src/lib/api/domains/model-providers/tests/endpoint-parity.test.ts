import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";

describe("model-provider endpoint parity", () => {
  it("preserves raw persona IDs and image-generation query order", () => {
    expect(modelProvidersEndpoints.getPersonaProviders(42).browserPath).toBe(
      "/api/llm/persona/42/providers"
    );
    expect(
      modelProvidersEndpoints.adminLlmProviderWithImageGen.browserPath
    ).toBe("/api/admin/llm/provider?include_image_gen=true");
  });
});

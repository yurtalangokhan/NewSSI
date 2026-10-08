import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";
import {
  MCP_SERVER_VALIDATION_KEYS,
  buildMCPServerValidationSchema,
} from "./mcpServerValidation";

const echoT = (key: string) => `t(${key})`;

function resolve(catalog: unknown, key: string): unknown {
  return key
    .split(".")
    .reduce<unknown>(
      (node, segment) =>
        node && typeof node === "object"
          ? (node as Record<string, unknown>)[segment]
          : undefined,
      catalog
    );
}

async function errorFor(
  field: string,
  value: unknown
): Promise<string | undefined> {
  const schema = buildMCPServerValidationSchema(echoT);
  try {
    await schema.validateAt(field, {
      name: "a name",
      description: "",
      server_url: "https://example.com/mcp",
      [field]: value,
    });
    return undefined;
  } catch (error) {
    return (error as { message: string }).message;
  }
}

describe("buildMCPServerValidationSchema", () => {
  it("reports a missing server name through the translator, not a hardcoded string", async () => {
    await expect(errorFor("name", "")).resolves.toBe(
      `t(${MCP_SERVER_VALIDATION_KEYS.nameRequired})`
    );
  });

  it("reports a missing server URL through the translator", async () => {
    await expect(errorFor("server_url", "")).resolves.toBe(
      `t(${MCP_SERVER_VALIDATION_KEYS.urlRequired})`
    );
  });

  it("reports a malformed server URL through the translator", async () => {
    await expect(errorFor("server_url", "not-a-url")).resolves.toBe(
      `t(${MCP_SERVER_VALIDATION_KEYS.urlInvalid})`
    );
  });

  it("accepts a valid server", async () => {
    await expect(errorFor("name", "My server")).resolves.toBeUndefined();
    await expect(
      errorFor("server_url", "https://example.com/mcp")
    ).resolves.toBeUndefined();
  });

  it.each(Object.entries(MCP_SERVER_VALIDATION_KEYS))(
    "has a translation for %s in every locale",
    (_field, key) => {
      expect(resolve(en, key)).toEqual(expect.any(String));
      expect(resolve(tr, key)).toEqual(expect.any(String));
    }
  );
});

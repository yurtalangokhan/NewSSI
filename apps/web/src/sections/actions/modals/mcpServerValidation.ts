import * as Yup from "yup";

export const MCP_SERVER_VALIDATION_KEYS = {
  nameRequired: "admin.mcp.serverNameRequired",
  urlRequired: "admin.mcp.serverUrlRequired",
  urlInvalid: "admin.mcp.serverUrlInvalid",
} as const;

/**
 * Built per render rather than once at module scope: Yup bakes the message
 * strings in at construction time, so a module-level schema would freeze
 * whichever locale was active when the module first loaded.
 */
export function buildMCPServerValidationSchema(t: (key: string) => string) {
  return Yup.object().shape({
    name: Yup.string().required(t(MCP_SERVER_VALIDATION_KEYS.nameRequired)),
    description: Yup.string(),
    server_url: Yup.string()
      .url(t(MCP_SERVER_VALIDATION_KEYS.urlInvalid))
      .required(t(MCP_SERVER_VALIDATION_KEYS.urlRequired)),
  });
}

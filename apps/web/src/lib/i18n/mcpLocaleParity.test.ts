import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

const mcp = (locale: unknown) =>
  Object.keys(
    (locale as { admin: { mcp: Record<string, string> } }).admin.mcp
  ).sort();

it("defines every admin.mcp message in both locales", () => {
  expect(mcp(tr)).toEqual(mcp(en));
});

it("translates the MCP page toasts instead of repeating the English text", () => {
  const enMcp = (en as any).admin.mcp;
  const trMcp = (tr as any).admin.mcp;

  expect(enMcp.toastServerDisconnected).toBe(
    "MCP server disconnected successfully"
  );
  expect(trMcp.toastServerDisconnected).not.toBe(enMcp.toastServerDisconnected);
  expect(trMcp.fetchToolsFailed).toContain("{{message}}");
});

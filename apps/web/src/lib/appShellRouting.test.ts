import { shouldRenderAppShell } from "@/providers/appShellRouting";

describe("shouldRenderAppShell", () => {
  it("does not render app-only providers on public auth and error surfaces", () => {
    expect(shouldRenderAppShell("/")).toBe(false);
    expect(shouldRenderAppShell("/auth/login")).toBe(false);
    expect(shouldRenderAppShell("/auth/ee/login")).toBe(false);
    expect(shouldRenderAppShell("/error/401")).toBe(false);
    expect(shouldRenderAppShell("/error/403")).toBe(false);
  });

  it("renders app-only providers on authenticated application surfaces", () => {
    expect(shouldRenderAppShell("/app")).toBe(true);
    expect(shouldRenderAppShell("/admin/configuration/llm")).toBe(true);
    expect(shouldRenderAppShell("/tools/playground")).toBe(true);
  });
});

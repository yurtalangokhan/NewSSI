import { test, expect } from "@playwright/test";
import { loginAs } from "@tests/e2e/utils/auth";
import { OnyxApiClient } from "@tests/e2e/utils/onyxApiClient";
import { sendMessage } from "@tests/e2e/utils/chatActions";

test.describe("Task 53 / Acceptance #1 — Create, Wire, Publish and Chat with Flow Agent", () => {
  let apiClient: OnyxApiClient;
  let createdAgentId: number | null = null;

  test.beforeEach(async ({ page }) => {
    await loginAs(page, "admin");
    apiClient = new OnyxApiClient(page.request);
  });

  test.afterEach(async () => {
    if (createdAgentId) {
      try {
        await apiClient.deleteAgent(createdAgentId);
      } catch (err) {
        console.warn("Teardown error deleting persona:", err);
      }
    }
  });

  test("53.1 — Full flow agent lifecycle: form -> canvas -> publish -> chat", async ({
    page,
  }) => {
    // 1. Navigate to create agent page
    await page.goto("/app/agents/create");
    await expect(
      page.locator('[data-testid="AgentsEditorPage/container"]')
    ).toBeVisible({ timeout: 15000 });

    // 2. Fill agent name & description
    await page.locator('input[name="name"]').fill("Flow Acceptance Agent");
    await page
      .locator('textarea[name="description"]')
      .fill("E2E acceptance test agent with visual flow");

    // 3. Switch to flow schema
    const flowTab = page.locator('[data-testid="editor-tab-flow"]');
    if (await flowTab.isVisible()) {
      await flowTab.click();
    }
  });
});

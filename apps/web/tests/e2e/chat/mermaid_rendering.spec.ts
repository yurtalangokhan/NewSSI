import { expect, Page, test } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { sendMessage } from "@tests/e2e/utils/chatActions";

// The fence opens in the first chunk and closes in the second, so the block
// passes through the streaming skeleton before it renders.
const DIAGRAM_HEAD =
  "Onboarding akışı:\n\n```mermaid\nflowchart LR\n  A[Başvuru] --> B[Belge kontrolü]\n";
const DIAGRAM_TAIL =
  '  B --> C["<img src=x onerror=window.__mermaidXss=1>"]\n```\n\nAkış hazır.';
const SEQUENCE =
  "```mermaid\nsequenceDiagram\n  participant P as Portal\n  participant E as ERP\n  P->>E: Kayıt\n  E-->>P: Kod\n```";
const BROKEN = "```mermaid\nflowchart LR\n  A --> B\n  B --> C[Unclosed\n```";

let turn = 0;

function buildStream(chunks: string[]): string {
  turn += 1;
  const userMessageId = turn * 100 + 1;
  const agentMessageId = turn * 100 + 2;
  const placement = { turn_index: 0, tab_index: 0 };
  const packets: Record<string, unknown>[] = [
    {
      user_message_id: userMessageId,
      reserved_assistant_message_id: agentMessageId,
    },
    {
      placement,
      obj: {
        type: "message_start",
        id: `mock-${agentMessageId}`,
        content: chunks[0],
        final_documents: null,
      },
    },
    ...chunks.slice(1).map((content) => ({
      placement,
      obj: { type: "message_delta", content },
    })),
    { placement, obj: { type: "stop", stop_reason: "finished" } },
    { message_id: agentMessageId, citations: {}, files: [] },
  ];
  return `${packets.map((packet) => JSON.stringify(packet)).join("\n")}\n`;
}

async function mockReply(page: Page, chunks: string[]): Promise<void> {
  await page.route("**/api/chat/send-chat-message", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: buildStream(chunks),
    });
  });
}

test.describe("Mermaid diagrams in chat", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    turn = 0;
    await page.context().clearCookies();
    await loginAsWorkerUser(page, testInfo.workerIndex);
    await page.goto("/app");
    await page.waitForLoadState("networkidle");
    await page.waitForSelector("#atlas-chat-input-textarea", {
      timeout: 15000,
    });
  });

  test("renders a streamed diagram as sanitized svg", async ({ page }) => {
    await mockReply(page, [DIAGRAM_HEAD, DIAGRAM_TAIL]);
    await sendMessage(page, "Süreci diyagramla göster");

    const block = page.getByTestId("mermaid-diagram").first();
    const svg = block.getByTestId("mermaid-svg").locator("svg");
    await expect(svg).toBeVisible();
    await expect(block).toHaveAttribute("data-status", "rendered");
    await expect(svg).toContainText("Başvuru");
    await expect(svg.locator("foreignObject")).toHaveCount(0);
    await expect(block.locator("img, script, [onerror]")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => (window as unknown as { __mermaidXss?: number }).__mermaidXss
      )
    ).toBeUndefined();
  });

  test("toggles code, downloads a png and zooms in the viewer", async ({
    page,
  }) => {
    await mockReply(page, [SEQUENCE]);
    await sendMessage(page, "Sıra diyagramı çiz");

    const block = page.getByTestId("mermaid-diagram").first();
    await expect(block.getByTestId("mermaid-svg").locator("svg")).toBeVisible();

    await block.getByRole("button", { name: /^(Code|Kod)$/ }).click();
    await expect(block.getByTestId("mermaid-source")).toContainText(
      "sequenceDiagram"
    );
    await block.getByRole("button", { name: /^(Diagram|Diyagram)$/ }).click();

    const download = page.waitForEvent("download");
    await block.getByRole("button", { name: /PNG/ }).click();
    expect((await download).suggestedFilename()).toBe("diagram-sequence.png");

    await block.getByRole("button", { name: /^(Expand|Büyüt)$/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByTestId("mermaid-viewer-content").locator("svg")
    ).toBeVisible();
    await dialog
      .getByRole("button", { name: /^(Zoom in|Yakınlaştır)$/ })
      .click();
    await expect(dialog.getByTestId("mermaid-viewer-zoom")).toHaveText(/125/);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("shows the failing line for a broken diagram", async ({ page }) => {
    await mockReply(page, [BROKEN]);
    await sendMessage(page, "Bozuk diyagram");

    const error = page.getByTestId("mermaid-error").first();
    await expect(error).toBeVisible();
    await expect(error.locator('[data-error-line="true"]')).toContainText(
      "C[Unclosed"
    );
    await expect(
      error.getByRole("button", {
        name: /^(Ask the agent to fix|Ajana düzelttir)$/,
      })
    ).toBeVisible();
  });
});

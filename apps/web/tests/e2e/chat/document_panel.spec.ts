import { expect, Page, test } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { sendMessage } from "@tests/e2e/utils/chatActions";

const DOC_ID = "00000000-0000-4000-8000-00000000d0c5";
const R1 =
  "# Onboarding\n\n## 1. Amaç\n\nAdımları tanımlar.\n\n| Adım | Süre |\n|---|---|\n| Belge | 3 gün |";
const R2 =
  "# Onboarding\n\n## 1. Amaç\n\nAdımları ve birimleri tanımlar.\n\n| Adım | Süre |\n|---|---|\n| Belge | 2 gün |\n| Hukuk | 3 gün |\n\n```mermaid\nflowchart LR\n  A[Başvuru] --> B[Hukuk]\n```";

const summary = (no: number) => ({
  revision_no: no,
  operation: no === 1 ? "create" : "edit",
  author_type: "agent",
  summary: no === 1 ? "İlk oluşturma" : "Hukuk incelemesi eklendi",
  format: "docx",
  stats:
    no === 1
      ? { added: 0, removed: 0, changes: [] }
      : {
          added: 9,
          removed: 3,
          changes: [{ kind: "table", label: "SLA", change: "modified" }],
        },
  rendered_file_id: `file-${no}`,
  created_at: "2026-09-28T14:18:00Z",
});

async function mockDocuments(page: Page) {
  await page.route("**/api/documents/**", async (route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/revisions\/(\d+)$/);
    if (match) {
      const no = Number(match[1]);
      return route.fulfill({
        json: {
          ...summary(no),
          document_id: DOC_ID,
          source_format: "markdown",
          content: no === 1 ? R1 : R2,
          options: {},
          title: "Onboarding",
          filename: "Onboarding.docx",
        },
      });
    }
    return route.fulfill({
      json: {
        document_id: DOC_ID,
        kind: "document",
        title: "Onboarding",
        filename: "Onboarding.docx",
        format: "docx",
        head_revision_no: 2,
        thread_id: null,
        updated_at: "2026-09-28T14:18:00Z",
        revisions: [summary(1), summary(2)],
      },
    });
  });
}

function stream(): string {
  const placement = { turn_index: 0, tab_index: 0 };
  const packets = [
    { user_message_id: 101, reserved_assistant_message_id: 102 },
    {
      placement,
      obj: {
        type: "generated_file",
        file_id: "file-2",
        filename: "Onboarding.docx",
        mime_type:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes: 24576,
        download_url: "/api/chat/file/file-2?download=1",
        document_id: DOC_ID,
        revision_no: 2,
        revision_count: 2,
        operation: "edit",
        summary: "Hukuk incelemesi eklendi",
        stats: summary(2).stats,
        diagram_check: "passed",
      },
    },
    {
      placement: { turn_index: 1, tab_index: 0 },
      obj: {
        type: "message_start",
        id: "mock-102",
        content: "Hukuk adımını ekledim.",
        final_documents: null,
      },
    },
    {
      placement: { turn_index: 1, tab_index: 0 },
      obj: { type: "stop", stop_reason: "finished" },
    },
    { message_id: 102, citations: {}, files: [] },
  ];
  return `${packets.map((p) => JSON.stringify(p)).join("\n")}\n`;
}

test.describe("Document panel", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await page.context().clearCookies();
    await loginAsWorkerUser(page, testInfo.workerIndex);
    await mockDocuments(page);
    await page.route("**/api/chat/send-chat-message", (route) =>
      route.fulfill({ status: 200, contentType: "text/plain", body: stream() })
    );
    await page.goto("/app");
    await page.waitForLoadState("networkidle");
    await page.waitForSelector("#atlas-chat-input-textarea", {
      timeout: 15000,
    });
  });

  test("opens from the chat card, switches drafts, compares and renders the diagram", async ({
    page,
  }) => {
    await sendMessage(page, "SLA tablosunu güncelle");

    const card = page.getByTestId("document-card").first();
    await expect(card).toBeVisible();
    await card.getByRole("button", { name: /See changes|Farkı gör/ }).click();

    const panel = page.getByTestId("document-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("diff-block").first()).toBeVisible();
    await expect(page.getByTestId("document-context-chip")).toBeVisible();

    await panel.getByRole("tab", { name: /Preview|Önizleme/ }).click();
    await expect(panel.getByTestId("mermaid-svg").locator("svg")).toBeVisible();

    await panel.getByRole("button", { name: /^(Draft|Taslak) 1$/ }).click();
    await expect(panel.getByText(/older draft|Eski bir taslağı/)).toBeVisible();

    await panel.getByRole("tab", { name: /Compare|Karşılaştır/ }).click();
    await expect(panel.getByTestId("compare-left")).toBeVisible();
    await expect(
      panel
        .getByTestId("compare-right")
        .locator("[data-status=changed]")
        .first()
    ).toBeVisible();
  });

  test("sends the open draft as document_context", async ({ page }) => {
    await sendMessage(page, "SLA tablosunu güncelle");
    await page
      .getByTestId("document-card")
      .first()
      .getByRole("button", { name: /See changes|Farkı gör/ })
      .click();
    await expect(page.getByTestId("document-panel")).toBeVisible();

    const request = page.waitForRequest("**/api/chat/send-chat-message");
    await sendMessage(page, "Tabloyu sadeleştir");
    expect((await request).postDataJSON().document_context).toEqual({
      document_id: DOC_ID,
      revision_no: 2,
    });
  });
});

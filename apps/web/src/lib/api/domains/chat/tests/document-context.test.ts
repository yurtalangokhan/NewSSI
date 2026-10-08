import { openChatMessageStream } from "@/lib/api/domains/chat/api";
import { apiRequest } from "@/lib/api/http/browser";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

async function bodyOf(
  params: Partial<Parameters<typeof openChatMessageStream>[0]>
) {
  jest.mocked(apiRequest).mockResolvedValue(new Response("", { status: 200 }));
  await openChatMessageStream({
    message: "m",
    parentMessageId: null,
    chatSessionId: "s",
    filters: null,
    ...params,
  } as Parameters<typeof openChatMessageStream>[0]);
  return JSON.parse(
    String(jest.mocked(apiRequest).mock.calls.at(-1)![1]!.body)
  );
}

it("sends document_context when given", async () => {
  expect(
    (await bodyOf({ documentContext: { document_id: "d", revision_no: 3 } }))
      .document_context
  ).toEqual({ document_id: "d", revision_no: 3 });
});

it("sends null without a document context", async () => {
  expect((await bodyOf({})).document_context).toBeNull();
});

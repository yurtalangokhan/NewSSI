import { updateToolsStatus } from "@/lib/api/domains/tools/api";
import { apiRequest } from "@/lib/api/http/browser";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

it("preserves tool-status error code and localized message", async () => {
  jest.mocked(apiRequest).mockResolvedValueOnce(
    Response.json(
      {
        statusCode: 403,
        data: null,
        message: "Bu işlemi yapma yetkiniz yok.",
        error: {
          code: "auth.forbidden",
          message: "Bu işlemi yapma yetkiniz yok.",
        },
      },
      { status: 403 }
    )
  );
  await expect(updateToolsStatus([1], true)).rejects.toMatchObject({
    status: 403,
    code: "auth.forbidden",
    message: "Bu işlemi yapma yetkiniz yok.",
  });
});

it("preserves successful tool status data", async () => {
  const data = { updated_count: 1, tool_ids: [1] };
  jest
    .mocked(apiRequest)
    .mockResolvedValueOnce(
      Response.json({ statusCode: 200, message: null, data, error: null })
    );
  await expect(updateToolsStatus([1], true)).resolves.toEqual(data);
});

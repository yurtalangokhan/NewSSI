import { backendRequest } from "@/lib/api/http/server";
import {
  fetchDocumentSetsSS,
  fetchStandardAnswerCategoriesSS,
  fetchStandardAnswersSS,
} from "../server";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/api/server-context", () => ({
  getServerRequestHeaders: jest.fn().mockResolvedValue({ cookie: "session=1" }),
}));

it("owns the knowledge server request targets", async () => {
  jest.mocked(backendRequest).mockResolvedValue(new Response("[]"));

  await fetchDocumentSetsSS();
  await fetchStandardAnswersSS();
  await fetchStandardAnswerCategoriesSS();

  expect(
    jest.mocked(backendRequest).mock.calls.map(([call]) => call.path)
  ).toEqual([
    "/api/v1/manage/document-set",
    "/api/v1/manage/admin/standard-answer",
    "/api/v1/manage/admin/standard-answer/category",
  ]);
});

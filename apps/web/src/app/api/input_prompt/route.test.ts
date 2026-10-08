import { GET } from "./route";
import { backendRequest } from "@/lib/api/http/server";
import { NextRequest } from "next/server";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));

const mockedBackendRequest = jest.mocked(backendRequest);

it.each([401, 403, 503])("preserves backend status %s", async (status) => {
  mockedBackendRequest.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: "Access denied" }), {
      status,
      headers: { "content-type": "application/json" },
    })
  );

  const response = await GET(
    new NextRequest("http://localhost:3000/api/input_prompt")
  );

  expect(response.status).toBe(status);
  expect(await response.json()).toEqual({ detail: "Access denied" });
});

it("returns prompt shortcuts for authorized users", async () => {
  const shortcuts = [{ id: 1, prompt: "Summarize" }];
  mockedBackendRequest.mockResolvedValueOnce(
    Response.json({
      statusCode: 200,
      message: null,
      data: { prompt_shortcuts: shortcuts },
      error: null,
    })
  );
  const response = await GET(
    new NextRequest("http://localhost:3000/api/input_prompt")
  );
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({
    statusCode: 200,
    message: null,
    data: shortcuts,
    error: null,
  });
});

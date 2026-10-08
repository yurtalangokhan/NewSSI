import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";
import { GET } from "./route";

jest.mock("@/lib/api/proxy", () => ({ proxyToBackend: jest.fn() }));

it("forwards version requests to the unchanged agent target", async () => {
  const response = NextResponse.json({});
  jest.mocked(proxyToBackend).mockResolvedValueOnce(response);
  const request = new NextRequest("http://localhost/api/version");
  await expect(GET(request)).resolves.toBe(response);
  expect(proxyToBackend).toHaveBeenCalledWith(request, {
    service: "agent",
    path: "/api/v1/version",
  });
});

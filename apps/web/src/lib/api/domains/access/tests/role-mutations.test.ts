import { apiRequest } from "@/lib/api/http/browser";
import { envelopeResponse } from "@tests/setup/responseModel";
import {
  createCoarseRole,
  createCompositeRole,
  deleteCoarseRoleResponse,
  patchCompositeRole,
  setDirectoryUserRole,
} from "@/lib/api/domains/access/api";

jest.mock("@/lib/api/http/browser", () => ({
  apiRequest: jest.fn(),
  parseJsonResponse: jest.fn(async (res: Response) => res.json()),
}));

const roleId = "33333333-3333-4333-8333-333333333333";
const json = { "Content-Type": "application/json" };

beforeEach(() => {
  jest.mocked(apiRequest).mockReset();
  jest.mocked(apiRequest).mockImplementation(async () => envelopeResponse({}));
});

it("creates a feature package as a client role under the selected service client", async () => {
  const payload = {
    name: "knowledge-reviewer",
    service_client: "rag-service-client",
    description: "Review knowledge",
    permissions: [],
  };
  await createCoarseRole(payload);

  expect(apiRequest).toHaveBeenCalledWith("/api/user-service/coarse-roles/", {
    method: "POST",
    headers: json,
    body: JSON.stringify(payload),
  });
});

it("deletes a feature package by its Keycloak role ID", async () => {
  await deleteCoarseRoleResponse(roleId);

  expect(apiRequest).toHaveBeenCalledWith(
    `/api/user-service/coarse-roles/${roleId}`,
    { method: "DELETE" }
  );
});

it("creates a composite role with a JSON body", async () => {
  await createCompositeRole({ name: "auditor", description: "" });

  expect(apiRequest).toHaveBeenCalledWith("/api/user-service/roles/", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ name: "auditor", description: "" }),
  });
});

it("patches a composite role by its Keycloak role ID with a JSON body", async () => {
  await patchCompositeRole(roleId, { description: "Operator" });

  expect(apiRequest).toHaveBeenCalledWith(`/api/user-service/roles/${roleId}`, {
    method: "PATCH",
    headers: json,
    body: JSON.stringify({ description: "Operator" }),
  });
});

it("assigns a user's role by its Keycloak role ID", async () => {
  await setDirectoryUserRole("u-1", roleId);

  expect(apiRequest).toHaveBeenCalledWith(
    "/api/user-service/users/u-1/role",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ role_id: roleId }),
    })
  );
});

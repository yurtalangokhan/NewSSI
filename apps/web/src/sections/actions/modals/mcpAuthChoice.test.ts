import {
  MCPAuthenticationPerformer,
  MCPAuthenticationType,
  MCPServerStatus,
} from "@/lib/tools/interfaces";
import type { MCPServer } from "@/lib/tools/interfaces";
import { savedAuthChoice } from "@/sections/actions/modals/mcpAuthChoice";

const server = (overrides: Partial<MCPServer>) =>
  ({
    id: 1,
    name: "Deneme",
    server_url: "https://example.com/mcp",
    status: MCPServerStatus.CONNECTED,
    auth_type: MCPAuthenticationType.API_TOKEN,
    auth_performer: MCPAuthenticationPerformer.ADMIN,
    ...overrides,
  }) as MCPServer;

it("has no saved choice for a provider that was only registered", () => {
  // The backend stores NONE for a registered provider; that is "not chosen
  // yet", not "no authentication".
  expect(
    savedAuthChoice(
      server({
        status: MCPServerStatus.CREATED,
        auth_type: MCPAuthenticationType.NONE,
        auth_performer: undefined,
      })
    )
  ).toBeNull();
});

it("returns what a configured server saved", () => {
  expect(savedAuthChoice(server({}))).toEqual({
    auth_type: MCPAuthenticationType.API_TOKEN,
    auth_performer: MCPAuthenticationPerformer.ADMIN,
  });
});

it("has no saved choice before the server detail is loaded", () => {
  expect(savedAuthChoice(undefined)).toBeNull();
});

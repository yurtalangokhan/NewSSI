import React from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { UserProvider, useUser } from "./UserProvider";
import { User } from "@/lib/types";
import { CombinedSettings } from "@/interfaces/settings";
import { AuthTypeMetadata } from "@/lib/userSS";

const mockUser: User = {
  id: "1",
  email: "test@example.com",
  is_active: true,
  is_verified: true,
  role: "user",
  team_name: null,
  preferences: {
    default_model: null,
    default_provider_id: null,
  } as any,
  personalization: {} as any,
};

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <UserProvider
      user={mockUser}
      settings={{} as CombinedSettings}
      authTypeMetadata={{} as AuthTypeMetadata}
    >
      {children}
    </UserProvider>
  );
}

describe("UserProvider updateUserDefaultModel", () => {
  beforeEach(() => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response(null, { status: 200 }));
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("optimistically updates both default_model and default_provider_id together, so the saved provider is not lost until the next refetch", async () => {
    const { result } = renderHook(() => useUser(), { wrapper });

    await act(async () => {
      await result.current.updateUserDefaultModel("gpt-4o", "3");
    });

    await waitFor(() => {
      expect(result.current.user?.preferences?.default_model).toBe("gpt-4o");
    });
    expect(result.current.user?.preferences?.default_provider_id).toBe("3");
  });

  it("clears default_provider_id locally when it is explicitly reset to null", async () => {
    const { result } = renderHook(() => useUser(), { wrapper });

    await act(async () => {
      await result.current.updateUserDefaultModel("gpt-4o", "3");
    });
    await waitFor(() => {
      expect(result.current.user?.preferences?.default_provider_id).toBe("3");
    });

    await act(async () => {
      await result.current.updateUserDefaultModel(null, null);
    });

    await waitFor(() => {
      expect(result.current.user?.preferences?.default_model).toBeNull();
    });
    expect(result.current.user?.preferences?.default_provider_id).toBeNull();
  });
});

import { act, render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { ProviderContextProvider, useProviderStatus } from "./ProviderContext";
import { useUser } from "@/providers/UserProvider";
import { testDefaultProvider } from "@/lib/api/domains/model-providers/api";

jest.mock("@/providers/UserProvider", () => ({ useUser: jest.fn() }));
jest.mock("@/lib/api/domains/model-providers/api", () => ({
  testDefaultProvider: jest.fn().mockResolvedValue(true),
}));
const mockRefetch = jest.fn();
jest.mock("@/lib/api/domains/model-providers/hooks", () => ({
  useLLMProviders: () => ({ refetch: mockRefetch }),
  useLLMProviderOptions: () => ({ refetch: mockRefetch }),
}));

let refresh: () => Promise<void>;
function Consumer() {
  const { refreshProviderInfo } = useProviderStatus();
  // Published from an effect: assigning a module variable during render is a
  // react-hooks/globals error.
  useEffect(() => {
    refresh = refreshProviderInfo;
  });
  return null;
}

test.each([null, { id: "unprivileged-user" }])(
  "does not probe restricted providers before access is granted: %p",
  async (user) => {
    localStorage.clear();
    jest.clearAllMocks();
    jest.mocked(useUser).mockReturnValue({
      user,
      hasPermission: () => false,
    } as unknown as ReturnType<typeof useUser>);
    render(
      <ProviderContextProvider>
        <Consumer />
      </ProviderContextProvider>
    );
    await waitFor(() => expect(refresh).toBeDefined());
    await refresh();
    expect(testDefaultProvider).not.toHaveBeenCalled();
    expect(mockRefetch).not.toHaveBeenCalled();
  }
);

test("starts provider checks after provider:read is granted", async () => {
  localStorage.clear();
  jest.clearAllMocks();
  jest.mocked(useUser).mockReturnValue({
    hasPermission: () => false,
  } as unknown as ReturnType<typeof useUser>);
  const view = render(
    <ProviderContextProvider>
      <Consumer />
    </ProviderContextProvider>
  );
  expect(testDefaultProvider).not.toHaveBeenCalled();

  jest.mocked(useUser).mockReturnValue({
    hasPermission: (permission: string) => permission === "provider:read",
  } as unknown as ReturnType<typeof useUser>);
  view.rerender(
    <ProviderContextProvider>
      <Consumer />
    </ProviderContextProvider>
  );
  await waitFor(() => expect(testDefaultProvider).toHaveBeenCalledTimes(1));
  await act(async () => {
    await refresh();
  });
  expect(mockRefetch).toHaveBeenCalledTimes(2);
});

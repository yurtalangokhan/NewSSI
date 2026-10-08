import useSWR from "swr";
import { useUser } from "@/providers/UserProvider";
import { usePromptShortcuts } from "../hooks";

jest.mock("swr", () => ({ __esModule: true, default: jest.fn() }));
jest.mock("@/providers/UserProvider", () => ({ useUser: jest.fn() }));

test.each([false, true])(
  "prompt shortcuts respect settings:read=%s",
  (allowed) => {
    jest.mocked(useUser).mockReturnValue({
      hasPermission: (permission: string) =>
        allowed && permission === "settings:read",
    } as ReturnType<typeof useUser>);
    const mutate = jest.fn();
    const shortcuts = [{ id: 1, active: true, is_public: false }];
    jest
      .mocked(useSWR)
      .mockReturnValue({ data: shortcuts, isLoading: true, mutate } as any);

    const result = usePromptShortcuts();

    expect(useSWR).toHaveBeenLastCalledWith(
      allowed ? "/api/input_prompt" : null,
      expect.any(Function)
    );
    expect(result.promptShortcuts).toEqual(allowed ? shortcuts : []);
    expect(result.isLoading).toBe(allowed);
    result.refresh();
    expect(mutate).toHaveBeenCalledTimes(allowed ? 1 : 0);
  }
);

test.each([false, true])(
  "returns the same empty shortcut list across renders when access=%s and data is absent",
  (allowed) => {
    jest.mocked(useUser).mockReturnValue({
      hasPermission: (permission: string) =>
        allowed && permission === "settings:read",
    } as ReturnType<typeof useUser>);
    jest.mocked(useSWR).mockReturnValue({
      data: undefined,
      isLoading: false,
      mutate: jest.fn(),
    } as any);

    const first = usePromptShortcuts();
    const second = usePromptShortcuts();

    expect(second.promptShortcuts).toBe(first.promptShortcuts);
  }
);

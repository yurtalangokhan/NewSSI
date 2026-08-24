import { renderHook, act } from "@testing-library/react";
import useUserPersonalization from "./useUserPersonalization";
import { User, UserPersonalization } from "@/lib/types";

describe("useUserPersonalization", () => {
  const mockUser: User = {
    id: "1",
    email: "test@example.com",
    is_active: true,
    is_verified: true,
    role: "user",
    team_name: null,
    preferences: {} as any,
    personalization: {
      name: "John Doe",
      role: "Developer",
      long_term_memory_enabled: false,
      extract_memory: true,
      user_preferences: "Initial preferences",
    },
  };

  it("does not call persistPersonalization or onSuccess when saving with unchanged values", async () => {
    const persistPersonalization = jest.fn().mockResolvedValue(undefined);
    const onSuccess = jest.fn();
    const onError = jest.fn();

    const { result } = renderHook(() =>
      useUserPersonalization(mockUser, persistPersonalization, {
        onSuccess,
        onError,
      })
    );

    // Call save without any changes (e.g. onBlur on an unedited input)
    await act(async () => {
      await result.current.handleSavePersonalization();
    });

    expect(persistPersonalization).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("calls persistPersonalization and onSuccess when user_preferences has changed", async () => {
    const persistPersonalization = jest.fn().mockResolvedValue(undefined);
    const onSuccess = jest.fn();
    const onError = jest.fn();

    const { result } = renderHook(() =>
      useUserPersonalization(mockUser, persistPersonalization, {
        onSuccess,
        onError,
      })
    );

    // Update preferences
    act(() => {
      result.current.updateUserPreferences("Updated preferences");
    });

    // Save
    await act(async () => {
      await result.current.handleSavePersonalization();
    });

    expect(persistPersonalization).toHaveBeenCalledTimes(1);
    expect(persistPersonalization).toHaveBeenCalledWith(
      expect.objectContaining({
        user_preferences: "Updated preferences",
      })
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);

    // Subsequent save without further changes should NOT save again
    persistPersonalization.mockClear();
    onSuccess.mockClear();

    await act(async () => {
      await result.current.handleSavePersonalization();
    });

    expect(persistPersonalization).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("calls persistPersonalization when overrides contain changed values", async () => {
    const persistPersonalization = jest.fn().mockResolvedValue(undefined);
    const onSuccess = jest.fn();
    const onError = jest.fn();

    const { result } = renderHook(() =>
      useUserPersonalization(mockUser, persistPersonalization, {
        onSuccess,
        onError,
      })
    );

    // Save with override (e.g. toggle switch)
    await act(async () => {
      await result.current.handleSavePersonalization({
        long_term_memory_enabled: true,
      });
    });

    expect(persistPersonalization).toHaveBeenCalledTimes(1);
    expect(persistPersonalization).toHaveBeenCalledWith(
      expect.objectContaining({
        long_term_memory_enabled: true,
      })
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });
});

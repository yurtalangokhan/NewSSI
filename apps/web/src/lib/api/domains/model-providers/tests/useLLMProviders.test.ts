import useSWR from "swr";
import { useSWRConfig } from "swr";
import {
  useLLMProviders,
  useLLMProviderOptions,
  useAvailableModels,
} from "@/lib/api/domains/model-providers/hooks";
import { useUser } from "@/providers/UserProvider";

jest.mock("@/providers/UserProvider", () => ({ useUser: jest.fn() }));

beforeEach(() => {
  jest.mocked(useUser).mockReturnValue({
    hasPermission: (permission: string) => permission === "provider:read",
  } as unknown as ReturnType<typeof useUser>);
});

jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(),
  useSWRConfig: jest.fn(),
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockUseSWRConfig = useSWRConfig as jest.MockedFunction<
  typeof useSWRConfig
>;

describe("useLLMProviders", () => {
  beforeEach(() => {
    mockUseSWR.mockReset();
    mockUseSWRConfig.mockReset();
    mockUseSWRConfig.mockReturnValue({ mutate: jest.fn() } as any);
  });

  test("uses public providers endpoint when personaId is not provided", () => {
    const mockMutate = jest.fn();
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      mutate: mockMutate,
      isValidating: false,
    } as any);

    const result = useLLMProviders();

    expect(mockUseSWR).toHaveBeenCalledWith(
      "/api/llm/provider",
      expect.any(Function),
      expect.objectContaining({
        revalidateOnFocus: false,
        dedupingInterval: 60000,
      })
    );
    expect(result.isLoading).toBe(true);
    expect(result.refetch).toBe(mockMutate);
  });

  test("uses persona-specific providers endpoint when personaId is provided", () => {
    const mockMutate = jest.fn();
    const providers = [{ name: "Persona Provider" }];
    mockUseSWR.mockReturnValue({
      data: { providers, default_text: null, default_vision: null },
      error: undefined,
      mutate: mockMutate,
      isValidating: false,
    } as any);

    const result = useLLMProviders(42);

    expect(mockUseSWR).toHaveBeenCalledWith(
      "/api/llm/persona/42/providers",
      expect.any(Function),
      expect.objectContaining({
        revalidateOnFocus: false,
        dedupingInterval: 60000,
      })
    );
    expect(result.llmProviders).toBe(providers);
    expect(result.isLoading).toBe(false);
    expect(result.refetch).toBe(mockMutate);
  });

  test("can defer persona-specific provider fetch until refetch is requested", async () => {
    const mockMutate = jest.fn();
    mockUseSWRConfig.mockReturnValue({ mutate: mockMutate } as any);
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      mutate: jest.fn(),
      isValidating: false,
    } as any);

    const result = useLLMProviders(42, { enabled: false });

    expect(mockUseSWR).toHaveBeenCalledWith(
      null,
      expect.any(Function),
      expect.objectContaining({
        revalidateOnFocus: false,
        dedupingInterval: 60000,
      })
    );

    await result.refetch();

    expect(mockMutate).toHaveBeenCalledWith("/api/llm/persona/42/providers");
  });

  test("reports not loading when SWR returns an error", () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: new Error("request failed"),
      mutate: jest.fn(),
      isValidating: false,
    } as any);

    const result = useLLMProviders();

    expect(result.isLoading).toBe(false);
    expect(result.error).toBeInstanceOf(Error);
  });
});

describe("provider read authorization", () => {
  test.each([useAvailableModels, useLLMProviders])(
    "%p skips fetching and refresh without provider:read",
    async (useProviders) => {
      jest.mocked(useUser).mockReturnValue({
        hasPermission: (permission: string) => permission === "chat:send",
      } as unknown as ReturnType<typeof useUser>);
      const mutate = jest.fn();
      mockUseSWRConfig.mockReturnValue({ mutate } as any);
      mockUseSWR.mockReset();
      mockUseSWR.mockReturnValue({ data: { providers: [] }, mutate } as any);

      const result = useProviders();

      expect(mockUseSWR).toHaveBeenCalledWith(
        null,
        expect.any(Function),
        expect.any(Object)
      );
      expect(result.isLoading).toBe(false);
      expect(result.llmProviders).toEqual([]);
      await result.refetch();
      expect(mutate).not.toHaveBeenCalled();
    }
  );

  test("fetches available models with provider:read", () => {
    const providers = [{ name: "Allowed provider" }];
    mockUseSWR.mockReset();
    mockUseSWR.mockReturnValue({ data: providers, mutate: jest.fn() } as any);
    expect(useAvailableModels().llmProviders).toEqual(providers);
    expect(mockUseSWR).toHaveBeenCalledWith(
      "/api/admin/providers/available-models",
      expect.any(Function),
      expect.any(Object)
    );
  });
});

describe("useLLMProviderOptions", () => {
  test("does not request the admin catalog when provider access is absent", () => {
    mockUseSWR.mockReset();
    mockUseSWR.mockReturnValue({ mutate: jest.fn() } as any);

    useLLMProviderOptions({ enabled: false } as any);

    expect(mockUseSWR).toHaveBeenCalledWith(
      null,
      expect.any(Function),
      expect.any(Object)
    );
  });
});

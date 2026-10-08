import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  ProjectsProvider,
  useProjectsContext,
} from "@/providers/ProjectsContext";
import { uploadFiles } from "@/lib/api/domains/projects/api";
import { toast } from "@/hooks/useToast";
import { tServer } from "@/i18n/server";
import type { SupportedLanguage } from "@/i18n/locales";

let mockLanguage: SupportedLanguage = "tr";
const mockRefreshProjects = jest.fn().mockResolvedValue([]);
const mockProjects: unknown[] = [];
const mockFocus = {
  isProject: () => false,
  isChat: () => false,
  getId: () => null,
};
const mockSearchParams = new URLSearchParams();
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      tServer(key, { ...options, lng: mockLanguage }),
  }),
}));
jest.mock("@/lib/api/domains/projects/hooks", () => ({
  useProjects: () => ({
    projects: mockProjects,
    refreshProjects: mockRefreshProjects,
  }),
}));
jest.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
}));
jest.mock("@/hooks/useAppFocus", () => ({
  __esModule: true,
  default: () => mockFocus,
}));
jest.mock("@/hooks/appNavigation", () => ({ useAppRouter: () => jest.fn() }));
jest.mock("@/hooks/useToast", () => ({
  toast: { warning: jest.fn(), error: jest.fn(), success: jest.fn() },
}));
jest.mock("@/lib/api/domains/projects/api", () => ({
  uploadFiles: jest.fn(),
  getRecentFiles: jest.fn().mockResolvedValue([]),
}));
jest.mock("@/lib/api/domains/chat/files", () => ({
  generateUUID: jest.fn(),
  mimeTypeToChatFileType: jest.fn(),
  fileToProjectFile: jest.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  return <ProjectsProvider>{children}</ProjectsProvider>;
}

it.each([
  ["en", "Some files were not uploaded. Invalid file."],
  ["tr", "Bazı dosyalar yüklenemedi. Invalid file."],
] as const)(
  "localizes partial upload feedback in %s",
  async (locale, expected) => {
    mockLanguage = locale;
    jest.mocked(uploadFiles).mockResolvedValueOnce({
      user_files: [],
      rejected_files: [{ file_name: "rejected.txt", reason: "Invalid file." }],
    });
    const { result } = renderHook(() => useProjectsContext(), { wrapper });
    await act(async () => {
      await result.current.beginUpload([new File(["text"], "rejected.txt")]);
    });
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(expected));
    expect(result.current.allRecentFiles).toEqual([]);
  }
);

it("localizes unknown upload failures and removes optimistic files", async () => {
  mockLanguage = "tr";
  jest.mocked(uploadFiles).mockRejectedValueOnce({});
  const { result } = renderHook(() => useProjectsContext(), { wrapper });
  await act(async () => {
    await result.current.beginUpload([new File(["text"], "rejected.txt")]);
  });
  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("Dosya yüklenirken hata oluştu")
  );
  expect(result.current.allRecentFiles).toEqual([]);
});

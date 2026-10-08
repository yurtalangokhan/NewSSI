import { act, renderHook } from "@testing-library/react";
import {
  WHITE_PAGE_STORAGE_KEY,
  cycleWhitePageMode,
  getWhitePageMode,
  setWhitePageMode,
  useWhitePage,
} from "@/sections/document-panel/useWhitePage";

beforeEach(() => {
  window.localStorage.clear();
  setWhitePageMode("off");
});

it("defaults to the app surface", () => {
  const { result } = renderHook(() => useWhitePage());

  expect(result.current[0]).toBe("off");
});

it("cycles off → paper → page → off and remembers each step", () => {
  const { result } = renderHook(() => useWhitePage());

  act(() => cycleWhitePageMode());
  expect(result.current[0]).toBe("paper");
  expect(window.localStorage.getItem(WHITE_PAGE_STORAGE_KEY)).toBe("paper");

  act(() => cycleWhitePageMode());
  expect(result.current[0]).toBe("page");
  expect(window.localStorage.getItem(WHITE_PAGE_STORAGE_KEY)).toBe("page");

  act(() => cycleWhitePageMode());
  expect(result.current[0]).toBe("off");
  expect(window.localStorage.getItem(WHITE_PAGE_STORAGE_KEY)).toBe("off");
});

it("reads the stored mode on the next page load", () => {
  window.localStorage.setItem(WHITE_PAGE_STORAGE_KEY, "paper");

  jest.isolateModules(() => {
    const fresh = require("@/sections/document-panel/useWhitePage") as {
      getWhitePageMode: () => string;
    };
    expect(fresh.getWhitePageMode()).toBe("paper");
  });

  expect(getWhitePageMode()).toBe("off");
});

it("still reads the single-flag value older builds stored", () => {
  window.localStorage.setItem(WHITE_PAGE_STORAGE_KEY, "1");

  jest.isolateModules(() => {
    const fresh = require("@/sections/document-panel/useWhitePage") as {
      getWhitePageMode: () => string;
    };
    expect(fresh.getWhitePageMode()).toBe("page");
  });
});

"use client";

import { useEffect, useState } from "react";
import {
  toMermaidDiagnostic,
  type MermaidDiagnostic,
} from "@/components/mermaid/mermaidDiagnostics";
import {
  getMermaidRuntime,
  type MermaidRenderResult,
} from "@/components/mermaid/mermaidRuntime";
import type { MermaidThemeConfig } from "@/components/mermaid/mermaidTheme";

export type MermaidRenderState =
  | { status: "pending"; lastGood: MermaidRenderResult | null }
  | { status: "rendered"; result: MermaidRenderResult }
  | {
      status: "error";
      diagnostic: MermaidDiagnostic;
      lastGood: MermaidRenderResult | null;
    };

function lastGoodOf(state: MermaidRenderState): MermaidRenderResult | null {
  return state.status === "rendered" ? state.result : state.lastGood;
}

function initialState(
  source: string,
  isComplete: boolean,
  theme: MermaidThemeConfig
): MermaidRenderState {
  if (isComplete) {
    const cached = getMermaidRuntime().peek(source, theme);
    if (cached) return { status: "rendered", result: cached };
  }
  return { status: "pending", lastGood: null };
}

/**
 * Renders only complete sources and keeps the last good SVG through
 * re-renders (theme switch, edited source) and failures, as spec §5.1 asks.
 */
export function useMermaidRender(
  source: string,
  isComplete: boolean,
  theme: MermaidThemeConfig
): MermaidRenderState {
  const [state, setState] = useState<MermaidRenderState>(() =>
    initialState(source, isComplete, theme)
  );

  useEffect(() => {
    if (!isComplete) {
      setState((previous) =>
        previous.status === "pending"
          ? previous
          : { status: "pending", lastGood: lastGoodOf(previous) }
      );
      return;
    }

    const runtime = getMermaidRuntime();
    const cached = runtime.peek(source, theme);
    if (cached) {
      setState((previous) =>
        previous.status === "rendered" && previous.result === cached
          ? previous
          : { status: "rendered", result: cached }
      );
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState((previous) =>
      previous.status === "pending"
        ? previous
        : { status: "pending", lastGood: lastGoodOf(previous) }
    );
    runtime.render(source, theme, controller.signal).then(
      (result) => {
        if (!cancelled) setState({ status: "rendered", result });
      },
      (error: unknown) => {
        if (cancelled) return;
        setState((previous) => ({
          status: "error",
          diagnostic: toMermaidDiagnostic(error),
          lastGood: lastGoodOf(previous),
        }));
      }
    );
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [source, isComplete, theme.key]);

  return state;
}

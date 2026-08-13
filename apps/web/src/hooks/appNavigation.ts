"use client";

import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { useCallback } from "react";

export type AppFocusValue =
  | { type: "agent" | "project" | "chat"; id: string }
  | "new-session"
  | "more-agents"
  | "user-settings"
  | "shared-chat";

export type AppPathInput =
  | { type: "new-session" }
  | { type: "chat" | "agent" | "project"; id: string | number };

interface UseAppRouterProps {
  chatSessionId?: string;
  agentId?: string | number;
  projectId?: number;
}

function appPathSegment(value: string | number) {
  return encodeURIComponent(String(value));
}

export function buildAppPath(focus: AppPathInput) {
  if (focus.type === "new-session") {
    return "/app";
  }
  if (focus.type === "chat") {
    return `/app/chats/${appPathSegment(focus.id)}`;
  }
  if (focus.type === "agent") {
    return `/app/agents/${appPathSegment(focus.id)}`;
  }
  return `/app/projects/${appPathSegment(focus.id)}`;
}

function getPathId(pathname: string, prefix: string) {
  if (!pathname.startsWith(prefix)) {
    return null;
  }

  const rest = pathname.slice(prefix.length);
  const [id] = rest.split("/");
  return id ? decodeURIComponent(id) : null;
}

const LEGACY_APP_FOCUS_PARAMS = new Set([
  SEARCH_PARAM_NAMES.CHAT_ID,
  SEARCH_PARAM_NAMES.PERSONA_ID,
  SEARCH_PARAM_NAMES.PROJECT_ID,
]);

function appendRemainingQueryParams(
  path: string,
  searchParams: Pick<URLSearchParams, "forEach">,
  paramsToSkip: Set<string>
) {
  const nextSearchParams = new URLSearchParams();
  searchParams.forEach((value, key) => {
    if (!paramsToSkip.has(key)) {
      nextSearchParams.append(key, value);
    }
  });
  const query = nextSearchParams.toString();
  return query ? `${path}?${query}` : path;
}

export function buildCanonicalAppPathFromSearch(
  searchParams: Pick<URLSearchParams, "get" | "forEach">
) {
  const chatId = searchParams.get(SEARCH_PARAM_NAMES.CHAT_ID);
  if (chatId) {
    return appendRemainingQueryParams(
      buildAppPath({ type: "chat", id: chatId }),
      searchParams,
      LEGACY_APP_FOCUS_PARAMS
    );
  }

  const agentId = searchParams.get(SEARCH_PARAM_NAMES.PERSONA_ID);
  if (agentId) {
    return appendRemainingQueryParams(
      buildAppPath({ type: "agent", id: agentId }),
      searchParams,
      new Set([SEARCH_PARAM_NAMES.CHAT_ID, SEARCH_PARAM_NAMES.PERSONA_ID])
    );
  }

  const projectId = searchParams.get(SEARCH_PARAM_NAMES.PROJECT_ID);
  if (projectId) {
    return appendRemainingQueryParams(
      buildAppPath({ type: "project", id: projectId }),
      searchParams,
      LEGACY_APP_FOCUS_PARAMS
    );
  }

  return null;
}

export function parseAppFocus(
  pathname: string,
  searchParams: Pick<URLSearchParams, "get">
): AppFocusValue {
  if (pathname.startsWith("/app/shared/")) {
    return "shared-chat";
  }

  if (pathname.startsWith("/app/settings")) {
    return "user-settings";
  }

  const chatPathId = getPathId(pathname, "/app/chats/");
  if (chatPathId) {
    return { type: "chat", id: chatPathId };
  }

  const projectPathId = getPathId(pathname, "/app/projects/");
  if (projectPathId) {
    return { type: "project", id: projectPathId };
  }

  const agentPathId = getPathId(pathname, "/app/agents/");
  if (agentPathId && !["create", "edit"].includes(agentPathId)) {
    return { type: "agent", id: agentPathId };
  }

  if (pathname.startsWith("/app/agents")) {
    return "more-agents";
  }

  const chatId = searchParams.get(SEARCH_PARAM_NAMES.CHAT_ID);
  if (chatId) return { type: "chat", id: chatId };

  const agentId = searchParams.get(SEARCH_PARAM_NAMES.PERSONA_ID);
  if (agentId) return { type: "agent", id: agentId };

  const projectId = searchParams.get(SEARCH_PARAM_NAMES.PROJECT_ID);
  if (projectId) return { type: "project", id: projectId };

  return "new-session";
}

export function useAppRouter() {
  const router = useRouter();
  return useCallback(
    ({ chatSessionId, agentId, projectId }: UseAppRouterProps = {}) => {
      const finalUrl = chatSessionId
        ? buildAppPath({ type: "chat", id: chatSessionId })
        : agentId
          ? buildAppPath({ type: "agent", id: agentId })
          : projectId
            ? buildAppPath({ type: "project", id: projectId })
            : buildAppPath({ type: "new-session" });

      router.push(finalUrl as Route);
    },
    [router]
  );
}

export function useAppParams() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  return useCallback(
    (name: string) => {
      const appFocus = parseAppFocus(pathname, searchParams);
      if (
        name === SEARCH_PARAM_NAMES.CHAT_ID &&
        typeof appFocus === "object" &&
        appFocus.type === "chat"
      ) {
        return appFocus.id;
      }
      if (
        name === SEARCH_PARAM_NAMES.PERSONA_ID &&
        typeof appFocus === "object" &&
        appFocus.type === "agent"
      ) {
        return appFocus.id;
      }
      if (
        name === SEARCH_PARAM_NAMES.PROJECT_ID &&
        typeof appFocus === "object" &&
        appFocus.type === "project"
      ) {
        return appFocus.id;
      }
      return searchParams.get(name);
    },
    [pathname, searchParams]
  );
}

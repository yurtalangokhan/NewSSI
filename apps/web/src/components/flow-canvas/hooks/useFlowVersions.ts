/**
 * Version history + publish + rollback for a flow-backed agent
 * definition. Mirrors `FlowVersionsRoute.py` exactly — see that file's
 * response shapes; not hand-guessed.
 *
 * Publish/rollback error handling follows design spec §10 precisely:
 * - 409 → the flow was published concurrently. Returned as a distinct
 *   `"conflict"` result so the caller (VersionBar) can offer
 *   reload-and-retry — never silently retried, never discarding the
 *   user's draft.
 * - 400 with `{detail: {errors: [...]}}` → publish refused by server-side
 *   validation. Returned as `"invalid"` with the raw issues so the
 *   caller can route each one to its `node_id`.
 * P3's `publish_flow` validates regardless of client state — this hook's
 * own `useFlowValidation` is an affordance, not the actual gate.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type { WireFlowSpec } from "../types/flow";
import { flowApi } from "@/components/flow-canvas/api/flowApi";

export type FlowVersionStatus = "draft" | "published" | "archived";

export type FlowVersion = {
  id: string;
  definition_id: string;
  version_no: number;
  status: FlowVersionStatus;
  created_by: string;
  published_by: string | null;
  created_at: string | null;
  published_at: string | null;
  notes: string | null;
};

/** Task 45 — one version row plus its stored `flow_spec`, from
 * GET /agent-definitions/{id}/flow/versions/{version_no}. The spec is the
 * verbatim historical artifact (no template migration), which is exactly
 * what a canvas preview must render. */
export type FlowVersionDetail = FlowVersion & { flow_spec: WireFlowSpec };

export type PublishIssue = {
  code: string;
  message: string;
  node_id: string | null;
  edge_id: string | null;
};

export type PublishResult =
  | { kind: "success"; version: FlowVersion }
  | { kind: "conflict"; message: string | null }
  | { kind: "invalid"; errors: PublishIssue[] };

async function safeJson(
  res: Response
): Promise<Record<string, unknown> | null> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export function useFlowVersions(definitionId: string) {
  const {
    data: versions,
    error,
    isLoading,
    mutate,
  } = useSWR<FlowVersion[]>(
    flowApi.versions(definitionId),
    errorHandlingFetcher
  );

  async function publish(
    expectedVersionNo?: number,
    notes?: string
  ): Promise<PublishResult> {
    const body: Record<string, unknown> = {};
    if (expectedVersionNo !== undefined)
      body.expected_version_no = expectedVersionNo;
    if (notes) body.notes = notes;

    const res = await fetch(flowApi.publish(definitionId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });

    if (res.status === 409) {
      const body = await safeJson(res);
      const detail = typeof body?.detail === "string" ? body.detail : null;
      return { kind: "conflict", message: detail };
    }

    if (res.status === 400) {
      const body = await safeJson(res);
      const detail = body?.detail as { errors?: PublishIssue[] } | undefined;
      return { kind: "invalid", errors: detail?.errors ?? [] };
    }

    if (!res.ok) {
      throw new Error(`Publish failed: ${res.status}`);
    }

    const version = (await res.json()) as FlowVersion;
    await mutate();
    return { kind: "success", version };
  }

  async function rollback(targetVersionNo: number): Promise<FlowVersion> {
    const res = await fetch(flowApi.rollback(definitionId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ target_version_no: targetVersionNo }),
    });

    if (!res.ok) {
      throw new Error(`Rollback failed: ${res.status}`);
    }

    const version = (await res.json()) as FlowVersion;
    await mutate();
    return version;
  }

  async function getVersionDetail(
    versionNo: number
  ): Promise<FlowVersionDetail | null> {
    const res = await fetch(flowApi.version(definitionId, versionNo), {
      credentials: "include",
    });
    if (res.status === 404) return null;
    if (!res.ok)
      throw new Error(`Failed to load version ${versionNo}: ${res.status}`);
    return (await res.json()) as FlowVersionDetail;
  }

  const publishedVersion =
    versions?.find((v) => v.status === "published") ?? null;
  const draftVersion = versions?.find((v) => v.status === "draft") ?? null;

  return {
    versions: versions ?? [],
    isLoading,
    error,
    publishedVersion,
    draftVersion,
    publish,
    rollback,
    getVersionDetail,
    refresh: mutate,
  };
}

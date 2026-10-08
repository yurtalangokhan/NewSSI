"use client";

import useSWR from "swr";
import { fetchRoleDistribution } from "@/lib/api/domains/access/api";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

export interface RoleCount {
  role: string;
  count: number;
}

export interface RoleDistributionResponse {
  status: "ready" | "pending" | "unavailable";
  distribution: RoleCount[];
  computed_at: string | null;
}

/** `calculating`: the backend is computing its first snapshot and is polled. */
export type RoleDistributionState =
  | "loading"
  | "calculating"
  | "ready"
  | "unavailable";

const DEFAULT_POLL_INTERVAL_MS = 5000;

export interface UseRoleDistributionOptions {
  pollIntervalMs?: number;
}

/**
 * Primary-role counts for admin dashboards.
 *
 * The backend serves this statistic from a background-refreshed snapshot, so a
 * cold read answers `pending` at once; poll until it is ready rather than
 * holding a request open past the gateway timeout.
 */
export default function useRoleDistribution({
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: UseRoleDistributionOptions = {}) {
  const { data, error, isLoading } = useSWR<RoleDistributionResponse>(
    accessEndpoints.userRoleDistribution.browserPath,
    () => fetchRoleDistribution<RoleDistributionResponse>(),
    {
      refreshInterval: (latest) =>
        latest?.status === "pending" ? pollIntervalMs : 0,
    }
  );

  let state: RoleDistributionState;
  if (data?.status === "ready") state = "ready";
  else if (data?.status === "pending") state = "calculating";
  else if (data?.status === "unavailable" || error) state = "unavailable";
  else state = isLoading ? "loading" : "unavailable";

  return {
    distribution: data?.status === "ready" ? data.distribution : [],
    state,
  };
}

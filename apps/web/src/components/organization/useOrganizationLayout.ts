"use client";

import { authenticatedFetch } from "@/lib/fetcher";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { XYPosition } from "@xyflow/react";
import useSWR from "swr";

export interface OrganizationLayoutPosition extends XYPosition {
  organization_id: string;
}

export interface OrganizationLayoutResponse {
  positions: OrganizationLayoutPosition[];
  writable_organization_ids: string[];
}

export type OrganizationLayoutStatus = "idle" | "saving" | "saved" | "error";
export const MAX_ORGANIZATION_LAYOUT_POSITIONS = 100_000;

export type OrganizationPositionMap = Record<string, XYPosition>;
type PositionMap = OrganizationPositionMap;
type SaveLayout = (
  positions: OrganizationLayoutPosition[]
) => Promise<{ positions: OrganizationLayoutPosition[]; count: number }>;

interface UseOrganizationLayoutOptions {
  debounceMs?: number;
  enabled?: boolean;
  layout?: OrganizationLayoutResponse;
  remoteLayout?: OrganizationLayoutResponse;
  saveLayout?: SaveLayout;
}

async function getLayout(url: string): Promise<OrganizationLayoutResponse> {
  const response = await fetch(url);
  if (!response.ok) {
    throw await responseError(
      response,
      "Organization layout could not be loaded"
    );
  }
  return response.json();
}

async function saveOrganizationLayout(
  positions: OrganizationLayoutPosition[]
): Promise<{ positions: OrganizationLayoutPosition[]; count: number }> {
  if (positions.length > MAX_ORGANIZATION_LAYOUT_POSITIONS) {
    throw new Error(
      `Organization layout cannot exceed ${MAX_ORGANIZATION_LAYOUT_POSITIONS} positions`
    );
  }
  const response = await authenticatedFetch(
    "/api/user-service/organizations/layout",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positions }),
    }
  );
  if (!response.ok) {
    throw await responseError(
      response,
      "Organization layout could not be saved"
    );
  }
  return response.json();
}

async function responseError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => null)) as {
    detail?: string;
    message?: string;
  } | null;
  return new Error(data?.detail || data?.message || fallback);
}

function positionMap(
  layout: OrganizationLayoutResponse | undefined
): PositionMap {
  return Object.fromEntries(
    (layout?.positions ?? []).map(({ organization_id, x, y }) => [
      organization_id,
      { x, y },
    ])
  );
}

function positionsEqual(first: XYPosition, second: XYPosition) {
  return first.x === second.x && first.y === second.y;
}

export function createOrganizationLayoutPayload(
  positions: OrganizationPositionMap,
  writableOrganizationIds: ReadonlySet<string>
): OrganizationLayoutPosition[] {
  const payload = Object.entries(positions)
    .filter(([organizationId]) => writableOrganizationIds.has(organizationId))
    .map(([organization_id, { x, y }]) => ({ organization_id, x, y }));
  if (payload.length > MAX_ORGANIZATION_LAYOUT_POSITIONS) {
    throw new Error(
      `Organization layout cannot exceed ${MAX_ORGANIZATION_LAYOUT_POSITIONS} positions`
    );
  }
  return payload;
}

function mergeLayoutBaseline(
  baseline: OrganizationLayoutResponse | undefined,
  positions: OrganizationLayoutPosition[],
  writableOrganizationIds: string[]
): OrganizationLayoutResponse {
  const mergedPositions = positionMap(baseline);
  for (const { organization_id, x, y } of positions) {
    mergedPositions[organization_id] = { x, y };
  }
  return {
    positions: Object.entries(mergedPositions)
      .map(([organization_id, { x, y }]) => ({ organization_id, x, y }))
      .sort((first, second) =>
        first.organization_id.localeCompare(second.organization_id)
      ),
    writable_organization_ids:
      baseline?.writable_organization_ids ?? writableOrganizationIds,
  };
}

export function useOrganizationLayout({
  debounceMs = 500,
  enabled = true,
  layout,
  remoteLayout,
  saveLayout = saveOrganizationLayout,
}: UseOrganizationLayoutOptions = {}) {
  const {
    data: fetchedLayout,
    error: loadError,
    isLoading: isLayoutLoading,
    mutate: refreshLayout,
  } = useSWR(
    enabled && !layout && !remoteLayout
      ? "/api/user-service/organizations/layout"
      : null,
    getLayout,
    { shouldRetryOnError: false }
  );
  const incomingLayout = remoteLayout ?? layout ?? fetchedLayout;
  const [positions, setPositions] = useState<PositionMap>({});
  const [writableIds, setWritableIds] = useState<string[]>([]);
  const [status, setStatus] = useState<OrganizationLayoutStatus>("idle");
  const [saveError, setSaveError] = useState<Error | undefined>();
  const [dirtyVersion, setDirtyVersion] = useState(0);
  const dirtyPositionsRef = useRef<PositionMap>({});
  const latestRemoteRef = useRef<OrganizationLayoutResponse | undefined>(
    undefined
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const savePromiseRef = useRef<Promise<boolean> | undefined>(undefined);
  const replacementPromiseRef = useRef<Promise<boolean> | undefined>(undefined);
  const failedReplacementRef = useRef<PositionMap | undefined>(undefined);
  const mountedRef = useRef(true);

  const setIfMounted = useCallback((callback: () => void) => {
    if (mountedRef.current) callback();
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!incomingLayout) return;
    latestRemoteRef.current = incomingLayout;
    setWritableIds(incomingLayout.writable_organization_ids);
    const remotePositions = positionMap(incomingLayout);
    setPositions(() => {
      const nextPositions = { ...remotePositions };
      for (const [organizationId, position] of Object.entries(
        dirtyPositionsRef.current
      )) {
        nextPositions[organizationId] = position;
      }
      return nextPositions;
    });
  }, [incomingLayout]);

  const writableOrganizationIds = useMemo(
    () => new Set(writableIds),
    [writableIds]
  );

  const saveDirtyPositions = useCallback(async (): Promise<boolean> => {
    if (replacementPromiseRef.current) {
      return replacementPromiseRef.current.then(async (saved) => {
        if (!saved || Object.keys(dirtyPositionsRef.current).length === 0) {
          return saved;
        }
        return saveDirtyPositions();
      });
    }
    if (savePromiseRef.current) {
      return savePromiseRef.current.then(async (saved) => {
        if (!saved || Object.keys(dirtyPositionsRef.current).length === 0) {
          return saved;
        }
        return saveDirtyPositions();
      });
    }
    const pendingPositions = Object.entries(dirtyPositionsRef.current).map(
      ([organization_id, { x, y }]) => ({ organization_id, x, y })
    );
    if (pendingPositions.length === 0) return true;

    const savePromise = (async () => {
      setIfMounted(() => {
        setStatus("saving");
        setSaveError(undefined);
      });
      try {
        const result = await saveLayout(pendingPositions);
        for (const position of pendingPositions) {
          const currentPosition =
            dirtyPositionsRef.current[position.organization_id];
          if (
            currentPosition &&
            positionsEqual(currentPosition, { x: position.x, y: position.y })
          ) {
            delete dirtyPositionsRef.current[position.organization_id];
          }
        }
        const requestBaseline = mergeLayoutBaseline(
          latestRemoteRef.current,
          pendingPositions,
          writableIds
        );
        const savedBaseline = mergeLayoutBaseline(
          requestBaseline,
          result.positions,
          writableIds
        );
        latestRemoteRef.current = savedBaseline;
        void refreshLayout(savedBaseline, { revalidate: false });
        setIfMounted(() => {
          setDirtyVersion((version) => version + 1);
          setStatus("saved");
        });
        return true;
      } catch (caughtError) {
        setIfMounted(() => {
          setStatus("error");
          setSaveError(
            caughtError instanceof Error
              ? caughtError
              : new Error("Organization layout could not be saved")
          );
        });
        return false;
      } finally {
        savePromiseRef.current = undefined;
      }
    })();
    savePromiseRef.current = savePromise;
    return savePromise;
  }, [refreshLayout, saveLayout, setIfMounted, writableIds]);

  const scheduleSave = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = undefined;
      void saveDirtyPositions();
    }, debounceMs);
  }, [debounceMs, saveDirtyPositions]);

  const setPosition = useCallback(
    (organizationId: string, position: XYPosition) => {
      if (!writableOrganizationIds.has(organizationId)) return;
      dirtyPositionsRef.current[organizationId] = position;
      setPositions((currentPositions) => ({
        ...currentPositions,
        [organizationId]: position,
      }));
      setStatus("idle");
      setSaveError(undefined);
      setDirtyVersion((version) => version + 1);
      scheduleSave();
    },
    [scheduleSave, writableOrganizationIds]
  );

  const flush = useCallback(async (): Promise<boolean> => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = undefined;
    }
    let saved = await saveDirtyPositions();
    while (saved && Object.keys(dirtyPositionsRef.current).length > 0) {
      saved = await saveDirtyPositions();
    }
    return saved;
  }, [saveDirtyPositions]);

  const replacePositionsAndSave = useCallback(
    async (nextPositions: PositionMap): Promise<boolean> => {
      if (replacementPromiseRef.current) {
        return replacementPromiseRef.current;
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = undefined;
      }
      const activeSave = savePromiseRef.current;
      const replacementPromise = (async () => {
        if (activeSave) await activeSave;
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = undefined;
        }

        const writablePositions = Object.fromEntries(
          Object.entries(nextPositions).filter(([organizationId]) =>
            writableOrganizationIds.has(organizationId)
          )
        );
        let pendingPositions: OrganizationLayoutPosition[];
        try {
          pendingPositions = createOrganizationLayoutPayload(
            writablePositions,
            writableOrganizationIds
          );
        } catch (caughtError) {
          failedReplacementRef.current = writablePositions;
          setIfMounted(() => {
            setStatus("error");
            setSaveError(
              caughtError instanceof Error
                ? caughtError
                : new Error("Organization layout could not be saved")
            );
          });
          return false;
        }
        if (pendingPositions.length === 0) return true;
        setIfMounted(() => {
          setStatus("saving");
          setSaveError(undefined);
          setDirtyVersion((version) => version + 1);
        });
        try {
          const result = await saveLayout(pendingPositions);
          const requestBaseline = mergeLayoutBaseline(
            latestRemoteRef.current,
            pendingPositions,
            writableIds
          );
          const savedBaseline = mergeLayoutBaseline(
            requestBaseline,
            result.positions,
            writableIds
          );
          latestRemoteRef.current = savedBaseline;
          dirtyPositionsRef.current = {};
          failedReplacementRef.current = undefined;
          void refreshLayout(savedBaseline, { revalidate: false });
          setIfMounted(() => {
            setPositions(positionMap(savedBaseline));
            setStatus("saved");
            setDirtyVersion((version) => version + 1);
          });
          return true;
        } catch (caughtError) {
          failedReplacementRef.current = writablePositions;
          setIfMounted(() => {
            setStatus("error");
            setSaveError(
              caughtError instanceof Error
                ? caughtError
                : new Error("Organization layout could not be saved")
            );
          });
          return false;
        }
      })();
      replacementPromiseRef.current = replacementPromise;
      try {
        return await replacementPromise;
      } finally {
        if (replacementPromiseRef.current === replacementPromise) {
          replacementPromiseRef.current = undefined;
        }
      }
    },
    [
      refreshLayout,
      saveLayout,
      setIfMounted,
      writableIds,
      writableOrganizationIds,
    ]
  );

  const retry = useCallback(async () => {
    if (failedReplacementRef.current) {
      return replacePositionsAndSave(failedReplacementRef.current);
    }
    return flush();
  }, [flush, replacePositionsAndSave]);

  const discard = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = undefined;
    }
    dirtyPositionsRef.current = {};
    failedReplacementRef.current = undefined;
    setPositions(positionMap(latestRemoteRef.current));
    setStatus("idle");
    setSaveError(undefined);
    setDirtyVersion((version) => version + 1);
  }, []);

  return {
    positions,
    writableOrganizationIds,
    status,
    error: saveError ?? loadError,
    isLoading: enabled && !layout && !remoteLayout && isLayoutLoading,
    hasDirtyPositions:
      dirtyVersion > 0 &&
      (Object.keys(dirtyPositionsRef.current).length > 0 ||
        Boolean(failedReplacementRef.current)),
    isWritable: (organizationId: string) =>
      writableOrganizationIds.has(organizationId),
    setPosition,
    replacePositionsAndSave,
    flush,
    retry,
    discard,
    refresh: refreshLayout,
  };
}
